# Contributing

## Branching

`main` is production. Direct pushes, force-pushes, and deletion are blocked by the [Merge Protection](https://github.com/d95tan/bb_bot/rules/12239273) ruleset. Changes land through a pull request with at least one approving review. Merge, squash, and rebase are all allowed.

The same ruleset also names `develop`. Collate work there, then open a PR from `develop` into `main` when you are ready to publish.

Day-to-day workflow:

1. Branch off `develop` (`feat/…`, `fix/…`, or `docs/…`).
2. Open a pull request into `develop`. Do not bump `pyproject.toml` on feature PRs.
3. When the set of changes on `develop` is ready to release, bump `version` in `pyproject.toml` on `develop` (human decision: major, minor, or patch).
4. Open a pull request from `develop` into `main`.
5. Wait for CI and one review, then merge. The Docker image publishes to GHCR (`latest` plus the version in `pyproject.toml`).

A push to `main` fails if that image tag already exists in GHCR, so the bump on `develop` must be a version that has not been published yet. Version bumps stay a human process; there is no auto-bump.

### Branches

| Branch | Role |
| ------ | ---- |
| `main` | Production. PR required. Every merge publishes GHCR. |
| `develop` | Integration. Same merge protection as `main`. Images are **not** published from it. |
| `feat/` / `fix/` / `docs/` | Short-lived work branches. Unprotected. PR into `develop`. |
| `master` | Leftover alias in the publish workflow only. Default branch is `main`. |
| `v*.*.*` tags | Extra GHCR publish trigger. Version on `main` already comes from `pyproject.toml`. |

### CI

**[PR Validation](.github/workflows/pr-validation.yml)** runs on pull requests to `main` or `develop`: flake8, pytest, import check, and a Docker build (no push).

**[Docker Build and Publish](.github/workflows/docker-publish.yml)**:

- Pull requests to `main`: build the image, do not push.
- Push to `main`: push `latest`, a branch tag, and the `pyproject.toml` version.
- `v*.*.*` tags and **workflow_dispatch** also publish.
- Pull requests to `develop` do not run this workflow.

The ruleset does not require status checks, so a PR can merge with a review even if CI is red. Treat green PR Validation as required in practice.

TrueNAS pulls `ghcr.io/d95tan/bb_bot:latest`. See [DEPLOYMENT.md](DEPLOYMENT.md).
