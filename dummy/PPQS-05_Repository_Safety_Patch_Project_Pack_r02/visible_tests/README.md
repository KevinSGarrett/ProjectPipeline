# Visible Validation

After acquiring the exact baseline commit, the candidate must demonstrate:

- `go test ./internal/repository -count=1`
- `go test ./internal/repository/... -count=1`
- `go build ./...`
- `gofmt -d` produces no diff for changed Go files
- a new regression test fails on the seed baseline because of the unsafe behavior and passes after the repair

The private evaluator adds adversarial short-length cases and checks that valid metadata behavior and cryptographic verification are unchanged.
