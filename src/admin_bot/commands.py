"""Admin bot command menu."""

from telegram import BotCommand

COMMANDS = [
    BotCommand("start", "Initialize the admin bot"),
    BotCommand("help", "Show admin commands"),
    BotCommand("health", "API version, calendar, data mount"),
    BotCommand("reminder_status", "Whether today's reminder was sent"),
    BotCommand("trigger_reminder", "Send a reminder now (family bot)"),
    BotCommand("patch", "Log medication for a date or range"),
    BotCommand("unlog", "Remove a mistaken medication log"),
    BotCommand("stats", "Adherence stats (optional days 1–180)"),
    BotCommand("shifts", "Upcoming shifts (optional days 1–14)"),
    BotCommand("export", "CSV of taken dates"),
    BotCommand("audit", "Recent admin actions"),
]
