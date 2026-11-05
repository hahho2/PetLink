# PetLink

A Windows desktop productivity companion built with Python and PySide6.
Choose Ishu, Coral or Lola, chat with a local model, and manage tasks through
editable drafts and explicit confirmation. Data stays in local SQLite.

## Run from source

Requires Python 3.11 or newer on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m petlink
```

Once dependencies are installed, double-click `run_petlink.bat`.

- Chat keeps model configuration in Settings, with background model discovery and
  connection tests. Conversation bubbles support Copy, microphone input remains
  explicit, and task cards offer reviewed confirmation or inactive Pending storage.
- Single-click the pet or pencil to type; double-click to open the main app.
- Right-click the Windows tray icon to hide/show the pet, open chat, tasks or
  notifications, or exit. Double-click the tray icon to restore the pet and chat.
  Reminders continue while the pet is hidden; unread alerts stay unread.
- Configure a local server and installed model in Settings. Ollama, LM Studio and
  other OpenAI-compatible loopback servers are supported. Connection details are
  remembered after Save and restored next launch.
- Model settings also supports opt-in OpenAI, Grok and Google Gemini chat.
  Enter your model ID and key; optional key storage uses Windows Credential
  Manager. The chat clearly labels when messages leave this laptop.
- Tasks & Pending supports task drafts, confirmation, daily/weekly recurrence,
  scheduled reminders and per-occurrence completion without loading an AI model.
- Type or transcribe one new task, then choose Draft task from message. The
  selected model prepares editable fields; Review draft saves a pending proposal,
  and Confirm changes is still required to create the task.
- Answer a clarification or correct the current draft with Continue task draft.
  Its context survives restarts; Start new begins a separate request and keeps
  saved pending drafts.
- Clear reminders such as "Remind me to make a cake at 13:00 tomorrow" open
  review directly on Send, without a model call. A daily reminder for a stated
  number of days gets exact calendar dates after you supply its start date.
- Explicit Add/Create task requests select task-draft mode on Send rather than
  ordinary chat. Common dated/timed forms are parsed locally; other forms use
  model interpretation. All still require review and confirmation.
- Ask "Are there any schedules for me?", "Show my reminders" or "List my tasks"
  to read confirmed local records without a model. Pending drafts are counted
  separately and do not appear as active tasks.
- The bell and exclamation badge show persistent, readable task alerts.
- Voice input uses a separately installed whisper.cpp executable and ggml model.
  Recording starts only on microphone activation; transcribed text is reviewed
  before sending. Configure local paths through the pet's Voice setup menu.

## Data and scope

SQLite is stored under the user's local app-data PetLink folder. `PETLINK_DATA_DIR`
can override the data directory for development. The repository excludes user
databases, downloaded speech models/binaries, virtual environments, credentials,
generated previews and machine-specific setup notes.

Reminders run only while the manually launched app is open. Local chat is the
default; hosted chat requires explicit opt-in and a provider API key.
Chat cannot execute task changes. Model-assisted drafting currently handles
one new task per request; edits, completion and removal use Tasks & Pending.
Screenshot logging, monthly/custom repeat
rules, backup/restore UI and analytics remain future work.

See [pet/chat usage](PET_WINDOW.md), [persistence](PERSISTENCE.md),
[reminders](REMINDERS.md), [voice and alerts](VOICE_AND_ALERTS.md), and
[character asset provenance](src/petlink/assets/README.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Tests use disposable databases, simulated clocks and a loopback server. They
do not record the microphone or require a paid API.

<!-- streak update: 2026-11-05 -->
