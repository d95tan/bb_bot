"""User-facing strings for the admin bot."""

UNAUTHORIZED = "You are not authorized to use this admin bot."

START_TEXT = """
*bb_bot admin*

Patch logs, check reminders, and inspect adherence. This bot talks to the API only — reminders still go out on the family bot.
"""

HELP_TEXT = """
*Admin commands*

/health — version, calendar, data mount
/reminder\\_status — if/when today's reminder fired
/trigger\\_reminder — send a reminder now (confirm)
/patch `YYYY-MM-DD` `[YYYY-MM-DD]` `[note]` — preview then confirm
/unlog `YYYY-MM-DD` `[YYYY-MM-DD]` `[note]` — preview then confirm
/stats `[days]` — streaks, rate, missed days (default 30, max 180)
/shifts `[days]` — upcoming calendar (default 7)
/export `[days]` — CSV document
/audit — recent admin actions
"""

USAGE_PATCH = "Usage: /patch YYYY-MM-DD [YYYY-MM-DD] [note]"
USAGE_UNLOG = "Usage: /unlog YYYY-MM-DD [YYYY-MM-DD] [note]"
USAGE_STATS = "Usage: /stats [days]  (1–180, default 30)"
USAGE_SHIFTS = "Usage: /shifts [days]  (1–14, default 7)"
USAGE_EXPORT = "Usage: /export [days]  (1–180, default 30)"

CONFIRM = "Confirm"
CANCEL = "Cancel"
CANCELLED = "Cancelled."
BACKEND_ERROR = "API error: {error}"

NO_SENDS_TODAY = "No reminder recorded for today ({today}, {tz})."
ACKED_YES = "Acknowledged: yes"
ACKED_NO = "Acknowledged: no"

TRIGGER_PROMPT = "Send a medication reminder now on the *family* bot?"
TRIGGER_DONE = "Sent {n} reminder(s). Already acknowledged today: {acked}."
