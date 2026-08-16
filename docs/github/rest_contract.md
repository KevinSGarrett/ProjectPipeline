# GitHub REST Contract Baseline

The GitHub adapter is implemented against GitHub's versioned REST API using `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2026-03-10`.

The bounded provider contract uses these endpoint families:

- repository metadata: `GET /repos/{owner}/{repo}`;
- branches: `GET /repos/{owner}/{repo}/branches`;
- branch protection: `GET /repos/{owner}/{repo}/branches/{branch}/protection`;
- pull request: `GET /repos/{owner}/{repo}/pulls/{pull_number}`;
- pull-request reviews: `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews`;
- check runs: `GET /repos/{owner}/{repo}/commits/{ref}/check-runs`;
- create branch reference: `POST /repos/{owner}/{repo}/git/refs`;
- create/update pull request: `POST/PATCH /repos/{owner}/{repo}/pulls...`;
- merge: `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`, including the evaluated head SHA;
- delete branch reference: `DELETE /repos/{owner}/{repo}/git/refs/heads/{branch}`.

Project Pipeline does not assume that API availability implies permission. Live reads and writes remain subject to credential, repository, policy, and explicit authorization checks. Mutations are not blindly retried after ambiguous transport failure.
