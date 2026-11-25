import os
from datetime import datetime

from google import genai
from google.genai import types


def load_client():
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("GEMINI_API_KEY environment variable is not set!")
    return genai.Client(http_options={"api_version": "v1alpha"})


MODEL = "gemini-3.8-live"

LIVE_CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=types.Content(
        role="system",
        parts=[
            types.Part(
                text=(
                    "You are a voice assistant for a Quectel Pi. "
                    "When the user asks to create a reminder, call create_reminder "
                    "with the reminder title and an ISO 8601 due_time. "
                    "Convert relative times such as tomorrow or 8 AM using the "
                    f"device local time and date: {datetime.now().isoformat()}. "
                    "Confirm the reminder naturally after it is created."
                )
            )
        ],
    ),
    tools=[
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="create_reminder",
                    description="Create a reminder for a future local date and time.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "title": types.Schema(
                                type="STRING",
                                description="What the reminder is for.",
                            ),
                            "due_time": types.Schema(
                                type="STRING",
                                description="Future reminder time as ISO 8601.",
                            ),
                        },
                        required=["title", "due_time"],
                    ),
                )
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
