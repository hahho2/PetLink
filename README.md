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

- Single-click the pet or pencil to type; double-click to open the main app.
- Configure a local server and installed model in chat. Ollama, LM Studio and
  other OpenAI-compatible loopback servers are supported.
- Tasks & Pending supports task drafts, confirmation, daily/weekly recurrence,
  scheduled reminders and per-occurrence completion without loading an AI model.
- The bell and exclamation badge show persistent, readable task alerts.
- Voice input uses a separately installed whisper.cpp executable and ggml model.
  Recording starts only on microphone activation; transcribed text is reviewed
  before sending. Configure local paths through the pet's Voice setup menu.

## Data and scope

SQLite is stored under the user's local app-data PetLink folder. `PETLINK_DATA_DIR`
can override the data directory for development. The repository excludes user
databases, downloaded speech models/binaries, virtual environments, credentials,
generated previews and machine-specific setup notes.

Reminders run only while the manually launched app is open. Hosted provider
adapters exist, but cloud credential settings are not yet exposed in the UI.
AI chat cannot execute task changes. Screenshot logging, monthly/custom repeat
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
