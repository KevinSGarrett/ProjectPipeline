# Local Jira mirror

The local mirror is a structured work-management database, not a set of narrative ticket files. Each issue retains a stable `PP-*` identity, parentage, requirements, canonical source ranges, exact plan sections and lines, dependencies, blockers, relationships, artifacts, acceptance criteria, verification methods, Definition of Done, test and evidence expectations, risk, security and observability impact, recovery considerations, state, and completion evidence.

The typed loader rejects:

- identifier and issue-type disagreement;
- non-epics without a parent or epics with a parent;
- missing or invalid parents;
- dangling relationships and dependencies;
- parent or dependency cycles;
- duplicate remote mappings;
- duplicate acceptance IDs;
- completed items without completion evidence;
- stale graph nodes and counts.

`jira-rebuild` regenerates indexes and the graph from authoritative issue records. `jira validate` adds typed semantic validation. `jira export` creates a deterministic portable bundle. An imported bundle is diffed and reviewed; it does not rewrite source-controlled issue files.
