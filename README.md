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

## To-dos and notes

Use natural requests such as:

- "Add buy groceries to my to-do list."
- "What's on my to-do list?"
- "Mark buy groceries as done."
- "Take a note: the workshop starts at 9 AM."
- "Find my note about the workshop."

To-dos and notes are stored locally in the same SQLite database. The assistant
can list and complete to-dos, and list or search saved notes.