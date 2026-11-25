import asyncio

from audio import drain_queue, mic_sender, speaker_player
from config import LIVE_CONFIG, MODEL, load_client


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
                        drain_queue(play_queue)
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
                        drain_queue(play_queue)
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


async def run_session(stop_event: asyncio.Event):
    client = load_client()
    play_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
    player_task = asyncio.create_task(speaker_player(play_queue, stop_event))
    loop_tasks: list[asyncio.Task] = []

    try:
        async with client.aio.live.connect(model=MODEL, config=LIVE_CONFIG) as session:
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
                await asyncio.wait(
                    [stop_waiter, *loop_tasks],
                    return_when=asyncio.FIRST_COMPLETED,
                )
            if not stop_waiter.done():
                stop_waiter.cancel()
                await asyncio.gather(stop_waiter, return_exceptions=True)
    finally:
        stop_event.set()
        drain_queue(play_queue)
        for task in (*loop_tasks, player_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(*loop_tasks, player_task, return_exceptions=True)
