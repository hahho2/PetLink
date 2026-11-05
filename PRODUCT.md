# PetLink

PetLink is a Windows-first native PySide6 productivity companion for individual
study and work. Original Ishu, Coral and Lola characters remain independent,
draggable desktop pets. Chat, task review and opt-in voice are its main workflows.

The chat surface is an Operate interface: readable conversations and actionable
drafts take priority over server configuration. Local models are the default;
hosted inference requires explicit opt-in. Credentials belong in Windows
Credential Manager. Microphone activation is always explicit.

Task data and conversations live in SQLite. Generated suggestions never execute
on their own. Users inspect full task fields and explicitly confirm activation;
pending drafts remain inactive. Saved-task questions use structured local data.
Model inference and speech work must not block the GUI thread. Screenshots and
automatic activity tracking are outside this redesign.

Source: PETLINK_PROJECT_CONTEXT.md and the user-supplied premium UI/UX brief.
