import os

from google import genai
from google.genai import types


def load_client():
    if "GEMINI_API_KEY" not in os.environ:
        raise ValueError("GEMINI_API_KEY environment variable is not set!")
    return genai.Client(http_options={"api_version": "v1alpha"})


MODEL = "gemini-3.8-live"

LIVE_CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),
)
