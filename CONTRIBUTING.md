# Contributing

## Branching

There is **no `staging` git branch**. Staging is a TrueNAS environment that tracks `develop`. Git stays:

`feat/*` → PR → `develop` (deploys staging) → PR → `main` (deploys production)

`main` and `develop` are protected by three [rulesets](https://github.com/d95tan/bb_bot/rules). Direct pushes, force-pushes, and deletion are blocked. A pull request is required; required approvals are **0** (solo: GitHub will not let you approve your own PR). Merge is blocked until **PR Validation** checks `Lint`, `Test`, and `Build Check` are green.

Open PRs to `main` **only from `develop`** (not from `feat/*`). GitHub does not always enforce the source branch; treat that as a hard convention.

### Rulesets

| Ruleset | Branches | What it does |
| ------- | -------- | ------------ |
| [protect-general](https://github.com/d95tan/bb_bot/rules/24634932) | `main`, `develop` | Block deletions and force-pushes. No bypass. |
| [protect-develop](https://github.com/d95tan/bb_bot/rules/24634933) | `develop` | Require a PR. Require `Lint`, `Test`, `Build Check`. Admin can bypass. |
| [protect-main](https://github.com/d95tan/bb_bot/rules/24634973) | `main` | Same as protect-develop. |

Do not add overlapping rulesets (the old Merge Protection / main-1 pair stacked with these).

Day-to-day workflow:

1. Branch off `develop` (`feat/…`, `fix/…`, or `docs/…`).
2. Open a pull request into `develop`. Do not bump `pyproject.toml` on feature PRs.
3. Merge to `develop` republishes GHCR tag `staging` (same name, new image). TrueNAS staging pulls `ghcr.io/d95tan/bb_bot:staging`.
4. When staging looks good, bump `version` in `pyproject.toml` on `develop` (human decision: major, minor, or patch).
5. Open a pull request from `develop` into `main`.
6. Wait for the required checks, then merge. Production publishes `latest` plus the immutable `pyproject.toml` version (e.g. `0.4.1`). Pin TrueNAS production to that version tag, not `latest`.

A push to `main` fails if that version tag already exists in GHCR, so the bump on `develop` must be a version that has not been published yet. Version bumps stay a human process; there is no auto-bump. The `staging` tag is overwritten on purpose.

### Branches

| Branch | Role |
| ------ | ---- |
| `main` | Production. PR required, from `develop` only. Publishes `latest` + version tag. |
| `develop` | Integration + staging. Same merge protection as `main`. Publishes floating `staging` tag. |
| `feat/` / `fix/` / `docs/` | Short-lived work branches. Unprotected. PR into `develop`. |
| `master` | Leftover alias in the publish workflow only. Default branch is `main`. |
| `v*.*.*` tags | Extra GHCR publish trigger. Version on `main` already comes from `pyproject.toml`. |

### Environments

| Env | Where | Image | Calendar |
| --- | ----- | ----- | -------- |
| dev | Laptop | `docker compose build` | Optional / dry-run |
| staging | TrueNAS | `ghcr.io/d95tan/bb_bot:staging` | Staging calendar id |
| prd | TrueNAS | `ghcr.io/d95tan/bb_bot:<version>` | Real calendar id |

Two TrueNAS stacks: different compose project names (or app names), data mounts, Telegram bots, `API_KEY`, and `GOOGLE_CALENDAR_ID`. See [DEPLOYMENT.md](DEPLOYMENT.md).

### CI

**[PR Validation](.github/workflows/pr-validation.yml)** runs on pull requests to `main` or `develop`: flake8, pytest, import check, and a Docker build (no push).

**[Docker Build and Publish](.github/workflows/docker-publish.yml)**:

- Pull requests to `main`: build the image, do not push.
- Push to `develop`: push floating tag `staging` (`BUILD_VERSION` is `<pyproject>-staging`).
- Push to `main`: push `latest`, a branch tag, and the immutable `pyproject.toml` version.
- `v*.*.*` tags and **workflow_dispatch** also publish.

**protect-develop** and **protect-main** require those three PR Validation jobs. The workflow YAML only *runs* the checks; the rulesets are what block merge when they are red. Do not require **Docker Build and Publish** as a status check. Repository admin bypass on the PR rulesets is the emergency escape if Actions is down.

Iceboxed ideas live in [FUTURE.md](FUTURE.md).
