---
version: alpha
name: PetLink
description: A quiet desktop work companion with expressive pastel characters and a restrained chat panel.
colors:
  primary: "#B7A9EB"
  background: "#161923"
  surface: "#222735"
  field: "#11151D"
  text: "#F0F2F7"
  muted: "#A9B1C4"
  border: "#414A5D"
  error: "#FFA8B8"
  success: "#92D4B1"
  warning: "#E7C17B"
typography:
  sans:
    fontFamily: "Segoe UI, sans-serif"
rounded:
  control: "8px"
  panel: "10px"
spacing:
  panel: "24px"
  gap: "12px"
components:
  button:
    rounded: "control"
    backgroundColor: "primary"
    textColor: "field"
  message:
    rounded: "panel"
    backgroundColor: "surface"
    textColor: "text"
  status:
    textColor: "muted"
  input:
    backgroundColor: "field"
    textColor: "text"
    rounded: "control"
  secondary-button:
    backgroundColor: "border"
    textColor: "text"
---

# PetLink desktop design

## Overview

The character is an expressive desk companion; chat is its quiet work notebook.
The source brief is PETLINK_PROJECT_CONTEXT.md and the supplied chibi reference.
Audience: Windows users discussing study and work. English UI with Unicode input;
no Japan-market assumptions. Product register; the pet supplies the visual signature.

## Colors

The canonical runtime palette is `src/petlink/ui_theme.py:COLORS`; this document
mirrors it. `stylesheet()` maps palette roles into shared Qt widget styles used
by ChatWindow and its descendants. Primary lavender is reserved for Send, focus,
and speaker labels. Error rose carries text, not just color. Painted pet palettes
remain character-specific. One dark panel theme is implemented.

## Typography

Segoe UI is the Windows interface family. Body and controls use 14px, heading
24px, speaker labels 12px. Qt handles Unicode shaping and platform font fallback.
Messages wrap and remain selectable. Use plain text for model/user content.

## Layout

Chat starts at 560 by 740 with a requested 360 by 560 minimum; the native layout
raises the minimum height as needed to fit connection and drafting controls.
A single transcript scroller
owns overflow; connection, status, input and actions remain reachable. The pet
and chat are separate windows. Showing chat clamps it to the pet's monitor.

## Elevation & Depth

Dark tonal surfaces and thin borders establish hierarchy without extra shadows.
The operating system owns title-bar controls and window movement.

## Shapes

8px controls and 10px message panels support the soft character art without
turning every control into a decorative bubble.

## Components

Native Qt controls own keyboard/focus semantics. `ui_theme.stylesheet` owns
buttons, inputs, focus, disabled/busy states and scrollbar styling. `ChatWindow`
owns connection validation and inline status; no toast or table capability exists.
Form errors preserve entered values. Labels are supplied by QFormLayout.
Input supports Enter, Shift+Enter and input-method composition. Buttons have
explicit hover, focus and disabled states. Default loading feedback is text.

All model calls occur off the GUI thread. Stop requests cooperative cancellation;
an outstanding socket read can take up to 120 seconds locally or 25 seconds for
hosted services to return. Overall budgets are 180 seconds locally and 90 hosted. No
new request starts until the old worker finishes. Chat history and unsent drafts
persist in local SQLite; rendering and model context remain bounded. Message
save errors preserve visible text and offer Retry save without new inference.

`TaskWindow` owns Tasks/Pending lists, summaries and confirmation. `TaskEditor`
owns a small labeled form. Native Qt combo boxes and their popup behavior are
accepted for status/priority; due dates use an explicit YYYY-MM-DD text field.
Shared styles now cover lists, tabs and combos. Lists load in batches of 100.
Create/edit/remove first produce a pending proposal. Confirm changes is the
only UI path that executes it; it checks revisions and applies all actions in
one transaction. Remove hides the task while retaining its local audit record.
The final preview explains this consequence. Dialog Cancel abandons the current
form; Review draft persists it without changing Tasks. Closing either window
does not erase previously saved drafts. No LLM-generated text executes tasks.

`PetControls` owns the pencil/microphone/bell strip and quick text input. Its
compact dark controls use the existing palette; their icon strokes are generated
with QPainter. Single click types and double click opens chat. Notification gold
is `#FFD166` with dark `#161923` text and `#FFF0C6` border. The badge means unread
alerts and does not clear merely from opening the inbox. `NotificationWindow`
shows selectable full statements and an explicit Mark selected as read action.
Voice setup uses labeled native file pickers. Recording starts only on explicit
microphone activation, is visible, and delivers a reviewable draft. No new audio
framework is introduced. Chat and task confirmation retain the shared behavior.

The task editor now includes Repeat, Remind at and Timezone, with explicit date
and time formats, at 460 by 680 initially. Its preview shows the schedule and
the consequence of marking the whole series Done. Occurrences owns per-date
completion through the same review/confirm flow. Asia/Kolkata is visibly editable.
Native Qt selects own repeat/status/priority popup behavior. Reminder work runs
off the UI thread; older notification statements remain reachable with Load more.

Repeat until and One month provide an explicit inclusive end date, shown in the
preview. Recurring parents use Active/Scheduled/Ended/Stopped series labels;
daily entries retain Pending/Overdue/Done. Completion counts are separate from
the series lifecycle. Completing an occurrence resolves its own unread alert.
An open inbox refreshes read state without losing selection, and overlapping
background checks recheck after confirmation to avoid a stale badge.

## Do's and Don'ts

Explicit general task/schedule/reminder questions are read-only local queries in
schedule_queries, answered before provider validation. Database.task_overview
applies the scope before its 20-row limit and includes only confirmed unfinished,
non-removed tasks. Pending proposal counts are separate. Dates, times, recurrence
and ended-series labels come from structured fields; nothing polls or mutates
reminders in this flow. The shared local-reply path preserves task context and
chat save/retry semantics. A failed read preserves the question and displays an
error instead of a false empty state. No cloud request occurs for the lookup.
Provider finish_reason=length reports an incomplete output-limit failure, even
when the stream contains only reasoning, rather than silently completing it.

Explicit one-off and bounded daily reminder phrases have a deterministic path in
task_interpretation.direct_reminder. Supported reminders sent with no existing
task context open the review flow directly; they never schedule themselves.
Missing daily start dates use a local clarification. A parked context instead
offers Start new, preserving the previous proposal. Unknown phrases fall back
to the selected model. The exact cake reminder with "tommorow" is covered by
tests. Dates and inclusive repeat ends are calculated in code, not guessed.
Explicit Add/Create task and Remind me requests choose task-draft mode on Send
or Retry. Common activity/date/time orders have a local grammar, with duration
text preserved in the title. Other forms use structured model interpretation;
they never enter ordinary chat or ask for optional planning details there. A
successful task draft clears stale chat Retry state. A parked draft is protected
by the existing Start new path, and unrelated unsent text survives Retry.
Local inference uses eight recent messages/8,000 characters; hosted limits remain
16/24,000. This only bounds inference context, preserving the saved transcript.

Local model settings expose an optional Skip extended thinking (Ollama) checkbox.
It persists per local connection and sends reasoning_effort=none only on opt-in;
hosted provider payloads are unaffected. Thinking-only empty answers offer this
recovery path. Local load/socket timeouts allow a cold model more time without
blocking the UI; Stop remains cooperative.
The connection label displays thinking skipped versus model-default thinking.
Model settings, provider building and metadata saves refresh the persisted local
thinking choice, so stale in-memory state cannot overwrite it on focus loss/exit.

Draft task from message is an explicit alternative to general chat Send. It uses the shared
request worker, busy/Stop/voice rules and model connection policy. Raw model JSON
is never shown as a product message or saved to chat history. One validated new
task opens the existing TaskEditor; no database mutation occurs until Review
draft, and only Confirm changes executes the pending proposal. The original
composer text remains editable. Continue task draft explicitly uses the visible
current-task context; ordinary chat leaves it parked. Start new clears that context
and keeps pending proposals. Migration 005 persists the bounded question/history,
draft fields and exact pending revision separately from ordinary chat. Corrections
merge only returned fields and reuse the original pending ID after review. Manual
review edits become the next correction's baseline; cancelling a pending correction
restores that baseline. Stale revisions block continuation. Existing saved task IDs
and mutation commands are rejected here. Cloud disclosure includes draft context.

ModelSettings uses the existing native form and dark theme. Provider selection
owns the official hosted endpoint, masked key, opt-in and optional Windows
Credential Manager persistence. Cloud disclosure stays visible in ChatWindow.
Cancel leaves the connection unchanged; saving performs no network request.
Provider changes preserve chat history and unsent input. Connection settings
are disabled while inference or voice input is active. Test connection checks
service access without transmitting conversation text. Hosted requests reject
redirects. Local mode remains loopback-only and needs no credential.

Chat's inline Server and Model fields persist their validated public details on
editingFinished, provider use, close and shutdown through the same settings writer
as ModelSettings. Empty/invalid edits preserve the previous saved connection.
The writer only allows address/model/consent/thinking option and active provider;
it never stores keys or modifies Credential Manager. Metadata validation remains
independent of session credentials. A write failure keeps fields visible and
reports an inline retry message. All tests and previews use disposable settings.

Windows tray navigation uses QSystemTrayIcon and a native keyboard-accessible
QMenu. CompanionController reuses existing window-opening and exit paths. Its
character icon and tooltip identify the current pet and unread count. Hiding is
reversible and leaves timers/data intact; it is disabled during voice capture
or transcription. No hide command is offered without an available system tray.

Expression symbols are vector overlays in the existing character palette, with
dark outlines for readability on desktop backgrounds. Ishu owns stars/blue-lilac,
Coral hearts/pink-mint, and Lola fish/paws/gold. Unread badge variants are a star,
flower and bell, retaining shared click, count and accessibility behavior.
Thinking uses a cloud; curiosity/confusion uses question marks; sleeping uses
closed eyes, z/z/Z and a translucent nose bubble. Motion uses short, bounded
character-specific celebrations. Reduced motion freezes pose/effect motion while
retaining meaningful state symbols. Controls keep their existing geometry.

- Keep character animation independent of model inference.
- Keep local connection status explicit and failures recoverable.
- Never interpret model chat text as saved tasks or executable commands.
- Never render model-provided HTML or fetch external images from chat messages.

## Chat redesign — Operate surface

The native chat now uses a compact selected-pet symbol, heading, subtitle and
configured/connected model line. Server and model field objects remain hidden
compatibility state; the permanent connection group is removed. Settings opens
AI Model Settings without leaving chat. Local installed-model refresh and service
testing run on daemon workers with stale-result guards. Advanced thinking
options are collapsed; Cancel never applies settings or resets conversation.
Connected green is only set after a real successful request.

Navy/charcoal replaces the old purple surfaces. Lavender marks focus and primary
actions, gray-blue provides structure, and pet artwork remains unchanged. Message
components have separate user/assistant surfaces, a 720px maximum readable width,
selectable plain text and an explicit Copy action. The composer owns Enter/IME
behavior and an opt-in microphone. Stop and Retry preserve their existing worker
lifecycle. Feedback offers a short summary with expandable original details.

Task drafts render a full-field card. Edit uses the existing editor; Confirm &
save is explicit, revision-checked activation; Pending stores an inactive proposal;
Cancel dismisses/discards the unconfirmed proposal. Stale cards cannot activate
a different draft. Pending Tasks exposes a count and Resume draft in its existing
window. A lightweight UI timer parks the pet beside chat or in a reserved right
rail on wide maximized layouts; modal dialogs temporarily hide the pet. Closing
chat leaves the pet alive. Chat geometry persists through QSettings.
