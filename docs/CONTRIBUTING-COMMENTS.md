# Commenting and Documentation Standards (Authoritative)

This guide distills the v6.5 Engineering Blueprint’s commenting and documentation rules.

## Code Commenting

- Explain intent, constraints, and safety. Avoid history.
- Prohibit in comments: dated notes, ticket IDs, author tags, and comment-as-changelog.
- Keep function docstrings concise and focused on behavior/contract.
- Update or remove nearby comments/docstrings when logic changes in the same changeset.
- Link to internal docs (e.g., titles in `docs/` or ADRs) when helpful.

Examples:
- Good: "Bounded retry: at most 2 clicks with menu verification after each."
- Bad: "Changed this on 2025-08-20 because PR #123 failed."

## Documentation Expectations

- Update relevant docs on behavioral or architectural changes:
  - `docs/blueprint.md` for architecture/process updates (rare; treat as authoritative).
  - `docs/*.md` feature docs for user-facing workflows and troubleshooting.
  - `docs/adr/*.md` for architectural decisions (rationale, alternatives, consequences, rollback).
- Keep changesets small and focused; include tests when behavior changes.

## ADR Authoring Checklist

- Title and incremented ADR number (e.g., ADR-0011-something-important). 
- Status (Proposed/Accepted/Deprecated/Superseded).
- Date and deciders.
- Context, Decision, Rationale, Alternatives, Consequences.
- Migration and Rollback when applicable.
- References to blueprint or related docs.

## Observability

- Add or preserve structured logs with context IDs (e.g., attempt numbers, timing, thresholds).
- On uncertainty, fail closed and log the reason.

## Windows Constraints

- Respect focus/integrity constraints; never inject into game memory.
- Ensure no blocking on GUI thread; heavy work in background threads.
