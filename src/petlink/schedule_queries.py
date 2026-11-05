"""Small, explicit read-only task questions answered from local records."""
import re
from .scheduling import task_status_label


def task_query(text):
    query = " ".join(text.lower().strip().rstrip("?.!").split())
    query = re.sub(r"^please | please$", "", query)
    noun = r"(?P<kind>schedules?|tasks?|reminders?)"
    patterns = (
        r"(?:are there|do i have) (?:any )?" + noun + r"(?: for me)?",
        r"(?:show|list)(?: me)? (?:my |the )?" + noun,
        r"what (?:is|are)(?: on)? my " + noun,
        r"what's on my " + noun,
        r"what " + noun + r" do i have",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, query)
        if match:
            return match["kind"].rstrip("s") + "s"
    return None


def overview_reply(database, kind):
    if database is None:
        return "Local task storage is not available in this preview. Open the full PetLink app to check your saved tasks."
    overview = database.task_overview(kind)
    records = overview["records"]
    if not records:
        reply = f"You have no confirmed, unfinished {kind} saved in PetLink."
    else:
        lines = [f"Your saved {kind} (confirmed, unfinished):"]
        for task in records:
            schedule = task["schedule"]
            detail = "No due date" if not task["due_date"] else f"Due/start: {task['due_date']}"
            if schedule["frequency"] != "none":
                detail += f" · {schedule['frequency'].title()} at {schedule['reminder_time'] or '00:00'} · {schedule['timezone']}"
                detail += f" · Ends: {schedule.get('end_date') or 'No end date'}"
            elif schedule["reminder_time"]:
                detail += f" · Reminder: {schedule['reminder_time']} · {schedule['timezone']}"
            elif task["due_date"]:
                detail += " · No timed reminder"
            lines.append(f"• {task['title']}\n  {task_status_label(task)} · {detail}")
        if overview["more"]:
            lines.append("Showing the first 20. Open Tasks & Pending to view more.")
        reply = "\n\n".join(lines)
    if overview["pending"]:
        reply += f"\n\nPending drafts awaiting confirmation: {overview['pending']}. These are not active tasks or reminders."
    reply += "\n\nOpen Tasks & Pending to review records. New reminders become active only after Review draft and Confirm changes."
    return reply
