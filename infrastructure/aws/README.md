# Optional AWS Cloud Spine

This Terraform blueprint is intentionally disabled by default. It models only the support-plane resources selected for witness, durable queueing, recovery storage, observability, and budget control. It does not move the Project Pipeline deterministic control plane to AWS and it does not create cloud workers or a DR director by default.

Activation requires explicit operator authorization, least-privilege IAM review, budget approval, environment isolation, and recovery validation. No cloud resource has been created by the repository build process.
