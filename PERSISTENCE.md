# SQLite foundation

Use `run_petlink.bat` or `.\.venv\Scripts\python.exe -m petlink`.
The project environment now contains all declared dependencies.

## Stored locally

The default database is `%LOCALAPPDATA%\PetLink\petlink.sqlite3`. Python includes
the SQLite engine; no separate database download or server is needed. SQLAlchemy
owns connections and transactions, Alembic applies the packaged initial migration.
`PETLINK_DATA_DIR` can override the data directory for development/tests.

Chat resumes the most recent conversation. Sent messages and completed replies
are saved; partial replies are marked incomplete and excluded from model context.
Unsent input is saved after a short debounce and when the chat closes. A crash
within the debounce window can lose the most recent keystrokes. The visible
transcript and model context are bounded; the database retains older records.
Conversation switching, search and paging through older chat are future work.

## Tasks and Pending

Open Tasks & Pending in chat. Use New task to enter a title, description, status,
priority and optional YYYY-MM-DD due date. Review draft saves a pending proposal.
Select that proposal to inspect its exact fields, edit it or Confirm changes.
Until confirmation, it is not an active task. Pending drafts survive restarts.

Select a task and Edit to change its fields or mark it Done. Remove proposes a
soft removal; the preview explains that local records and audit are retained.
Confirm changes executes the operation. Discard draft explicitly abandons a
pending proposal without changing saved tasks. Refresh reloads local records.
Both lists offer Load more in batches of 100.

`Database.confirm` checks the reviewed draft revision and each target task's
version. It applies up to 20 actions, their audit records and the pending-state
change in one transaction. Any failure rolls back the whole proposal. Repeated
confirmation cannot duplicate a task. Edits invalidate prior draft confirmations.
If a task changes underneath a draft, discard it and start a new edit from the
current saved record. The current UI authors one action at a time; the service
already supports atomic batches for later natural-language proposals.

Lifecycle timestamps are UTC ISO strings. Due dates are date-only values, not
UTC instants. Foreign keys, constraints, indexes, WAL and a bounded lock timeout
are enabled. The frozen initial migration must be extended with new revision
files, not silently edited for existing databases.

## Boundaries and verification

This milestone does not implement goals, custom metrics,
LLM task parsing, cloud sync, backup/restore UI or deletion of audit history.
The AI remains a chat/planning interface; it cannot execute or claim saved tasks.
The task form works without a model running. Persistence is on local disk; no
encryption-at-rest mechanism is added by this implementation.

Migration 002 adds persistent due-task notifications. The manually running app
checks date-only due/overdue tasks every minute and on task confirmation, using
the Windows local date. Each task/due-date pair alerts once; acknowledgements
are saved. It does not run a background service while PetLink is closed.

Migration 003 adds confirmed one-off/daily/weekly schedules, separate occurrences,
UTC reminder instants and completion history. Notification event keys prevent
repeated delivery across restarts. See REMINDERS.md for timing and catch-up bounds.

Tests use disposable databases and a loopback model fixture. They cover migration
reopen, foreign keys, restart recovery, proposal edits, stale revisions, duplicate
confirmation, rollback with no audit leakage, soft removal, chat save failures,
retry-save without duplicate inference and the existing pet/chat behavior.

Ponytail keeps this milestone to one service and one migration. Graphify's source
map is refreshed in `src/graphify-out/`; it maps code relationships, not all asset
or business-document semantics. No cloud graph backend is required.
