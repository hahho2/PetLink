---
version: beta
name: PetLink
description: Monochrome native productivity tools with expressive colored desktop pets.
colors:
  primary: "#F5F5F5"
  background: "#0B0B0B"
  surface: "#151515"
  elevated: "#1C1C1C"
  field: "#202020"
  text: "#F5F5F5"
  muted: "#A3A3A3"
  subtle: "#858585"
  border: "#303030"
  error: "#F5F5F5"
  success: "#F5F5F5"
  warning: "#F5F5F5"
typography:
  sans:
    fontFamily: "Segoe UI, sans-serif"
rounded:
  control: "8px"
  panel: "12px"
spacing:
  panel: "24px"
  gap: "12px"
---

# PetLink desktop design

## Overview

PetLink is an Operate interface for personal study and work. Chat is the quiet
work notebook; the colored character supplies personality. The user's monochrome
brief replaces the earlier navy/lavender identity. Native PySide6 only. English
interface, Unicode input, Windows typography and keyboard conventions.

## Colors

`src/petlink/ui_theme.py:COLORS` is the canonical runtime source. `stylesheet()`
styles chat, tasks, model settings, voice setup, notifications, menus, tooltips
and pet controls. All surrounding UI is neutral grayscale. Colored sprite art
and character animation overlays remain independent. Notification icons use
monochrome character-specific shapes. State meaning uses words: Connected,
Configured, Listening, Transcribing, Error, Pending and Done, rather than color.
No gradients, glows or ornamental shadows. Dark theme is the implemented default;
a light-theme toggle is not shipped.

## Typography

Segoe UI, 14px body, 20px window headings, 18px task titles, 12px message labels.
Model and user text remain plain, selectable and wrapped. Native IME composition
is preserved. No model-generated HTML or remote images are rendered.

## Layout

Compact avatar/name and Hide row, then local/cloud status, Settings and Pending
Tasks. Model ID is available in Settings and the status tooltip. Cloud disclosure
remains visible. A single transcript scroller owns overflow; composer and actions
stay reachable. User messages align right on elevated gray; assistant messages
align left without a heavy background. Message measure adapts to viewport width.
24px panels and 12px groups use the existing native layout. Narrow chat is tested
at 380px; tasks at 390px. Window geometry persists through QSettings.

## Elevation & Depth

Tonal surfaces and restrained borders establish hierarchy. Native title bars own
window movement. Menus and tooltips use the same neutral tokens.

## Shapes

8px input/control corners and 12–14px message/task corners. White primary actions
carry dark text; other actions remain quiet until hover or keyboard focus.

## Components

ChatWindow owns conversation, input and worker lifecycle. MessageBubble provides
Copy and accessible plain text. Feedback shows concise errors and expandable
original details, retaining Retry and unsent input. Composer supports Enter and
Shift+Enter. Mic capture is explicit; Stop mic and Transcribing state remain
visible. Transcripts append to the draft and never send automatically.

ModelSettings owns validated local endpoints, installed-model discovery, service
tests, opt-in hosted inference and Windows Credential Manager. Advanced thinking
options stay collapsed. Background jobs reject stale results. Cancel/X/Escape
never apply edited settings or reset conversation. Connection success is reported
only after a real successful check/request.

TaskWindow owns Tasks/Pending/Occurrences. Saved-task navigation offers All,
Today, Upcoming, Recurring and Completed. Database.tasks filters before pagination;
Today/Upcoming refer to the saved parent due/start date, while individual recurring
dates and their completion remain in Occurrences. Lists retain selection by ID
on refresh and load in batches. Empty views explain how to continue. Relevant
actions appear per tab; confirmation gets a full-width row on narrow windows.

TaskDraftCard shows the exact proposal with Edit, Confirm, Save as Pending and
Cancel. Draft corrections reuse the current pending revision. TaskEditor supplies
labeled native fields and validation. Draft/review/explicit-confirmation remains
the only mutation path. Confirmation checks task versions and proposal revisions
and commits atomically. Removal retains audit history. Completing an occurrence
leaves its recurring parent active. Closing dialogs never erases saved proposals.

PetControls owns monochrome pencil/microphone/bell controls. Original assets,
independent animation, drag, blink and reduced-motion behavior remain intact.
CompanionController parks the pet beside chat or in a reserved rail and hides it
for modal dialogs. Tray actions reuse the same navigation and exit handlers.
NotificationWindow exposes full statements and explicit acknowledgement; opening
an inbox does not clear unread alerts. Speech paths and models stay machine-local.

## Do's and Don'ts

- Keep inference, transcription and reminder work off the GUI thread.
- Keep model-generated task text untrusted; validate all structured proposals.
- Never treat a chat answer as authorization to schedule or mutate tasks.
- Preserve editable text on failures; show honest errors and recovery actions.
- Use native controls for selection, date text entry and keyboard focus.
- Respect reduced motion; do not add decorative panel animations.
- Do not recolor pet sprite assets as part of the monochrome UI.
- Keep local data, credentials, previews, downloaded models and environments out of Git.
