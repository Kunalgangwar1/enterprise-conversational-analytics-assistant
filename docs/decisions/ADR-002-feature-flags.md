# ADR-002: Local validated feature flags

- Status: Accepted
- Date: 2026-09-13

## Context

The final system has multiple AI strategies and specialist tools that need controlled rollout.

## Decision

Use a version-controlled local YAML file validated by Pydantic as the initial feature flag source.
The parsed configuration is cached for the process lifetime, so changes require an application
restart.

## Alternatives considered

- Hardcoded Python constants
- An environment variable for every individual flag
- Database-backed flags
- A remote service such as LaunchDarkly

## Consequences

The configuration is simple, auditable, and easy to use locally. It is not yet suitable for
dynamic or per-user production rollout, and a restart is required to pick up changes.
