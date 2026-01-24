# Deployment Guide

## 1. Build and Push Docker Image

The repository includes a GitHub Action workflow that automatically builds and pushes the Docker image to GitHub Container Registry (GHCR) whenever you push to the `main` or `master` branch.

### Manual Trigger
You can also manually trigger the build in the "Actions" tab of your GitHub repository.

### Image Location
The image will be available at:
`ghcr.io/d95tan/bb_bot:latest`

(Note: Ensure your GitHub repository visibility allows access, or you are logged in to GHCR on your TrueNAS if it's private).

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

To persist configuration (like shift definitions) and allow editing them without rebuilding the image, mount the configuration directory.

- **Host Path**: `/mnt/pool/dataset/bb_bot/config` (Example path on your NAS)
- **Mount Path**: `/app/config`

You should copy your local `config/shifts.yaml` and `config/grid.yaml` to this directory on your NAS.

Optional: To save debug images
- **Host Path**: `/mnt/pool/dataset/bb_bot/debug`
- **Mount Path**: `/app/debug`

## 4. Troubleshooting

If the bot fails to start, check the container logs in TrueNAS.
Common issues:
- Missing environment variables.
- Invalid Google Tokens.
- Config files missing in the mounted volume (if you mounted `/app/config`, ensure the files exist there, otherwise the container sees an empty directory).

**Note on Config Mounting**:
The Docker image contains default config files. If you mount a host directory to `/app/config`, it will hide the default files. **You must populate the host directory with the config files first.**
