# OpenClaw Coding Kit REQUIREMENTS

## Current Baseline

- Repo must stay portable and self-contained for local-first reuse.
- README, INSTALL, examples, and tests must describe commands that actually work in a fresh clone.
- PM reviewed flow must behave correctly for `run-reviewed`, `review`, `rerun`, `complete`, `monitor-status`, and `monitor-stop`.
- Continuation guard coverage must remain valid for `acp`, `codex-cli`, and `openclaw`.
- Repo-local smoke path must not depend on author-machine-only scripts or paths.
