# PetLink workflow

- Read README.md and DESIGN.md before implementation. If a local
  PETLINK_PROJECT_CONTEXT.md exists, read it as additional project context.
- Use the Ponytail skill for every coding task: inspect the real flow, reuse existing
  code, keep the change minimal, and verify it.
- Use the Graphify skill for every coding task: consult the existing graph before
  editing and refresh the source graph after architectural changes. Treat graph
  omissions and stale nodes as coverage limits, not proof that code is absent.
- Use local deterministic source extraction when appropriate. Never require a
  cloud key merely to map Python source. Exclude generated assets and environments.
- Preserve the draft/review/explicit-confirmation boundary for task mutations.
