---
version: alpha
name: PetLink
description: A quiet desktop work companion with expressive pastel characters and a restrained chat panel.
colors:
  primary: "#C9B4F4"
  background: "#242333"
  surface: "#302E43"
  field: "#1D1C2B"
  text: "#F4EFFA"
  muted: "#C2BBD3"
  border: "#56516D"
  error: "#FFC0CC"
typography:
  sans:
    fontFamily: "Segoe UI, sans-serif"
rounded:
  control: "8px"
  panel: "10px"
spacing:
  panel: "22px"
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

Chat starts at 460 by 700 with a 360 by 560 minimum. A single transcript scroller
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
an outstanding socket read can take up to its 25-second timeout to return. No
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
is `#FFD166` with dark `#242333` text and `#FFF0C6` border. The badge means unread
alerts and does not clear merely from opening the inbox. `NotificationWindow`
shows selectable full statements and an explicit Mark selected as read action.
Voice setup uses labeled native file pickers. Recording starts only on explicit
microphone activation, is visible, and delivers a reviewable draft. No new audio
framework is introduced. Chat and task confirmation retain the shared behavior.

The task editor now includes Repeat, Remind at and Timezone, with explicit date
and time formats, at 460 by 620 initially. Its preview shows the schedule and
the consequence of marking the whole series Done. Occurrences owns per-date
completion through the same review/confirm flow. Asia/Kolkata is visibly editable.
Native Qt selects own repeat/status/priority popup behavior. Reminder work runs
off the UI thread; older notification statements remain reachable with Load more.

## Do's and Don'ts

- Keep character animation independent of model inference.
- Keep local connection status explicit and failures recoverable.
- Never interpret model chat text as saved tasks or executable commands.
- Never render model-provided HTML or fetch external images from chat messages.
