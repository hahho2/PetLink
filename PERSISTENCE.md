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

General task/schedule/reminder questions use Database.task_overview for a bounded
read of confirmed unfinished records plus a separate pending-draft count. They
do not poll schedules, create occurrences, mark alerts read or confirm changes.
The response is persisted as ordinary chat; save retries reuse the same answer.

This milestone does not implement goals, custom metrics,
cloud sync, backup/restore UI or deletion of audit history.
Model-assisted new-task parsing and corrections produce reviewed drafts only;
the AI cannot execute or claim saved task changes.
The task form works without a model running. Persistence is on local disk; no
encryption-at-rest mechanism is added by this implementation.

Migration 002 adds persistent due-task notifications. The manually running app
checks date-only due/overdue tasks every minute and on task confirmation, using
the Windows local date. Each task/due-date pair alerts once; acknowledgements
are saved. It does not run a background service while PetLink is closed.

Migration 003 adds confirmed one-off/daily/weekly schedules, separate occurrences,
UTC reminder instants and completion history. Notification event keys prevent
repeated delivery across restarts. See REMINDERS.md for timing and catch-up bounds.

Migration 004 adds inclusive recurrence end dates without resetting existing
rules. End-only edits preserve occurrence IDs/completions. Confirmed completion
acknowledges the matching alert atomically; other occurrences are unaffected.

Migration 005 adds conversations.task_context with an empty default, preserving
existing chat, composer text and pending proposals. It stores one bounded task
question/history, draft fields and exact pending ID/revision independently of
ordinary chat. Context updates do not create tasks or pending actions. A reviewed
correction uses the existing revision-checked revise operation and must be
confirmed again. Starting a separate request clears context only. A local save
failure preserves the previous context; no generated correction is applied.

Tests use disposable databases and a loopback model fixture. They cover migration
reopen, foreign keys, restart recovery, proposal edits, stale revisions, duplicate
confirmation, rollback with no audit leakage, soft removal, chat save failures,
retry-save without duplicate inference and the existing pet/chat behavior.

Ponytail keeps persistence in the existing database service. Graphify's source
map is refreshed in `src/graphify-out/`; it maps code relationships, not all asset
or business-document semantics. No cloud graph backend is required.
