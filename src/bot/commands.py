"""Bot command definitions and descriptions."""

from telegram import BotCommand


# Command definitions with descriptions
COMMANDS = [
    BotCommand("start", "Initialize the bot"),
    BotCommand("help", "Show available commands and usage instructions"),
    BotCommand("schedule", "View your upcoming schedule from Google Calendar"),
    BotCommand("took_medication", "Mark medication as taken today"),
    BotCommand("version", "Show deployed version"),
]
