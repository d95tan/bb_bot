"""User-facing reply and status messages used by the bot."""

# ----- Command responses -----
HELP_TEXT = """
📅 *Shift Schedule Bot*

Upload a screenshot of your shift schedule, and I'll add it to your Google Calendar.

*Available Commands:*
/start - Initialize the bot
/help - Show this help message
/schedule - View your upcoming schedule
/took_medication - Mark medication as taken today (stops reminder for today)

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
PROCESSING_IMAGE_UNCOMPRESSED_SUFFIX = "\n_(Using uncompressed image for better accuracy)_"

# ----- Reminder -----
REMINDER_MESSAGE = (
    "💊 Medication reminder\n\n"
    "Time to take your medication for today.\n\n"
    "Tap the button below when done, or use /took_medication"
)
REMINDER_ACK_EDIT_TEXT = "💊 _Acknowledged._"
TOOK_MEDICATION_REPLY = "✅ Recorded. Stay safe!"

# ----- Calendar status (for _build_calendar_status) -----
CALENDAR_STATUS_DRY_RUN = "🧪 DRY-RUN MODE: Calendar uploads disabled"
CALENDAR_STATUS_ALL_FAILED = "❌ Failed to add shifts to calendar ({failed} failed)"
CALENDAR_STATUS_PARTIAL = "⚠️ Partial success: {parts}"
CALENDAR_STATUS_ALL_SKIPPED = "ℹ️ All {skipped} shifts already exist in calendar"
CALENDAR_STATUS_SUCCESS_SOME_SKIPPED = "✅ Added to calendar ({created} new, {skipped} already existed)"
CALENDAR_STATUS_ALL_SUCCESS = "✅ All shifts added to Google Calendar!"

# ----- Other replies -----
UNAUTHORIZED = "⛔ You are not authorized to use this bot."
NOT_AUTHORIZED_CALLBACK = "Not authorized."
REMINDER_ACK_CALLBACK_ANSWER = "Done!"

NO_SCHEDULE_FOUND = (
    "📭 No upcoming shifts found in your calendar.\n\n"
    "Upload a screenshot of your shift schedule to add shifts."
)
SCHEDULE_HEADER = "📅 *Your Upcoming Schedule:*\n"
SCHEDULE_FETCH_ERROR = "❌ Error fetching schedule: {error}"
IMAGE_EXTRACT_FAILED = (
    "❌ Could not extract schedule from the image. "
    "Please make sure the screenshot is clear and try again."
)
IMAGE_PROCESSING_ERROR = "❌ An error occurred while processing your schedule: {error}"
SEND_SCREENSHOT = (
    "📷 Please send me a screenshot of your shift schedule.\n\n"
    "Use /help to see available commands."
)
NOT_AN_IMAGE = "📄 That doesn't look like an image. Please send a PNG or JPEG screenshot."

# ----- Version -----
VERSION_REPLY = "bb_bot version {version}"
