# quectel-pi-ai-assistant

Voice AI assistant for the Quectel Pi. It uses Gemini Live, the Pi microphone,
and its speaker.

## Run

Set the Gemini API key and start the assistant:

```bash
export GEMINI_API_KEY="your-api-key"
python app.py
```

## Create a reminder

Speak naturally, for example:

> "Remind me tomorrow at 8 AM to start my morning workout."

Gemini calls the local `create_reminder` tool. Reminders are stored in SQLite at
`~/.quectel-pi-ai-assistant/reminders.db` and are spoken aloud when due.