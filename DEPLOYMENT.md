# Deployment Guide

## 1. Build and Push Docker Image

The repository includes a GitHub Action workflow that automatically builds and pushes the Docker image to GitHub Container Registry (GHCR) whenever you push to the `main` or `master` branch.

### Manual Trigger
You can also manually trigger the build in the "Actions" tab of your GitHub repository.

### Image Location
The image will be available at:
`ghcr.io/d95tan/bb_bot:latest`

### Authentication (For Private Repositories)

If your GitHub repository is private, you need to provide TrueNAS with credentials to pull the image.

**1. Generate a GitHub Personal Access Token (PAT)**
   - Go to GitHub -> Settings -> Developer settings -> Personal access tokens -> Tokens (classic).
   - Click **Generate new token (classic)**.
   - Give it a name (e.g., "TrueNAS").
   - Select the `read:packages` scope.
   - Generate and copy the token.

**2. Add Credential to TrueNAS Scale**
   - In the TrueNAS web interface, go to **Apps**.
   - Click on the **Settings** dropdown (or look for "Manage Container Registries").
   - Click **Add**.
   - **Registry**: `https://ghcr.io` (or Select "GitHub" if available)
   - **Username**: Your GitHub Username
   - **Password**: The Personal Access Token (PAT) you copied.
   - Save the credential.

**3. Use Credential in App**
   - When configured the app, under the "Image" or "Container" section, look for **Image Pull Secrets** or **Container Registry**.
   - Select the credential you just created.

## 2. Prepare Configuration

Before deploying, ensure you have your `GOOGLE_REFRESH_TOKEN`.
If you haven't generated one yet, run the auth setup locally on your machine:

```bash
python -m src.auth_setup
```

Copy the refresh token output by the script.

## 3. Deploy on TrueNAS Scale

You can deploy this as a "Custom App" in TrueNAS Scale.

### Application Configuration

- **Application Name**: `bb-bot` (or any name you prefer)
- **Container Image**: `ghcr.io/d95tan/bb_bot:latest`
- **Image Pull Policy**: `Always` (ensures you get updates on restart)

### Environment Variables

Add the following environment variables in the "Container Environment Variables" section:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram Bot Token |
| `TELEGRAM_USER_ID` | Your Telegram User ID |
| `GOOGLE_CLIENT_ID` | Your Google OAuth Client ID |
| `GOOGLE_CLIENT_SECRET` | Your Google OAuth Client Secret |
| `GOOGLE_REFRESH_TOKEN` | The token you generated in step 2 |
| `GOOGLE_CALENDAR_ID` | `primary` (or your specific calendar ID) |
| `TIMEZONE` | `Asia/Singapore` (or your timezone) |

### Storage (Volumes)

**Optional**: To persist configuration (like shift definitions) and allow editing them without rebuilding the image, mount the configuration directory. If left unmounted, the bot will use the default configuration files included in the Docker image.

- **Host Path**: `/mnt/pool/dataset/bb_bot/config` (Example path on your NAS)
- **Mount Path**: `/app/config`

If you mount this path, you should copy your local `config/shifts.yaml` and `config/grid.yaml` to this directory on your NAS.

Optional: To save debug images
- **Host Path**: `/mnt/pool/dataset/bb_bot/debug`
- **Mount Path**: `/app/debug`

**Reminder acknowledgments** (choose one):

- **Redis (recommended for TrueNAS / multi-instance):** Install Redis (e.g. as a TrueNAS app or in a container), then set `REDIS_URL` in the bot’s environment, e.g. `redis://redis-host:6379/0`. The bot will use Redis for reminder state so it survives restarts and is shared across multiple bot instances.
- **File (single instance):** If `REDIS_URL` is not set, the bot uses `data/reminder_acknowledgments.json`. Mount a volume for persistence, e.g. Host `/mnt/pool/dataset/bb_bot/data` → `/app/data`. Multiple instances do not share the file.

## 4. Troubleshooting

If the bot fails to start, check the container logs in TrueNAS.
Common issues:
- Missing environment variables.
- Invalid Google Tokens.
- Config files missing in the mounted volume (if you mounted `/app/config`, ensure the files exist there, otherwise the container sees an empty directory).

**Note on Config Mounting**:
The Docker image contains default config files. If you mount a host directory to `/app/config`, it will hide the default files. **You must populate the host directory with the config files first.**
