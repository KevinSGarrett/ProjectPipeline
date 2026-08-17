# Optional AWS Cloud Spine

This Terraform blueprint is intentionally disabled by default. It models only the support-plane resources selected for witness, durable queueing, recovery storage, observability, and budget control. It does not move the Project Pipeline deterministic control plane to AWS and it does not create cloud workers or a DR director by default.

Activation requires explicit operator authorization, least-privilege IAM review, budget approval, environment isolation, and recovery validation. No cloud resource has been created by the repository build process.

## Safety contract

- `enable_cloud_spine=false` is the default and must remain fail-closed.
- `terraform apply` and `terraform destroy` require explicit authorization outside normal local development.
- Plan/apply are separated; a reviewed plan with locking is required before any live apply.
- Backend state details are not embedded in source. Provide bucket/key/lock settings via explicit approved `terraform init -backend-config` values.
- Mock/local evidence is not equivalent to live cloud evidence and must be tracked separately.
