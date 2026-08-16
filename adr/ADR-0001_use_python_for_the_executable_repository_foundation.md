# ADR-0001 — Use Python for the executable repository foundation

- **Status:** `ACCEPTED`
- **Source basis:** `GOV-001:L001319-L001360`
- **Date:** `2026-08-14`


## Context

The project needs immediately executable, portable validation and packaging on Windows and Linux without committing the full runtime stack prematurely.

## Decision

Use Python 3.11 or newer and the standard library for bootstrap manifests, repository maps, archive tooling, registries, and validators. This decision does not force every later subsystem to use Python.

## Alternatives considered

- TypeScript-first control core
- Rust-first control core
- Polyglot bootstrap

## Consequences

The foundation runs with minimal setup and is testable in the current environment. Major runtime language choices remain subject to their own decisions.

## Review trigger

Revisit when measured project constraints, security findings, or operational evidence invalidate this decision.
