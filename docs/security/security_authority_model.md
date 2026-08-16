# Security authority model

Project Pipeline keeps security authority deterministic and internal. Human, agent, service, and adapter identities are distinct principals. Roles provide bounded baseline capabilities; temporary grants add narrowly scoped capability, project, environment, operation, target, and expiry constraints. High-impact actions require a separate authorized approver and a proposer cannot approve its own action.

OPA and Conftest are conformance/config-policy backends. Their output can supply policy evidence, but they do not replace the canonical `SecurityPolicyEngine`. Root-of-trust configuration contains references and procedures, never private key material.

Security decisions are evidence-bearing state. A denied or approval-required result cannot be overridden by an advisory model.
