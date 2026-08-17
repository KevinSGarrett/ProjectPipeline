# PLAN-SEC-002 — Security Authority, Secrets, and Supply Chain [Status: ACTIVE]

## PLAN-SEC-002:SEC-01 Upstream security activation
Review the mapped security portfolio before implementation. Reuse existing Docker MCP Gateway, Gitleaks, OSV-Scanner, Cosign, and Zizmor boundaries; add bounded Trivy, OPA, Conftest, SOPS, age, OpenBao, Scorecard, and Harden-Runner integration patterns.

## PLAN-SEC-002:SEC-02 Identity, roles, and root of trust
Define separate human, agent, service, and adapter principals; bounded roles and temporary grants; suspension and revocation; bootstrap/root-of-trust references and recovery/rotation procedures.

## PLAN-SEC-002:SEC-03 Independent approval and deterministic policy
High-impact merge, deploy, spend, external-model, secret, instruction, policy, completion, and emergency actions require deterministic authorization and independent approval. Advisory models cannot override policy.

## PLAN-SEC-002:SEC-04 Data classification and egress
Classify data, deny secret/local-only egress, require approval for confidential egress, and constrain untrusted instructions to data-only semantics.

## PLAN-SEC-002:SEC-05 Secrets Broker
Represent credentials as scoped references and time-bounded leases. Persist metadata only; plaintext exists only during explicit runtime materialization. Support local ENV/FILE plus optional SOPS, age, and OpenBao backends.

## PLAN-SEC-002:SEC-06 Supply-chain scanning and normalization
Normalize external scanner results into Project Pipeline findings. Cover secrets, vulnerabilities, misconfiguration, license, provenance, integrity, CI permissions, action pinning, SBOM, and signatures.

## PLAN-SEC-002:SEC-07 SBOM, integrity, provenance, and signing
Generate an internal SBOM, hash artifacts, bind release provenance to source and verification evidence, and retain Cosign as the optional signing/verification boundary.

## PLAN-SEC-002:SEC-08 CI hardening and least privilege
Require explicit workflow permissions and immutable third-party action references. Add Harden-Runner audit mode to every CI job and keep CI verification non-authoritative until evidence is ingested.

## PLAN-SEC-002:SEC-09 Safe self-modification
Changes to control, security, assurance, migrations, configuration, or provenance require independent review, rollback material, and security verification.

## PLAN-SEC-002:SEC-10 Persistence, schemas, CLI, and validation
Persist security metadata using PPDB-0014, export typed schemas, provide approval-gated CLI operations, add deterministic simulations/tests, and fail repository validation if the security upstream gate or foundation drifts.
