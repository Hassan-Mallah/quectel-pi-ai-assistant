import os
from datetime import datetime

from google import genai
from google.genai import types


def load_client():
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("GEMINI_API_KEY environment variable is not set!")
    return genai.Client(http_options={"api_version": "v1beta"})


MODEL = "gemini-3.8-live"


def function_declaration(name, description, properties, required=None):
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=types.Schema(
            type="OBJECT",
            properties=properties,
            required=required or [],
        ),
    )


LIVE_CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=types.Content(
        role="system",
        parts=[
            types.Part(
                text=(
                    "You are a voice assistant for a Quectel Pi. "
                    "Answer general-knowledge questions directly using your "
                    "built-in knowledge; do not claim you lack general information. "
                    "Use Google Search for current or time-sensitive information, "
                    "such as weather, news, schedules, and prices. Base answers on "
                    "the search results, briefly mention sources aloud, and be clear "
                    "if current information cannot be found. Ask for a location "
                    "when one is needed and the user has not provided it. "
                    "Use tools for reminders, to-dos, and notes, and only confirm "
                    "an action after its tool succeeds. For reminders, call "
                    "create_reminder with a title and ISO 8601 due_time. "
                    "Convert relative times such as tomorrow or 8 AM using the "
                    f"device local time and date: {datetime.now().isoformat()}. "
                    "If a reminder time is unclear, ask the user before creating it. "
                    "Use add_todo to save tasks, list_todos to review them, and "
                    "complete_todo to finish one. If the task is not uniquely "
                    "identified, list tasks and clarify rather than completing a "
                    "guess. Use add_note to save notes, list_notes for recent notes, "
                    "and search_notes to find notes. Read list results briefly and "
                    "do not invent saved content."
                )
            )
        ],
    ),
    tools=[
        # {"google_search": {}},
        types.Tool(
            function_declarations=[
                function_declaration(
                    "create_reminder",
                    "Create a reminder for a future local date and time.",
                    {
                        "title": types.Schema(
                            type="STRING",
                            description="What the reminder is for.",
                        ),
                        "due_time": types.Schema(
                            type="STRING",
                            description="Future reminder time as ISO 8601.",
                        ),
                    },
                    ["title", "due_time"],
                ),
                function_declaration(
                    "add_todo",
                    "Add an item to the user's to-do list.",
                    {"title": types.Schema(type="STRING", description="The to-do task.")},
                    ["title"],
                ),
                function_declaration(
                    "list_todos",
                    "List to-do items by status.",
                    {
                        "status": types.Schema(
                            type="STRING",
                            description="Filter by pending, completed, or all.",
                            enum=["pending", "completed", "all"],
                        )
                    },
                ),
                function_declaration(
                    "complete_todo",
                    "Mark a pending to-do complete using its ID.",
                    {
                        "todo_id": types.Schema(
                            type="INTEGER",
                            description="ID from list_todos.",
                        )
                    },
                    ["todo_id"],
                ),
                function_declaration(
                    "add_note",
                    "Save a note with a short title and its full content.",
                    {
                        "title": types.Schema(
                            type="STRING",
                            description="A concise note title.",
                        ),
                        "content": types.Schema(
                            type="STRING",
                            description="The note content to preserve.",
                        ),
                    },
                    ["title", "content"],
                ),
                function_declaration(
                    "list_notes",
                    "List recent saved notes.",
                    {
                        "limit": types.Schema(
                            type="INTEGER",
                            description="Number of recent notes to return, from 1 to 50.",
                        )
                    },
                ),
                function_declaration(
                    "search_notes",
                    "Find saved notes containing a phrase.",
                    {
                        "query": types.Schema(
                            type="STRING",
                            description="Text to search for.",
                        )
                    },
                    ["query"],
                ),
            ]
        )
    ],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),
)
