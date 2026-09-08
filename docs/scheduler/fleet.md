# Three-host fleet placement

Cycle 19 extends the existing scheduler resource model. Local `machine:local`
CPU and process claims remain the default. When a remote machine is selected,
those physical claims are rewritten onto that host's registered pools.

## Admission

- Unregistered physical pools are denied.
- Stale, offline, drained, quarantined, or enrollment-pending hosts cannot
  receive new work.
- Declared host records are not observations. Without an observation source,
  declared capacity is stale. Command Center and CLI share `fleet_state.json`
  next to the scheduler database. Drain/resume persist there. Resume does not
  refresh `observed_at_utc`.
- Fermi-class GPUs (Quadro 6000, compute capability 2.0) are ineligible for
  modern CUDA dispatch.
- AVX2 wheels may be denied on older Xeon ISA.

`WIN-EVSH1DN8H5O` is enrolled as a bounded CPU/memory worker over Windows
OpenSSH on Tailscale `100.107.207.66` as `kines@`. Do not SSH as `kevin@`.
Tailscale SSH-server is not the Windows transport. Quadro 6000 remains
Fermi CC2.0 and is ineligible for modern CUDA. E5-2670 has AVX and not AVX2.

`COMFY-V4-CPU-01` is enrolled as a CPU-only worker over Windows OpenSSH on
Tailscale `100.77.151.3` as `-l "Windows 11"` (`comfy-v4-cpu-01\windows 11`).
Do not SSH as `kevin@` or `kines@` on this host. Intel UHD Graphics 630 is not
a discrete CUDA device. The laptop `id_ed25519` is authorized in
`C:\ProgramData\ssh\administrators_authorized_keys`. Do not copy `.env`.

## Operations

- `python -m project_pipeline.cli scheduler fleet`
- `python -m project_pipeline.cli scheduler observe --inventory-file <inventory.json>`
- `python -m project_pipeline.cli scheduler remote-run --signals-file <envelope.json> --apply --approve`
- `python -m project_pipeline.cli scheduler place` loads `fleet_admission.json`
  next to the scheduler database. Missing records, self-authored PM labels,
  wrong SHA/tree, stale hosts, and `ENROLLMENT_PENDING` deny remote placement.
  Local `machine:local` claims remain the default without that file.
- Authenticated Command Center `GET /api/v1/command-center/fleet` plus
  drain/resume POSTs.
