import asyncio
import sqlite3

from audio import drain_queue, mic_sender, speaker_player
from config import LIVE_CONFIG, MODEL, load_client
from personal_data import TodoNotesStore
from reminders import ReminderStore, parse_due_time
from google.genai import types


def handle_tool_call(function_call, reminder_store, personal_store):
    name = function_call.name
    args = function_call.args or {}
    try:
        if name == "create_reminder":
            title = str(args.get("title", "")).strip()
            due_time = str(args.get("due_time", "")).strip()
            reminder_id = reminder_store.create(title, parse_due_time(due_time))
            result = {"result": "Reminder created", "reminder_id": reminder_id}
            print(f'[reminder]: created #{reminder_id} "{title}" for {due_time}')
        elif name == "add_todo":
            todo_id = personal_store.add_todo(str(args.get("title", "")))
            result = {"result": "To-do added", "todo_id": todo_id}
            print(f"[todo]: added #{todo_id}")
        elif name == "list_todos":
            todos = personal_store.list_todos(args.get("status", "pending"))
            result = {"result": "To-do list", "items": todos}
        elif name == "complete_todo":
            todo_id = args.get("todo_id")
            if not isinstance(todo_id, int) or isinstance(todo_id, bool):
                raise ValueError("To-do ID must be an integer")
            if not personal_store.complete_todo(todo_id):
                raise ValueError(f"No pending to-do found with ID {todo_id}")
            result = {"result": "To-do marked complete", "todo_id": todo_id}
            print(f"[todo]: completed #{todo_id}")
        elif name == "add_note":
            note_id = personal_store.add_note(
                str(args.get("title", "")),
                str(args.get("content", "")),
            )
            result = {"result": "Note saved", "note_id": note_id}
            print(f"[note]: saved #{note_id}")
        elif name == "list_notes":
            limit = args.get("limit", 10)
            notes = personal_store.list_notes(limit)
            result = {"result": "Recent notes", "items": notes}
        elif name == "search_notes":
            notes = personal_store.search_notes(str(args.get("query", "")))
            result = {"result": "Matching notes", "items": notes}
        else:
            result = {"error": f"Unsupported tool: {name}"}
    except (TypeError, ValueError, sqlite3.Error) as exc:
        result = {"error": str(exc)}
        print(f"[tool error] {name}: {exc}")

    return types.FunctionResponse(
        id=function_call.id,
        name=name,
        response=result,
    )


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


async def audio_receiver(
    session,
    play_queue: asyncio.Queue,
    stop_event: asyncio.Event,
    reminder_store: ReminderStore,
    personal_store: TodoNotesStore,
):
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

                    if getattr(response, "tool_call", None):
                        function_responses = [
                            handle_tool_call(
                                function_call,
                                reminder_store,
                                personal_store,
                            )
                            for function_call in response.tool_call.function_calls
                        ]

                        await session.send_tool_response(
                            function_responses=function_responses
                        )

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


async def reminder_scheduler(
    session, stop_event: asyncio.Event, reminder_store: ReminderStore
):
    """Send due reminders back through Gemini so they are spoken aloud."""
    while not stop_event.is_set():
        try:
            for reminder in reminder_store.get_due():
                if stop_event.is_set():
                    break
                reminder_store.mark_triggered(reminder["id"])
                print(f"[reminder]: due #{reminder['id']} \"{reminder['title']}\"")
                await session.send_realtime_input(
                    text=f"Reminder: {reminder['title']}"
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            print(f"[reminder_scheduler error]: {exc}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


async def run_session(stop_event: asyncio.Event):
    client = load_client()
    play_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
    player_task = asyncio.create_task(speaker_player(play_queue, stop_event))
    reminder_store = ReminderStore()
    personal_store = TodoNotesStore(reminder_store.db_path)
    loop_tasks: list[asyncio.Task] = []

    try:
        async with client.aio.live.connect(model=MODEL, config=LIVE_CONFIG) as session:
            print("Connected to Gemini Live API!")
            await play_initial_greeting(session, play_queue, stop_event)
            if stop_event.is_set():
                return

            loop_tasks = [
                asyncio.create_task(mic_sender(session, stop_event)),
                asyncio.create_task(
                    audio_receiver(
                        session,
                        play_queue,
                        stop_event,
                        reminder_store,
                        personal_store,
                    )
                ),
                asyncio.create_task(
                    reminder_scheduler(session, stop_event, reminder_store)
                ),
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
