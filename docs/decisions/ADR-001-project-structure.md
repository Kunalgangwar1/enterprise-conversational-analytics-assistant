# ADR-001: Monorepo project structure

- Status: Accepted
- Date: 2026-09-13

## Context

The planned product has a Python API and a React/TypeScript user interface that will evolve
together. The reconstruction should remain approachable for learning while leaving room for
independent backend and frontend tooling.

## Decision

Use one monorepo with top-level `backend` and `frontend` directories. Keep shared project
documentation in `docs` and introduce repository-level scripts only when a concrete need arises.
Each application owns its dependencies and development commands.

## Alternatives considered

- Separate backend and frontend repositories: stronger isolation, but more coordination overhead.
- One undivided source directory: initially small, but mixes language tooling and responsibilities.

## Consequences

Cross-application changes and documentation remain easy to review together. Tooling boundaries
must be kept explicit, and CI may later need path-specific jobs as the applications grow.
