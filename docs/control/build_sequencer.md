# Build Sequencer Operator Notes

Use `project-pipeline control evaluate` or `control sequence` to inspect deterministic ready work. The output includes graph identity, ready/active/blocked counts, ordered candidates, critical-path/slack information, scope findings, and completion projection.

The sequencer is not the parallel lane scheduler. Conflict graphs, machine/GPU/port/environment leases, admission control, and backpressure are separate resource-governance responsibilities.

A graph error, unknown dependency, cycle, or invalid accepted state is a hard sequencing failure. Correct the authoritative source rather than bypassing the validator.
