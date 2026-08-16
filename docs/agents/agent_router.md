# Agent Router and Provider Abstraction

Project Pipeline routes by capability, never by vendor name. Provider/model/tool-specific protocol details are confined to adapters. The Control Kernel, scheduler, policy, budget, and completion systems retain their own authority.

Committed external providers are disabled until credentials and representative qualification exist. The deterministic mock provider exists only for local contract testing and cannot create live-verification evidence.
