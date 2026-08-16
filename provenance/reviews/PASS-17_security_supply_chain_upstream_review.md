# Pass 17 Security, Identity, Policy, Secrets, and Supply-Chain Upstream Review

- **Gate:** `PASS-17-SECURITY-UPSTREAM-GATE`
- **Outcome:** `REVIEW_COMPLETE_MATERIAL_IMPLEMENTATION_ALLOWED`
- **Historical corrective rounds repeated:** `false`
- **Authority boundary:** Upstream scanners, secret stores, policy engines, and signing tools may enforce bounded controls or produce evidence; Project Pipeline remains authoritative for identity, role/capability scope, approval separation, data classification, egress admission, action authorization, secret lease issuance, supply-chain acceptance, self-modification gates, and audit state.

## Activation decisions

| Upstream | Inspected revision | Decision | Pass 17 boundary |
|---|---|---|---|
| `UPSTREAM-007` Trivy | `d98911ea338b061f8bef0baeef85b35660013b32` | Implement external CLI adapter | Repository/image/filesystem vulnerability, secret, misconfiguration, and SBOM evidence; no automatic remediation. |
| `UPSTREAM-029` Docker MCP Gateway | `24b028f4f9aac85ce1a1057c5e8d739836e7c18d` | Reuse existing adapter | Secure tool isolation; tool availability never grants authority. |
| `UPSTREAM-035` age | `706dfc1e799a03443ae46023502bd88d4e9e324f` | Implement external CLI adapter | Recipient/identity encryption boundary for local encrypted secret material. |
| `UPSTREAM-039` SOPS | `30332a959e3d987f622702519f6b52d8ff81e1dc` | Implement external CLI adapter | Structured encrypted configuration; plaintext only materialized ephemerally after policy/lease checks. |
| `UPSTREAM-043` Gitleaks | `b58d3f102cf3a2c84cb7f923d05c25c9b1aed84b` | Reuse existing adapter | Full-redaction secret scanning. |
| `UPSTREAM-047` OSV-Scanner | `567f3ea998f1241e60ec3ca9c4cc9e30809cd820` | Reuse existing adapter | Dependency vulnerability evidence; no automatic fix. |
| `UPSTREAM-075` OpenBao | `9c17d73cb4a71690d32d7ed223f9bc8f241f9157` | Implement optional backend adapter | Optional dynamic/scoped secret backend behind Project Pipeline Secrets Broker; not required for local-core. |
| `UPSTREAM-078` Conftest | `c149d816bb161496cdb2402a720fa5e291236690` | Implement external CLI adapter | Repository/config policy evidence using Project Pipeline-authored policy inputs. |
| `UPSTREAM-079` OPA | `16b5a013726fff3c2197f98ac4afcd6d2218588a` | Implement external CLI adapter | Optional policy conformance/evaluation backend; Project Pipeline policy semantics remain canonical. |
| `UPSTREAM-081` OSSF Scorecard | `d1fab88f54636ff366076edfc5c239f97b3c8e66` | Implement external CLI adapter | Repository supply-chain posture evidence; not a release authority. |
| `UPSTREAM-094` Cosign | existing source-level review | Reuse existing verification adapter | Verify immutable signed artifacts; signing requires explicit later release authorization. |
| `UPSTREAM-100` Harden-Runner | `05e31511f85b41b11d1cf0ef85d0992719546e2c` | Adopt CI-hardening profile/pattern | Static CI policy checks for minimal permissions, pinned actions, and hardened runner posture; no remote workflow mutation. |
| `UPSTREAM-116` Zizmor | existing source-level review | Reuse existing adapter | Offline GitHub Actions security audit evidence. |

## Source-level findings applied

- Trivy has structured report/config surfaces suitable for deterministic parsing and can provide vulnerability, misconfiguration, secret, and SBOM evidence from repository/filesystem/image targets.
- OSSF Scorecard exposes named supply-chain checks; its scores/findings are evidence inputs rather than pass/fail authority by themselves.
- Harden-Runner is useful for GitHub Actions egress and runner-hardening policy; Project Pipeline uses a static profile check and does not mutate remote workflows.
- OPA provides centralized policy evaluation semantics and Conftest provides configuration-policy result categories. The canonical Project Pipeline policy decision record stays provider-neutral and deterministic.
- SOPS provides structured encrypted configuration and age provides recipient/identity encryption. Project Pipeline does not persist decrypted bytes in logs/evidence/state.
- OpenBao provides renewable/revocable leases and dynamic secret concepts. The local-core profile must remain usable without OpenBao, so it is an optional backend behind `SecretBackendPort`.
- Existing Docker MCP Gateway, Gitleaks, OSV-Scanner, Cosign, and Zizmor adapters are reused rather than rebuilt.

## Evidence sources

- `github:aquasecurity/trivy@d98911ea338b061f8bef0baeef85b35660013b32:pkg/types/report.go`
- `github:ossf/scorecard@d1fab88f54636ff366076edfc5c239f97b3c8e66:docs/checks.md`
- `github:step-security/harden-runner@05e31511f85b41b11d1cf0ef85d0992719546e2c:README.md`
- `github:open-policy-agent/opa@16b5a013726fff3c2197f98ac4afcd6d2218588a:docs/docs/policy-language.md`
- `github:open-policy-agent/conftest@c149d816bb161496cdb2402a720fa5e291236690:policy/engine.go`
- `github:getsops/sops@30332a959e3d987f622702519f6b52d8ff81e1dc:cmd/sops/main.go`
- `github:FiloSottile/age@706dfc1e799a03443ae46023502bd88d4e9e324f:age.go`
- `github:openbao/openbao@9c17d73cb4a71690d32d7ed223f9bc8f241f9157:website/content/docs/secrets/databases/index.mdx`
