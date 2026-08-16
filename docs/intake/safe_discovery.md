# Safe Repository Discovery

Repository discovery creates a deterministic inventory without trusting or executing repository content.

## Boundary rules

- The selected root must exist and be a directory.
- Every discovered path is normalized relative to the selected root.
- Traversal never follows symbolic links or junction-like indirections.
- A symlink target may be recorded as text, but target content is not read through the link.
- Nested repositories are reported and are excluded unless the caller explicitly enables bounded nested-repository discovery.
- Version-control internals, caches, generated build output, and Project Pipeline local runtime state are excluded by policy.
- File, byte, and depth limits fail closed rather than silently returning an incomplete inventory.

## Discovery surfaces

The scanner identifies, without executing:

- repository identity and configured remote origin where safely readable;
- instruction and policy files;
- plan, Jira, requirement, architecture, evidence, CI, build, deployment, and test surfaces;
- language and framework signals;
- source symbols and import/dependency references using bounded lexical or AST analysis;
- test-to-source naming relationships;
- ownership files and package manifests;
- possible secret-reference names without preserving secret values.

Discovery records semantic hashes so equivalent repository content produces equivalent compilation identities regardless of absolute host path.

## Explicit exclusions

The scanner does not run package managers, interpreters, build systems, hooks, containers, test commands, or files found in the repository. Live GitHub, Jira, cloud, and provider inspection is outside this local intake boundary.
