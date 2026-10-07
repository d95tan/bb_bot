# Deployment Guide

## 1. Build and Push Docker Image

The GitHub Action publishes to GHCR:

- Merge to **`develop`**: tag `staging` (overwritten each time)
- Merge to **`main`**: tags `latest` and the immutable `pyproject.toml` version (e.g. `0.4.0`)

### Manual Trigger

You can also manually trigger the build in the "Actions" tab of your GitHub repository.

### Image Location

Images:

- Staging: `ghcr.io/d95tan/bb_bot:staging`
- Production: `ghcr.io/d95tan/bb_bot:<version>` (pin this; use `latest` only if you accept auto-follow)

### Authentication (For Private Repositories)

If your GitHub repository is private, you need to provide TrueNAS with credentials to pull the image.

#### i. Generate a GitHub Personal Access Token (PAT)

- Go to GitHub -> Settings -> Developer settings -> Personal access tokens -> Tokens (classic).
- Click **Generate new token (classic)**.
- Give it a name (e.g., "TrueNAS").
- Select the `read:packages` scope.
- Generate and copy the token.

#### ii. Add Credential to TrueNAS Scale

- In the TrueNAS web interface, go to **Apps**.
- Click on the **Settings** dropdown (or look for "Manage Container Registries").
- Click **Add**.
- **Registry**: `https://ghcr.io` (or Select "GitHub" if available)
- **Username**: Your GitHub Username
- **Password**: The Personal Access Token (PAT) you copied.
- Save the credential.

#### iii. Use Credential in App

- When configured the app, under the "Image" or "Container" section, look for **Image Pull Secrets** or **Container Registry**.
- Select the credential you just created.

## 2. Prepare Configuration

Before deploying, ensure you have your `GOOGLE_REFRESH_TOKEN`.
If you haven't generated one yet, run the auth setup locally on your machine:

```bash
telebot-auth
```

Copy the refresh token output by the script.

## 3. Environments on TrueNAS Scale

Run **two separate stacks** on the NAS (staging and production). Do not share `/app/data`, Redis, or Telegram bot tokens between them. Both may write to Google Calendar; use a **different `GOOGLE_CALENDAR_ID`** for staging.

Local **dev** stays on your laptop (`docker compose up --build`). It does not use GHCR.

### Compose (recommended if TrueNAS runs a compose YAML)

Same image, different tag and project name. Hardcoded `container_name` values were removed so two stacks can coexist.

Staging:

```bash
COMPOSE_PROJECT_NAME=bb_bot_staging BB_BOT_TAG=staging API_HOST_PORT=8001 \
  docker compose -f docker-compose.yml -f docker-compose.nas.yml --profile admin up -d
```

Production (example pin):

```bash
COMPOSE_PROJECT_NAME=bb_bot_prd BB_BOT_TAG=0.4.0 \
  docker compose -f docker-compose.yml -f docker-compose.nas.yml --profile admin up -d
```

Point each project at its own directory (or bind mounts) for `data/`, `config/`, and `.env`. After a new `develop` merge, restage with `docker compose … pull && up -d` — the tag string stays `staging`.

### Custom App (Repository + Tag)

You can deploy this as a "Custom App" in TrueNAS Scale. Create **two** apps (`bb-bot-staging`, `bb-bot`).

### Application Configuration

- **Application Name**: `bb-bot-staging` or `bb-bot`
- **Container Image**: `ghcr.io/d95tan/bb_bot:staging` or `ghcr.io/d95tan/bb_bot:0.4.0`
- **Image Pull Policy**: `Always` (ensures you get updates on restart)

### Environment Variables

Add the following environment variables in the "Container Environment Variables" section:

| Key                    | Value                                       |
| ---------------------- | ------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`   | Your Telegram Bot Token                     |
| `TELEGRAM_USER_IDS`    | Your Telegram User ID(s), comma-separated   |
| `ADMIN_TELEGRAM_BOT_TOKEN` | Admin bot token (only if you run the admin container) |
| `ADMIN_TELEGRAM_USER_IDS` | Your Telegram user id for the admin bot     |
| `API_KEY`              | Shared secret the user-bot sends to the API |
| `API_BASE_URL`         | `http://api:8000` when API is another container |
| `GOOGLE_CLIENT_ID`     | Your Google OAuth Client ID                 |
| `GOOGLE_CLIENT_SECRET` | Your Google OAuth Client Secret             |
| `GOOGLE_REFRESH_TOKEN` | The token you generated in step 2           |
| `GOOGLE_CALENDAR_ID`   | Staging calendar id vs production calendar id |
| `TIMEZONE`             | `Asia/Singapore` (or your timezone)         |

### Storage (Volumes)

**Optional**: To persist configuration (like shift definitions) and allow editing them without rebuilding the image, mount the configuration directory. If left unmounted, the bot will use the default configuration files included in the Docker image.

- **Host Path**: `/mnt/pool/dataset/bb_bot/config` (Example path on your NAS)
- **Mount Path**: `/app/config`

If you mount this path, you should copy your local `config/shifts.yaml` and `config/grid.yaml` to this directory on your NAS.

Optional: To save debug images

- **Host Path**: `/mnt/pool/dataset/bb_bot/debug`
- **Mount Path**: `/app/debug`

**Reminder acknowledgments:**

- **With docker-compose:** Redis, FastAPI (`api`), and Telegram user-bot (`user-bot`) run in the same stack. The API owns OCR, calendar sync, and medication reminders; the bot is a thin Telegram client. Reminder state is stored in the `redis_data` volume and survives restarts.
- **Without compose (e.g. TrueNAS custom app):** Run **two** containers from the same image — one with `python -m src.api.main`, one with `python -m src.main` — sharing `/app/data` and Redis. Set `API_BASE_URL` on the bot to reach the API. Or leave `REDIS_URL` unset on the API for file-based storage (`data/reminder_acknowledgments.json`) and mount `/app/data` for persistence.
- **Admin bot (optional):** Third container, same image tag, command `python -m src.admin_bot.main`, env `ADMIN_TELEGRAM_BOT_TOKEN` + `ADMIN_TELEGRAM_USER_IDS` + `API_BASE_URL`. You can omit it until you want admin commands. After it is running, remove your id from `TELEGRAM_USER_IDS` so family reminders only go to the user-bot account.

**Note:** A single container that only runs `python -m src.main` is no longer enough; the API process must be running for uploads, schedule, reminders, and medication stats.

## 4. Troubleshooting

If the bot fails to start, check the container logs in TrueNAS.
Common issues:

- Missing environment variables.
- Invalid Google Tokens.
- Config files missing in the mounted volume (if you mounted `/app/config`, ensure the files exist there, otherwise the container sees an empty directory).

**Note on Config Mounting**:
The Docker image contains default config files. If you mount a host directory to `/app/config`, it will hide the default files. **You must populate the host directory with the config files first.**
