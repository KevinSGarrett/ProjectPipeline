# Target Architecture

This directory is the machine-readable and diagram-as-code representation of Project Pipeline's target component model.

- `component_catalog.json` defines authority, responsibilities, interfaces, dependencies, source basis, and implementation state.
- `state_ownership.json`, `trust_boundaries.json`, and `data_flows.json` define operational ownership and risk boundaries.
- `technology_stack.json` records selected, fallback, optional, and deferred technologies with ADR and upstream provenance.
- `decision_map.json` maps accepted decisions to requirements, components, and technologies.
- `deployment_profiles.json` separates local core, optional hybrid AWS, and offline portable operation.
- `diagrams/` contains Mermaid architecture-as-code views.

These records establish verified architecture and technology decisions. They do not claim that every runtime component or external integration has been implemented.

The Project Intake Compiler is partially implemented with safe local discovery, deterministic compilation, gap analysis, controlled bootstrap, and persistence boundaries. Acceptance into executable project-control state remains outside its authority.
