# Controlled Bootstrap

Bootstrap translates a compilation and gap report into a deterministic sequence of bounded file-system actions.

## Default behavior

Bootstrap defaults to dry-run. The plan records every proposed path, action type, content hash, prerequisite, and rollback behavior. Applying a plan requires explicit confirmation.

## Existing-project protection

For an existing repository, bootstrap may create missing Project Pipeline authority files only when the target path does not already exist. It never:

- overwrites or edits a pre-existing file;
- deletes, renames, reformats, or relocates repository content;
- executes instructions, hooks, package scripts, build tools, or tests;
- creates remote issues, branches, pull requests, cloud resources, or purchases;
- advances the project into autonomous execution.

## Idempotency and rollback

Each plan has a stable identity derived from the compilation and proposed semantics. A repeated apply returns the original receipt when the plan has already been completed. File creation uses exclusive writes. If an action fails, rollback removes only files and directories created by that attempt and leaves all pre-existing content untouched.

Bootstrap receipts can be persisted for reconciliation and audit. A receipt distinguishes dry-run, applied, replayed, rolled-back, and failed outcomes without treating a mock or local action as external completion evidence.
