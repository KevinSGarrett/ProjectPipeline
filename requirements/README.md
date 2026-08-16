# Dependency Artifacts

`pyproject.toml` is the declaration authority. `environment.lock.json` is the exact, locally verified lock for dependency groups that are active in the current executable foundation. It records package versions, dependency closure, and hashes of installed distribution metadata.

`runtime.txt` and `development.txt` are deterministic pin exports generated from that observed lock. `quality-tools.txt` records exact tool intentions whose live installation and transitive resolution require package-index access.

A resolver-generated `uv.lock` remains a required release prerequisite. Its current state is recorded as `BLOCKED_EXTERNAL` in `config/dependency_policy.json`; the repository does not substitute a handwritten file for a resolver-produced lock.
