# Pet and chat

From the project folder, run:

```powershell
.\.venv\Scripts\python.exe -m petlink
```

Or double-click `run_petlink.bat`.

The pet opens with a control strip underneath. Single-click the pet or press
the pencil to type; double-click it to open the main app. Drag to move it.
The microphone provides click-to-start/click-to-stop voice capture; the bell
opens task notification statements. A yellow exclamation badge means unread
alerts. Right-click for Open chat, Voice setup, character choice, expression
previews, reduced motion and Exit. Hiding chat keeps the pet visible.

Voice needs a local whisper.cpp executable and compatible ggml model. The first
microphone press opens setup if these are missing. See VOICE_AND_ALERTS.md.
The microphone never starts on launch or hover.

## Windows tray controls

Right-click the PetLink icon in the Windows notification area (it may be under
the overflow arrow) for Show/Hide pet, Open chat, Tasks & Pending,
Notifications with its unread count, Voice setup and Exit PetLink.
Double-click the tray icon to restore the pet and open chat. The icon follows
your selected character. The pet's menu also offers Hide pet to tray.
Hiding preserves drafts and keeps scheduled reminders running. It does not mark
alerts as read. Hiding is unavailable during recording/transcription so voice
status remains visible. If Windows has no tray available, the hide action is
omitted. Closing chat still leaves the pet running; Exit PetLink stops the app.
Launch remains manual, with no startup registration.

## Connect a local model

Start a local model server separately, then enter its server address and the
exact installed model name in chat. Examples of server addresses:

- Ollama: `http://127.0.0.1:11434`
- LM Studio: `http://localhost:1234`
- llama.cpp: the local address/port used when starting its compatible server

Root addresses and addresses ending in `/v1` are both accepted. Test connection
checks that the server's models endpoint responds; Send verifies generation with
the selected model. It does not download or start models automatically.

Enter sends; Shift+Enter adds a newline. Replies stream without blocking pet
animation. Stop cooperatively cancels; an outstanding server read may take up
to its socket timeout to return (120 seconds for local models, 25 for hosted
services). Local requests have a 180-second overall budget; hosted requests
retain 90 seconds. Retry preserves the original question.
You can type the next message while waiting. Duplicate submissions are blocked.

Local mode accepts loopback addresses only. Use Model settings to save a local
connection or select OpenAI, Grok or Google Gemini. Hosted endpoints are fixed
to the provider's official service; enter an exact model ID available to your
account, your API key, and explicitly enable cloud chat. Saving settings does
not send a request. Test connection checks access without sending your chat;
it does not guarantee that the selected model can generate a reply.

When cloud chat is enabled, Send and Retry transmit your message and bounded
recent conversation history to that provider. The connection label always
shows cloud mode. Charges may apply. Choose Local server to return to local
chat; provider switching preserves your history and unsent text.

Keys are masked. With Remember key enabled, they are saved through Windows
Credential Manager; otherwise they remain in this app session only. Uncheck
Remember key and save to remove that provider's remembered key. Keys are never
stored in SQLite or the ordinary settings file. Server/model/provider choice
is saved separately. No API key is required for local servers.
Messages and unfinished typed input now persist locally across restarts.
Use Settings → AI Model Settings for server/model configuration. Refresh models
lists installed local models; selecting a result fills the Model field. Test
connection runs in the background. Advanced options contains the thinking toggle.
Save applies the configuration; Cancel, Escape and X leave it unchanged. Chat
shows only a compact configured/connected indicator, and never assumes a service
is connected before a successful check or response.

The chat includes Copy actions, selectable messages, a microphone button that
requires a click, and short feedback with expandable Details. Drafts appear as
cards: Edit, Confirm and save, Pending, and Cancel. Confirm and save is explicit
activation of the previewed fields; Pending preserves an inactive proposal. Older
cards cannot activate a replacement draft. The pet parks outside chat or in a
reserved rail and hides temporarily for modal dialogs. Chat size/position persist.

Open Tasks & Pending to create, edit,
complete or remove tasks through a draft preview and explicit confirmation.
See PERSISTENCE.md for the data location and current feature boundaries.
For scheduled reminders, daily/weekly repeats and per-occurrence completion,
see REMINDERS.md. These features work without a model running.
For a month-long task, choose a daily repeat and use One month, or type an
inclusive Repeat until date. Review the exact dates before confirming.

For Ollama thinking models, Model settings offers Skip extended thinking. Enable
it if requests spend their output allowance on thinking and return no answer text.
It sends reasoning_effort=none only when enabled for a local connection; leave it
off for other servers unless they support that field. See the
[Ollama compatibility documentation](https://docs.ollama.com/api/openai-compatibility).

## Check saved tasks and reminders

General questions such as "Are there any schedules for me?", "What's on my
schedule?", "Show my reminders" and "List my tasks" read local SQLite directly,
even without a configured model. No calendar account or cloud service is queried.
The reply lists up to 20 confirmed unfinished records, their dates, timezones,
repeat/end details and series status, and points to Tasks & Pending for more.
Done/removed tasks are excluded; ended series are labeled as ended. General
schedule queries include dated tasks; reminder queries require a timed reminder
or recurrence; task queries also include undated tasks.

Pending drafts are counted separately and are not active reminders. The lookup
does not confirm, complete, acknowledge alerts or generate scheduled occurrences.
Read errors preserve your question and never claim that the database is empty.
Ordinary chat history is saved as usual, and an existing task follow-up stays
parked. These explicit general-list queries do not interpret date-filtered or
compound mutation requests.

## Draft one task from text or voice

Clear supported reminder phrases bypass model inference. For example, Send
"Remind me to make a cake at 13:00 tomorrow" opens a one-off draft with that
date and time; the common typo "tommorow" is accepted. Review draft and Confirm
changes are still required. If another task follow-up is parked, choose Start
new first so the separate request cannot overwrite it.

Explicit "Add a task…", "Create a task…" and "Remind me…" requests select
task-draft mode on Send, including Retry of a previously failed request.
Common dated/timed forms are interpreted locally, including:

- "create a task to do some workout tommorow at 13:00"
- "Add a task for tommorow to do DSA questions for 1 hour and reminder at 14:00 hours"

These preserve the activity and any stated duration in the title; they do not
ask for exercises, ingredients or other optional planning details. No duration
tracking metric is invented. Other explicit creation requests use the model's
task-interpretation prompt, never the ordinary chat prompt. With another task
context parked, Start new remains explicit to protect that earlier draft.

For "daily remind me of Doing DSA for 7 days at 14:00", the app asks for the
start date without inference. Replace the message with "tomorrow" or a YYYY-MM-DD
date and choose Continue task draft. End dates are calculated inclusively, so
seven days starting November 6 end November 12. Explicit "starting tomorrow"
phrases can skip that question. Unsupported phrasing still uses the model;
there is no broad heuristic that executes tasks from arbitrary chat text.

Local chat sends at most eight recent messages and 8,000 content characters to
reduce prompt processing on smaller models. Hosted chat retains the existing
16-message/24,000-character cap. The saved SQLite transcript is not deleted.
Default model replies are brief unless you request more detail. Smaller models
can misinterpret complex requests; inspect the draft fields before confirmation.

Write a request in chat (or review a voice transcript), then press
Draft task from message instead of Send. It uses the selected provider and the
same cloud consent settings. The task request, bounded task follow-up history,
current draft fields and Asia/Kolkata date context are sent for this action.
Ordinary chat history and unrelated saved tasks are not included. No extra model
or API key is required.

The model can draft one new task with its title, description, priority, due/start
date and supported daily/weekly reminder schedule. Inspect every field in Review
task draft, especially relative dates and reminder times. Review draft saves only
a pending proposal; select it in Tasks & Pending and use Confirm changes to
activate it. Cancel abandons the generated form without creating a pending action.
Your original message remains editable throughout. Normal Send remains chat for
requests outside the explicit reminder patterns above.

If details are ambiguous, replace the message with your answer and press
Continue task draft. The visible Task follow-up label identifies its subject or
question. You can also enter a short correction such as "make it 3" after reviewing
a draft. Only returned correction fields are merged; omitted dates, priority and
schedule fields are preserved. Inspect all changes before reviewing again.

When the current task already has a saved pending draft, Review draft revises that
same draft and requires a fresh confirmation. Cancelling its editor preserves the
previous pending fields. Confirmed, discarded or externally edited drafts cannot
be changed by a stale follow-up. Use Tasks & Pending to review them.

Task follow-up context is stored separately in local SQLite and resumes after a
restart. Ordinary chat leaves it parked. Start new clears
this one follow-up context without deleting saved pending drafts; replace the
composer text with your separate new task. Up to six task exchanges are retained;
the app asks you to review or start new when that bounded context is full.
Malformed output, unsupported fields, Stop and errors never execute task changes.
Multi-task batches, edits by saved task name and structured metrics remain future
work. Model interpretations and field choices still require human review.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

The suite uses fake providers and a loopback HTTP server, never a paid API.
