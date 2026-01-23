"""Bot command definitions and descriptions."""

from telegram import BotCommand


# Command definitions with descriptions
COMMANDS = [
    BotCommand("start", "Initialize the bot"),
    BotCommand("help", "Show available commands and usage instructions"),
    BotCommand("schedule", "View your upcoming schedule from Google Calendar"),
]


HELP_TEXT = """
📅 *Shift Schedule Bot*

Upload a screenshot of your shift schedule, and I'll add it to your Google Calendar.

*Available Commands:*
/start - Initialize the bot
/help - Show this help message
/schedule - View your upcoming schedule

*How to use:*
1. Send me a screenshot of your shift schedule
2. I'll process it and add the shifts to your calendar

*Supported Shifts:*
• AM (07:30-15:30)
• PM (13:30-21:30)
• Night (21:00-08:00 next day)
• Training (08:00-18:00)
• Off
• Annual Leave
"""


START_TEXT = """
👋 Welcome to the Shift Schedule Bot!

I can help you manage your work schedule by:
• Reading screenshots of your shift roster
• Adding shifts to your Google Calendar

Simply send me a screenshot of your shift schedule to get started!

Need help? Use /help to see all available commands.
"""


CALENDAR_NOT_CONFIGURED_TEXT = """
⚠️ *Google Calendar is not configured.*

Please run the setup script to authorize Google Calendar access:

```
telebot-auth
```

Then add the refresh token to your `.env` file.
"""


SCHEDULE_UPLOADED_TEXT = """
✅ *Schedule Processed Successfully!*

I found the following shifts:

{schedule_summary}

{calendar_status}
"""


PROCESSING_IMAGE_TEXT = "🔄 Processing your schedule image..."
