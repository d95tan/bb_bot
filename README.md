# Telegram Shift Schedule Bot

A Telegram bot that processes shift work schedule screenshots using OCR and automatically adds them to Google Calendar.

## Features

- **Screenshot Processing**: Send a screenshot of your shift schedule, and the bot extracts shifts using Tesseract OCR
- **Google Calendar Integration**: Automatically creates/updates calendar events for each shift
- **Smart OCR**: Character whitelisting, dictionary bypass, and fuzzy matching for common OCR errors
- **Color Fallback**: When OCR fails, uses color detection to identify shift types
- **Configurable Shifts**: Easy to customize shift types, timings, and colors via YAML config
- **Multi-User Support**: Allow multiple Telegram users to use the bot
- **Night Shift Handling**: Automatically adjusts rest days that follow night shifts
- **Docker Support**: Easy deployment with Docker and Docker Compose

## Supported Shift Types

Shift timings are fully customizable in `config/shifts.yaml`. Example:

| Shift | Time | Notes |
|-------|------|-------|
| AM (A1-A6) | 07:30 - 15:00+ | Morning shifts |
| PM (P1-P3) | 13:30 - 21:30+ | Afternoon shifts |
| Night (N1) | 21:00 - 08:00 | Overnight (ends next day) |
| Training | 08:00 - 18:00 | Training day |
| Off (DO/RD) | All day | Day off / Rest day |
| Leave (AL/HL) | All day | Annual/Hospital leave |

## Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Cloud Project with Calendar API enabled
- Tesseract OCR installed on your system

### Installing Tesseract

**Windows:**
```bash
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
# Or use chocolatey:
choco install tesseract
```

**macOS:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng
```

## Setup

### 1. Clone and Install Dependencies

```bash
git clone <repo-url>
cd bb_bot
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Install the package
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### 2. Create Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token provided

### 3. Get Your Telegram User ID

1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send any message to it
3. Copy your user ID (and your partner's if needed)

### 4. Setup Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Calendar API**:
   - Go to APIs & Services > Library
   - Search for "Google Calendar API"
   - Click Enable
4. Create OAuth credentials:
   - Go to APIs & Services > Credentials
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" as application type
   - Copy the Client ID and Client Secret
5. Configure OAuth consent screen:
   - Go to APIs & Services > OAuth consent screen
   - Add your email as a test user (required for unverified apps)

### 5. Configure Environment Variables

Copy `env.example` to `.env` and fill in your values:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_USER_IDS=123456789,987654321  # Comma-separated for multiple users

# Google Calendar API
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=  # Leave empty - will be filled after auth setup
GOOGLE_CALENDAR_ID=primary
TIMEZONE=Asia/Singapore

# Feature Flags
ENABLE_CALENDAR_UPLOAD=true      # Set to false for dry-run mode
DEBUG_SAVE_CELLS=false           # Save cropped cell images for debugging
COLOR_ONLY_MODE=false            # Skip OCR, use only color detection
```

### 6. Authorize Google Calendar

Run the authorization setup script:

```bash
telebot-auth
# Or: python -m src.auth_setup
```

This will:
1. Open a browser for Google sign-in
2. Ask you to grant calendar access
3. Display a refresh token

Copy the refresh token to your `.env` file.

### 7. Run the Bot

```bash
# Production
telebot

# Development (with auto-reload)
telebot-dev
```

## Local development / testing

Two ways to run and test on your machine.

### Option A: Docker Compose (simplest)

Runs the bot and Redis together; no need to install Python or Tesseract locally for integration testing.

1. **Prepare `.env`** (copy from `env.example`, fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_IDS`, Google credentials). You still need to run `telebot-auth` once (e.g. in a local venv) to get `GOOGLE_REFRESH_TOKEN`, then put it in `.env`.
2. **Start the stack:**
   ```bash
   docker compose up -d
   ```
   This starts Redis and the bot. The bot uses `REDIS_URL=redis://redis:6379/0` automatically.
3. **Test:** Open Telegram, send your bot a schedule screenshot. Check logs with `docker compose logs -f bb_bot`.
4. **Stop:** `docker compose down`. Add `-v` to remove the Redis volume and lose reminder state.

### Option B: Run the bot locally (venv)

Useful for debugging, OCR tweaks, or running tests.

1. **Prerequisites:** Python 3.11+, Tesseract installed, venv created, `pip install -e ".[dev]"`.
2. **Redis (optional):** To test reminder + Redis locally, start Redis:
   ```bash
   docker run -d -p 6379:6379 --name redis redis:7-alpine
   ```
   Then in `.env` set `REDIS_URL=redis://localhost:6379/0`. If you omit `REDIS_URL`, the bot uses file-based reminder storage under `data/`.
3. **Google token:** Run `telebot-auth` once and set `GOOGLE_REFRESH_TOKEN` in `.env`.
4. **Run the bot:**
   ```bash
   telebot          # or: python -m src.main
   # or with reload:
   telebot-dev
   ```
5. **Test:** Send a schedule image to the bot in Telegram. For OCR-only tests without the bot: `python scripts/test_ocr.py sample_images/01_2026.jpg` (run from repo root with `PYTHONPATH=.` or install the package).

### Quick checklist

- [ ] `.env` filled (bot token, user IDs, Google client id/secret, refresh token)
- [ ] `telebot-auth` run and refresh token in `.env`
- [ ] Tesseract installed (for local run) or use Docker
- [ ] Redis: use Docker Compose, or `docker run redis` + `REDIS_URL`, or leave unset for file storage

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot |
| `/help` | Show available commands |
| `/schedule` | View upcoming shifts from Google Calendar |

### Uploading a Schedule

1. Take a screenshot of your shift schedule app
2. Send it to the bot (as photo or uncompressed file)
3. The bot will process it and add events to your calendar

### Utility Scripts

```bash
# Test OCR on sample images
python scripts/test_ocr.py sample_images/

# Wipe a month's calendar events
python scripts/wipe_calendar.py
```

## Configuration

### Shift Mappings (`config/shifts.yaml`)

The configuration uses a two-tier lookup system:

**1. Code Mappings (Primary)** - Direct shift code to timing:

```yaml
code_mappings:
  D0G8:
    name: "A3"              # Display name for calendar
    start: "07:30"
    end: "15:30"
    same_day: true
    description: "D0G8 - AM Shift"
  
  N2111:
    name: "N1"
    start: "21:00"
    end: "08:00"
    same_day: false         # Overnight shift
    description: "Night Shift"
  
  DO:
    name: "Day Off"
    all_day: true
    description: "Day Off"
```

**2. Color Fallbacks (Secondary)** - Used when OCR fails:

```yaml
color_fallbacks:
  pink:
    rgb_range:
      r: [200, 255]
      g: [100, 180]
      b: [150, 220]
    shift:
      start: "13:30"
      end: "21:30"
      same_day: true
      description: "PM Shift (detected by color)"
```

### Grid Configuration (`config/grid.yaml`)

Calibrate the OCR grid boundaries for your phone's screenshot format:

```yaml
# Grid boundaries (percentage of image size)
grid_left_pct: 0.02
grid_right_pct: 0.98
grid_top_pct: 0.28
grid_bottom_pct: 0.775

# Cell cropping (remove day number and time text)
crop_top_pct: 0.15
crop_bottom_pct: 0.515

# Grid structure
grid_columns: 7
grid_rows: 6
```

To calibrate:
1. Set `DEBUG_SAVE_CELLS=true` in `.env`
2. Send an image to the bot
3. Check `debug/<month>/_grid_overlay.png`
4. Adjust values until the grid aligns

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Manual Docker Build

```bash
docker build -t bb-bot .
docker run -d --env-file .env -v ./config:/app/config:ro bb-bot
```

## Project Structure

```
bb_bot/
├── src/
│   ├── main.py                 # Entry point
│   ├── dev.py                  # Development server with auto-reload
│   ├── config.py               # Configuration management
│   ├── auth_setup.py           # Google OAuth setup script
│   ├── bot/
│   │   ├── handlers.py         # Telegram message handlers
│   │   └── commands.py         # Command definitions
│   └── services/
│       ├── image_processor.py  # OCR and schedule extraction
│       ├── calendar_service.py # Google Calendar integration
│       └── reminder_service.py # Reminders (stub)
├── config/
│   ├── shifts.yaml             # Shift definitions
│   └── grid.yaml               # Grid calibration
├── scripts/
│   ├── test_ocr.py             # OCR testing utility
│   └── wipe_calendar.py        # Calendar cleanup utility
├── tests/
│   └── test_image_processor.py # Unit tests
├── .github/
│   └── workflows/
│       └── pr-validation.yml   # CI workflow
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Development

### Running Tests

```bash
# Activate venv first
.\venv\Scripts\python.exe -m pytest tests/ -v

# Or after activating venv
pytest tests/ -v
```

### Linting

```bash
flake8 src/
```

### Debug Mode

Enable debug features in `.env`:

```env
DEBUG_SAVE_CELLS=true           # Saves cropped cell images to debug/
ENABLE_CALENDAR_UPLOAD=false    # Dry-run mode (no calendar changes)
```

## Troubleshooting

### "Google Calendar is not configured"

Run `telebot-auth` to authorize the bot and get a refresh token.

### OCR not reading shifts correctly

1. Enable debug mode: `DEBUG_SAVE_CELLS=true`
2. Send an image and check `debug/<month>/` for cropped cells
3. Adjust `config/grid.yaml` if grid alignment is off
4. Add missing shift codes to `config/shifts.yaml`

### Bot doesn't respond

- Verify your user ID is in `TELEGRAM_USER_IDS`
- Check the bot token is correct
- Ensure the bot is running

### D0G8 being read as DOGS

The OCR has dictionary bypass enabled, but some misreads may still occur. The bot uses character whitelisting from your `shifts.yaml` codes to reduce errors.

## How It Works

1. **Screenshot Processing**:
   - OCR extracts month/year from the header
   - Grid is divided into cells based on `grid.yaml` calibration
   - Each cell is cropped, scaled, and processed with Tesseract
   - Shift codes are normalized to handle OCR errors (D0G8 ↔ DOGS, etc.)

2. **Shift Lookup** (Two-tier):
   - First matches shift code in `code_mappings`
   - Falls back to color detection if code is unknown

3. **Calendar Events**:
   - Clears existing events for the date range
   - Creates new events with proper timing
   - Rest days after night shifts start at 8am (not all-day)

## License

MIT
