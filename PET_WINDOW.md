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
to its 25-second socket timeout to return. Retry preserves the original question.
You can type the next message while waiting. Duplicate submissions are blocked.

This milestone's chat form accepts loopback addresses only. Hosted adapters
remain in the provider layer for later Settings and secure credential work.
Messages and unfinished typed input now persist locally across restarts.
Connection fields remain session-only. Open Tasks & Pending to create, edit,
complete or remove tasks through a draft preview and explicit confirmation.
See PERSISTENCE.md for the data location and current feature boundaries.
For scheduled reminders, daily/weekly repeats and per-occurrence completion,
see REMINDERS.md. These features work without a model running.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

The suite uses fake providers and a loopback HTTP server, never a paid API.
