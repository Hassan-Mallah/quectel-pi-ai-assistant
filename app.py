import asyncio
import math
import os
import signal
import struct
import sys
from google import genai
from google.genai import types

if "GEMINI_API_KEY" not in os.environ:
    raise ValueError("GEMINI_API_KEY environment variable is not set!")

client = genai.Client(http_options={"api_version": "v1alpha"})
model = "gemini-3.8-live"

CHUNK_SIZE = 3200  # 100ms of 16kHz 16-bit mono PCM (16000 * 2 * 0.1)

config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),
)


def _pcm16_rms(pcm_bytes: bytes) -> float:
    sample_count = len(pcm_bytes) // 2
    if sample_count == 0:
        return 0.0
    samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
    return math.sqrt(sum(s * s for s in samples) / sample_count)


def _drain_queue(play_queue: asyncio.Queue):
    while not play_queue.empty():
        try:
            play_queue.get_nowait()
            play_queue.task_done()
        except asyncio.QueueEmpty:
            break


async def _stop_proc(proc: asyncio.subprocess.Process | None):
    if not proc:
        return
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.5)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass


async def play_initial_greeting(
    session, play_queue: asyncio.Queue, stop_event: asyncio.Event, timeout: float = 10.0
):
    """Send an initial 'Hello' and collect its audio response."""
    if stop_event.is_set():
        return
    print("[init]: Sending initial 'Hello' to Gemini Live...")
    await session.send_realtime_input(text="Hello")

    async def _collect_greeting():
        async for response in session.receive():
            if stop_event.is_set():
                return
            if getattr(response, "go_away", None):
                print("[init]: server sent go_away")
                stop_event.set()
                return

            server_content = response.server_content
            if not server_content:
                continue

            if server_content.model_turn:
                for part in server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        audio_data = part.inline_data.data
                        if len(audio_data) >= 32 and not play_queue.full():
                            await play_queue.put(audio_data)

            if server_content.turn_complete:
                print("[init]: Greeting received.")
                return

    try:
        await asyncio.wait_for(_collect_greeting(), timeout=timeout)
    except asyncio.TimeoutError:
        print("[init]: Timed out waiting for greeting; starting mic loop anyway.")


async def mic_sender(session, stop_event: asyncio.Event):
    """Stream microphone audio from -D default to Gemini Live with RMS logging."""
    arecord_cmd = [
        "arecord",
        "-D",
        "default",
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-t",
        "raw",
        "-q",
        "-",
    ]

    proc = await asyncio.create_subprocess_exec(
        *arecord_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print("Mic live - speak naturally. Press Ctrl+C to exit.")
    chunks_sent = 0
    max_rms = 0.0

    try:
        while not stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(CHUNK_SIZE), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if not chunk:
                print("[mic]: EOF reached (arecord exited)")
                break

            rms = _pcm16_rms(chunk)
            if rms > max_rms:
                max_rms = rms

            chunks_sent += 1
            if chunks_sent % 20 == 1:
                print(f"[mic]: chunk={chunks_sent} rms={rms:.1f} peak={max_rms:.1f}")
                max_rms = 0.0

            if stop_event.is_set():
                break

            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        if not stop_event.is_set():
            print(f"[mic_sender error]: {exc}")
    finally:
        await _stop_proc(proc)
        if proc.stderr:
            try:
                err_out = await asyncio.wait_for(proc.stderr.read(), timeout=0.3)
                err_msg = err_out.decode(errors="ignore").strip()
                if err_msg and not stop_event.is_set():
                    print(f"[arecord stderr]: {err_msg}")
            except Exception:
                pass


async def audio_receiver(session, play_queue: asyncio.Queue, stop_event: asyncio.Event):
    """Receive audio chunks and transcripts from Gemini Live."""
    last_msg = asyncio.get_running_loop().time()

    try:
        while not stop_event.is_set():
            try:
                async for response in session.receive():
                    if stop_event.is_set():
                        return

                    now = asyncio.get_running_loop().time()
                    if getattr(response, "go_away", None):
                        print("[server]: go_away received")
                        _drain_queue(play_queue)
                        stop_event.set()
                        return

                    server_content = response.server_content
                    if not server_content:
                        continue

                    in_tx = getattr(server_content, "input_transcription", None)
                    tx_text = getattr(in_tx, "text", None) if in_tx else None
                    if tx_text:
                        print(f"[heard +{now - last_msg:.2f}s]: {tx_text}")
                        last_msg = now

                    if server_content.interrupted:
                        print("[server]: interrupted")
                        _drain_queue(play_queue)
                        continue

                    if server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_data = part.inline_data.data
                                if len(audio_data) >= 32 and not play_queue.full():
                                    await play_queue.put(audio_data)
                                    last_msg = now

                    if server_content.turn_complete:
                        print("[server]: turn_complete")
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if stop_event.is_set():
                    return
                print(f"[audio_receiver error]: {exc}")
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass


async def speaker_player(play_queue: asyncio.Queue, stop_event: asyncio.Event):
    """Play queued 24kHz PCM audio chunks through aplay -D default."""
    aplay_cmd = [
        "aplay",
        "-D",
        "default",
        "-r",
        "24000",
        "-f",
        "S16_LE",
        "-c",
        "1",
        "-q",
    ]

    proc = await asyncio.create_subprocess_exec(
        *aplay_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    chunks_played = 0
    bytes_played = 0

    try:
        while not stop_event.is_set() or not play_queue.empty():
            try:
                audio_data = await asyncio.wait_for(play_queue.get(), timeout=0.15)
            except asyncio.TimeoutError:
                continue

            try:
                if proc.stdin and not proc.stdin.is_closing():
                    proc.stdin.write(audio_data)
                    await proc.stdin.drain()
                    chunks_played += 1
                    bytes_played += len(audio_data)
                    if chunks_played % 15 == 1:
                        print(
                            f"[speaker]: played {chunks_played} chunks ({bytes_played} bytes)"
                        )
            except (BrokenPipeError, OSError) as exc:
                if not stop_event.is_set():
                    print(f"[aplay write error]: {exc}")
                break
            finally:
                play_queue.task_done()
    except asyncio.CancelledError:
        pass
    finally:
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
        if proc.stderr:
            try:
                err_out = await asyncio.wait_for(proc.stderr.read(), timeout=0.3)
                err_msg = err_out.decode(errors="ignore").strip()
                if err_msg and not stop_event.is_set():
                    print(f"[aplay stderr]: {err_msg}")
            except Exception:
                pass
        await _stop_proc(proc)


async def _run_session(stop_event: asyncio.Event):
    play_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
    player_task = asyncio.create_task(speaker_player(play_queue, stop_event))
    loop_tasks: list[asyncio.Task] = []

    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            print("Connected to Gemini Live API!")
            await play_initial_greeting(session, play_queue, stop_event)
            if stop_event.is_set():
                return

            loop_tasks = [
                asyncio.create_task(mic_sender(session, stop_event)),
                asyncio.create_task(audio_receiver(session, play_queue, stop_event)),
            ]

            stop_waiter = asyncio.create_task(stop_event.wait())
            done_set = {t for t in loop_tasks if t.done()}
            if not done_set:
                _, _ = await asyncio.wait(
                    [stop_waiter, *loop_tasks],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            if not stop_waiter.done():
                stop_waiter.cancel()
                await asyncio.gather(stop_waiter, return_exceptions=True)
    finally:
        stop_event.set()
        _drain_queue(play_queue)
        for t in (*loop_tasks, player_task):
            if not t.done():
                t.cancel()
        await asyncio.gather(*loop_tasks, player_task, return_exceptions=True)


async def main():
    stop_event = asyncio.Event()
    sigint_count = 0

    def _handle_sig(signum, frame):
        nonlocal sigint_count
        sigint_count += 1
        if sigint_count == 1:
            print("\n[exit]: Stopping gracefully (press Ctrl+C again to force quit)...")
            stop_event.set()
        else:
            print("\n[exit]: Force quitting.", file=sys.stderr)
            os._exit(130)

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    try:
        await asyncio.wait_for(_run_session(stop_event), timeout=None)
    except asyncio.CancelledError:
        pass
    finally:
        print("[exit]: Done.")


if __name__ == "__main__":
    asyncio.run(main())