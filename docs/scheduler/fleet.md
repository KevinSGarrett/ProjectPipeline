# Three-host fleet placement

Cycle 19 extends the existing scheduler resource model. Local `machine:local`
CPU and process claims remain the default. When a remote machine is selected,
those physical claims are rewritten onto that host's registered pools.

## Admission

- Unregistered physical pools are denied.
- Stale, offline, drained, quarantined, or enrollment-pending hosts cannot
  receive new work.
- Fermi-class GPUs (Quadro 6000, compute capability 2.0) are ineligible for
  modern CUDA dispatch.
- AVX2 wheels may be denied on older Xeon ISA.

## Enrollment

`WIN-EVSH1DN8H5O` remains `ENROLLMENT_PENDING` until Windows OpenSSH is enabled
on the Tailscale interface and the existing operator principal is authorized.
Tailscale SSH-server is not the Windows transport.

## Operations

- `python -m project_pipeline.cli scheduler fleet`
- `python -m project_pipeline.cli scheduler place`
- Authenticated Command Center `GET /api/v1/command-center/fleet` plus
  drain/resume POSTs.
