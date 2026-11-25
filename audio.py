import asyncio
import math
import struct

from google.genai import types


CHUNK_SIZE = 3200


def pcm16_rms(pcm_bytes: bytes) -> float:
    sample_count = len(pcm_bytes) // 2
    if sample_count == 0:
        return 0.0
    samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
    return math.sqrt(sum(s * s for s in samples) / sample_count)


def drain_queue(play_queue: asyncio.Queue):
    while not play_queue.empty():
        try:
            play_queue.get_nowait()
            play_queue.task_done()
        except asyncio.QueueEmpty:
            break


async def stop_process(proc: asyncio.subprocess.Process | None):
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

            rms = pcm16_rms(chunk)
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
        await stop_process(proc)
        if proc.stderr:
            try:
                err_out = await asyncio.wait_for(proc.stderr.read(), timeout=0.3)
                err_msg = err_out.decode(errors="ignore").strip()
                if err_msg and not stop_event.is_set():
                    print(f"[arecord stderr]: {err_msg}")
            except Exception:
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
        await stop_process(proc)
