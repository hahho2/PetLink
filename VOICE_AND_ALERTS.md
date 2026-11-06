# Pet controls, voice and notifications

Launch `run_petlink.bat` or `.\.venv\Scripts\python.exe -m petlink`.
The pet opens on its own; double-click it to open the main app.

## Under the pet

- Pencil or single click: open quick typing. The draft is shared with chat and
  follows its local persistence behavior.
- Microphone: click to record, click again to stop; it stops after 30 seconds.
  Listening has a red button and visible status. Capture is off at launch.
- Bell or yellow exclamation badge: open full notification statements. Read the
  text, open Tasks & Pending, or explicitly Mark selected as read.
- Quick input arrow: send text through the selected local model. Chat still
  requires its server/model configuration. Task changes still require confirmation.

## Local speech setup

Right-click → Voice setup, or press the microphone before configuring it.
Select an existing `whisper-cli.exe` and compatible `ggml-*.bin` model. Paths
are saved locally; these files are not downloaded by the app. No API key is used.

The subprocess follows the official [whisper.cpp CLI documentation](https://github.com/ggml-org/whisper.cpp/tree/master/examples/cli):
`-m`, `-f`, `-otxt`, `-of`, `-l auto`, `-ng`, and two CPU threads. Qt Multimedia
captures the default microphone; a worker converts native PCM to 16 kHz mono
PCM16. Temporary audio/transcript files are removed when transcription finishes.
The process times out after two minutes and is killed on shutdown.

Transcribed text becomes an editable draft; it is never sent or executed
automatically. Review it, then send. Voice and model generation are gated so
they do not run together. Silence may still produce incorrect transcription.

In chat, click Mic, speak, and click Stop mic. Listening/transcription status
appears in chat. The transcript appends to existing composer text for review;
Send uses the selected model or the existing local task-request route. Draft
task from message explicitly interprets a task; Confirm changes activates it.
When chat is hidden, the pet microphone keeps its quick-input review flow.
Whisper handles speech only; it shares no weights with the selected reasoning
model and needs no API key.

If recording fails, check Windows microphone access and the default input.
Install whisper.cpp and a compatible model separately, then configure their
paths in Voice setup. Actual microphone capture needs verification on your
device. Fixtures verify conversion, CLI arguments,
WAV format, temporary cleanup and draft-only delivery. Tests never activate a mic.

## Task notifications

Active due/overdue tasks produce local inbox statements on startup, once a minute,
and after confirmation. Dates use Windows local time; no specific reminder hour
is inferred. Completed/removed tasks do not produce new alerts. SQLite deduplicates
each task/due-date pair across restarts. Existing statements are historical
snapshots. Unread badges remain until explicit acknowledgement; the inbox shows
100 statements at a time with Load older notifications. This is an in-app inbox,
not Windows push notifications. Confirmed timed reminders and daily/weekly
recurrence are now supported too; see REMINDERS.md.

Graphify maintains the source map in `src/graphify-out/`. Ponytail keeps this to
Qt controls and a standard-library whisper subprocess without extra audio frameworks.
