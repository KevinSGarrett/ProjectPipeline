# Visible Control-Plane Contract

The implementation must expose health, job creation, job status, artifact metadata, audit history, retry, cancel, webhook receipt, and policy-inspection interfaces. Job creation must require an idempotency key and return an artifact reference by default rather than the full converted document. The untrusted fixture must never control agents, Jira, GitHub, policy, or external writes.
