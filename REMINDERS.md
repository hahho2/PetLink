# Reminders and recurring tasks

Double-click the pet → Tasks & Pending → New task. Enter a due/start date,
Repeat (none/daily/weekly), optional HH:MM reminder time, and timezone.
Asia/Kolkata is visibly prefilled and editable. Review draft → Confirm changes.
Unconfirmed proposals do not schedule anything.

One-off reminders require a date and time. Repeats follow the local calendar,
anchored to the start date; a blank repeat time means midnight, shown in preview.
Plain date-only tasks retain their existing local-day due alert.

## Complete a date or stop the series

In Occurrences, select a date → Complete selected occurrence → review its Pending
proposal → Confirm changes. This records only that date's UTC completion and
audit event. The series remains active. To stop the entire series, edit the task,
set Status to Done, review and confirm. Remove soft-removes the task and cancels
pending occurrences. Changing a schedule cancels unfinished old-rule dates while
retaining completed history. The view shows the current schedule; old history is
retained in SQLite for later analytics.

## Timing

Checks run each minute and after confirmation in a background worker, without
AI. PetLink must be open. On reopening, missed dates catch up without automatic
completion or repeated alert delivery. Catch-up is bounded to 100 additional
dates per series/check and 1,000 new scheduled alerts/check, continuing next time.
Use Load older notifications to reach older unread statements in batches of 100.

Migration 003 preserves existing data and adds schedules, separate occurrences,
and unique notification event keys. Reminder instants and completion timestamps
are stored in UTC; dates remain local calendar dates. Python's
[zoneinfo](https://docs.python.org/3/library/zoneinfo.html) and tzdata supply
timezone rules on Windows. In a repeated clock hour the first instance is used;
skipped times move forward to the next valid local minute. Tests cover both.

These are minute-polled notifications, not hard real-time alarms. Monthly/custom
rules, end dates, snooze, sounds and background execution while the app is closed
are not implemented. The LLM still cannot execute task changes.

Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`.
Tests use simulated clocks and disposable databases. Ponytail keeps scheduling
as deterministic functions over the existing service; Graphify maps the source
in `src/graphify-out/`.
