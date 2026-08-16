# Windows Service Packaging

`ProjectPipelineService.xml` is the WinSW service definition for the bounded Command Center API host. The WinSW executable is **not vendored** in this repository. A reviewed WinSW release must be obtained separately, its digest and MIT notice recorded, and Windows installation must run through `scripts/windows/install.ps1`.

The current Pass 24 build environment is not Windows and has no WinSW/PowerShell runtime, so this directory is **source implemented but runtime not qualified**. The service wrapper is supervision only; it does not own canonical state, policy, completion, or recovery authority.

The authentication token is supplied only at runtime through the service environment/secret-management boundary. No credential value belongs in the XML or install scripts.
