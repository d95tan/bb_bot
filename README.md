# Telegram Shift Schedule Bot

A simple, stateless Telegram bot that processes shift work schedule screenshots and adds them to Google Calendar.

## Features

- **Screenshot Processing**: Send a screenshot of your shift schedule, and the bot extracts the shifts automatically (placeholder implementation - awaiting sample images)
- **Google Calendar Integration**: Automatically creates calendar events for each shift
- **Configurable Shifts**: Easy to add/edit shift types and timings via YAML config
- **Single User**: Designed for personal use with minimal setup

## Supported Shift Types

| Shift | Time | Notes |
|-------|------|-------|
| AM | 07:30 - 15:30 | Morning shift |
| PM | 13:30 - 21:30 | Afternoon shift |
| Night | 21:00 - 08:00 | Overnight (ends next day) |
| Training | 08:00 - 18:00 | Training day |
| Off | All day | Day off |
| Annual Leave | All day | Leave day |

Shift timings can be customized in `config/shifts.yaml`.

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
sudo apt install tesseract-ocr
```

## Setup

### 1. Clone and Install Dependencies

```bash
cd telebot-app
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
3. Copy your user ID

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

Create a `.env` file in the project root:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_USER_ID=your_telegram_user_id

# Google Calendar API
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret

# Leave empty for now - will be filled after auth setup
GOOGLE_REFRESH_TOKEN=

# Calendar settings
GOOGLE_CALENDAR_ID=primary
TIMEZONE=Australia/Sydney
```

### 6. Authorize Google Calendar

Run the authorization setup script:

```bash
# Using the CLI command
telebot-auth

# Or using Python module
python -m src.auth_setup
```

This will:
1. Open a browser for Google sign-in
2. Ask you to grant calendar access
3. Display a refresh token

Copy the refresh token and add it to your `.env` file:

```env
GOOGLE_REFRESH_TOKEN=your_refresh_token_here
```

### 7. Run the Bot

```bash
# Using the CLI command
telebot

# Or using Python module
python -m src.main
```

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot |
| `/help` | Show available commands |
| `/schedule` | View upcoming shifts from Google Calendar |

### Uploading a Schedule

1. Take a screenshot of your shift schedule
2. Send it to the bot
3. The bot will process it and add events to your calendar

## Configuration

### Shift Mappings (`config/shifts.yaml`)

The configuration uses a two-tier lookup system:

**1. Code Mappings (Primary)** - Direct shift code to timing:

```yaml
code_mappings:
  E0M8:
    start: "13:30"
    end: "21:30"
    same_day: true
    description: "PM Shift"
  
  N2111:
    start: "21:00"
    end: "08:00"
    same_day: false  # Overnight
    description: "Night Shift"
  
  DO:
    all_day: true
    description: "Day Off"
```

**2. Color Fallbacks (Secondary)** - Used when code is unknown:

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

### Adding New Shift Codes

1. Edit `config/shifts.yaml`
2. Add a new entry under `code_mappings:`
3. No restart needed - config is loaded per request

## Project Structure

```
telebot-app/
├── src/
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration management
│   ├── auth_setup.py           # Google OAuth setup script
│   ├── bot/
│   │   ├── handlers.py         # Telegram message handlers
│   │   └── commands.py         # Command definitions
│   └── services/
│       ├── image_processor.py  # Schedule extraction (placeholder)
│       ├── calendar_service.py # Google Calendar integration
│       └── reminder_service.py # Medication reminders (stub)
├── config/
│   └── shifts.yaml             # Shift definitions
├── pyproject.toml              # Project config & dependencies
└── README.md
```

## Troubleshooting

### "Google Calendar is not configured"

Run `python -m src.auth_setup` to authorize the bot and get a refresh token.

### "Could not extract schedule from image"

The image processor is currently a placeholder. It returns mock data for testing. Actual OCR implementation is pending sample screenshots.

### Bot doesn't respond

- Make sure your Telegram user ID in `.env` matches your actual ID
- Check that the bot token is correct
- Verify the bot is running (`python -m src.main`)

## How It Works

1. **Screenshot Processing**: When you send a schedule screenshot:
   - OCR extracts the month/year from the header
   - Each calendar cell is analyzed for shift codes
   - Colors are detected as a fallback for unknown codes

2. **Shift Lookup**: Two-tier system:
   - First tries to match the shift code (e.g., "E0M8") in `code_mappings`
   - Falls back to color detection if code is unknown

3. **Calendar Events**: Creates Google Calendar events with proper timing based on shift config

## Future Features (Planned)

- **Medication Reminders**: Periodic reminders based on shift schedule (stub implementation included)

## License

MIT
