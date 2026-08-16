
# Create a Release Archive

1. Validate the repository and tests.
2. Generate the repository map and manifest.
3. Re-run validation because generated files are part of the release state.
4. Create the archive with the CLI `archive` command.
5. Verify archive integrity and expected root with the `verify-archive` command.
6. Record the archive digest and verification output in the evidence ledger.
