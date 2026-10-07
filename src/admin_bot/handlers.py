"""Admin Telegram handlers (thin HTTP client)."""

from __future__ import annotations

import logging
import re
from datetime import date
from io import BytesIO

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from src.admin_bot import replies
from src.admin_bot.commands import COMMANDS
from src.clients.backend import BackendClient
from src.config import get_settings

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CB_OK_PATCH = "admin_ok:patch"
CB_NO_PATCH = "admin_no:patch"
CB_OK_UNLOG = "admin_ok:unlog"
CB_NO_UNLOG = "admin_no:unlog"
CB_OK_TRIGGER = "admin_ok:trigger"
CB_NO_TRIGGER = "admin_no:trigger"


def is_authorized_admin(user_id: int) -> bool:
    """True if user_id is in ADMIN_TELEGRAM_USER_IDS."""
    return user_id in get_settings().authorized_admin_user_ids


def _backend() -> BackendClient:
    return BackendClient()


def _confirm_keyboard(ok: str, cancel: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(replies.CONFIRM, callback_data=ok),
                InlineKeyboardButton(replies.CANCEL, callback_data=cancel),
            ]
        ]
    )


def _error_text(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return replies.BACKEND_ERROR.format(error=detail)
    return replies.BACKEND_ERROR.format(error=str(exc))


def _parse_date_args(args: list[str]) -> tuple[date, date, str | None] | None:
    """Parse YYYY-MM-DD [YYYY-MM-DD] [note]. Returns None if missing/invalid start."""
    if not args or not _DATE_RE.match(args[0]):
        return None
    try:
        start = date.fromisoformat(args[0])
    except ValueError:
        return None
    rest = args[1:]
    end = start
    if rest and _DATE_RE.match(rest[0]):
        try:
            end = date.fromisoformat(rest[0])
        except ValueError:
            return None
        rest = rest[1:]
    note = " ".join(rest).strip() or None
    return start, end, note


def _parse_bounded_int(
    args: list[str], default: int, lo: int, hi: int
) -> int | None:
    """Parse optional int in [lo, hi]. Empty args → default. Invalid → None."""
    if not args:
        return default
    try:
        value = int(args[0])
    except ValueError:
        return None
    if value < lo or value > hi:
        return None
    return value


def _format_preview(kind: str, data: dict) -> str:
    start = data.get("start_date")
    end = data.get("end_date")
    window = start if start == end else f"{start} → {end}"
    already = data.get("already_taken") or []
    missing = data.get("missing") or []
    note = data.get("note")
    lines = [
        f"*{kind}* {window}",
        f"Streak now: {data.get('streak_before')} → after: {data.get('streak_after')}",
    ]
    if already:
        lines.append("Already logged: " + ", ".join(already))
    if missing:
        lines.append("Not logged: " + ", ".join(missing))
    if note:
        lines.append(f"Note: {note}")
    lines.append("Confirm?")
    return "\n".join(lines)


def _format_sends(sends: list[dict], tz: str) -> list[str]:
    lines: list[str] = []
    for send in sends:
        sent_at = send.get("sent_at") or ""
        source = send.get("source") or ""
        lines.append(f"• {sent_at} ({source}, {tz})")
    return lines


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        await update.message.reply_text(replies.UNAUTHORIZED)
        return
    await update.message.reply_text(replies.START_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    await update.message.reply_text(replies.HELP_TEXT, parse_mode="Markdown")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    try:
        data = await _backend().admin_health(update.effective_user.id)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    cal = "yes" if data.get("calendar_configured") else "no"
    mount = "writable" if data.get("data_dir_writable") else "not writable"
    await update.message.reply_text(
        f"version: {data.get('version')}\ncalendar: {cal}\ndata/: {mount}"
    )


async def reminder_status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    try:
        data = await _backend().admin_reminder_status(update.effective_user.id)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    tz = data.get("timezone") or ""
    today = data.get("today") or ""
    sends = data.get("sends") or []
    acked = replies.ACKED_YES if data.get("acknowledged") else replies.ACKED_NO
    if not sends:
        await update.message.reply_text(
            replies.NO_SENDS_TODAY.format(today=today, tz=tz) + f"\n{acked}"
        )
        return
    lines = [f"Today {today} ({tz})", acked, "Sent:"]
    lines.extend(_format_sends(sends, tz))
    await update.message.reply_text("\n".join(lines))


async def trigger_reminder_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        replies.TRIGGER_PROMPT,
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(CB_OK_TRIGGER, CB_NO_TRIGGER),
    )


async def patch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    parsed = _parse_date_args(list(context.args or []))
    if parsed is None:
        await update.message.reply_text(replies.USAGE_PATCH)
        return
    start, end, note = parsed
    try:
        data = await _backend().admin_patch(
            update.effective_user.id,
            start.isoformat(),
            end.isoformat(),
            note=note,
            dry_run=True,
        )
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    context.user_data["pending_patch"] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "note": note,
    }
    await update.message.reply_text(
        _format_preview("Patch", data),
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(CB_OK_PATCH, CB_NO_PATCH),
    )


async def unlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    parsed = _parse_date_args(list(context.args or []))
    if parsed is None:
        await update.message.reply_text(replies.USAGE_UNLOG)
        return
    start, end, note = parsed
    try:
        data = await _backend().admin_unlog(
            update.effective_user.id,
            start.isoformat(),
            end.isoformat(),
            note=note,
            dry_run=True,
        )
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    context.user_data["pending_unlog"] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "note": note,
    }
    await update.message.reply_text(
        _format_preview("Unlog", data),
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(CB_OK_UNLOG, CB_NO_UNLOG),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    days = _parse_bounded_int(list(context.args or []), 30, 1, 180)
    if days is None:
        await update.message.reply_text(replies.USAGE_STATS)
        return
    try:
        data = await _backend().admin_stats(update.effective_user.id, days=days)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    current = int(data.get("current_streak") or 0)
    longest = int(data.get("longest_streak") or 0)
    rate = float(data.get("adherence_rate") or 0.0)
    missed = [
        item.get("date")
        for item in (data.get("day_by_day") or [])
        if not item.get("taken")
    ]
    lines = [
        f"*Adherence* ({days} days)",
        f"• Current streak: {current}",
        f"• Longest streak: {longest}",
        f"• Rate: {rate * 100:.0f}%",
    ]
    if missed:
        shown = missed[-14:]
        extra = len(missed) - len(shown)
        suffix = f" (+{extra} earlier)" if extra > 0 else ""
        lines.append("• Missed: " + ", ".join(shown) + suffix)
    else:
        lines.append("• Missed: none")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def shifts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    days = _parse_bounded_int(list(context.args or []), 7, 1, 14)
    if days is None:
        await update.message.reply_text(replies.USAGE_SHIFTS)
        return
    try:
        data = await _backend().admin_shifts(update.effective_user.id, days=days)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    if not data.get("calendar_configured", True):
        await update.message.reply_text("Calendar is not configured.")
        return
    events = data.get("events") or []
    if not events:
        await update.message.reply_text("No upcoming shifts in that window.")
        return
    lines = [f"*Shifts* (next {days} days)"]
    for event in events:
        summary = event.get("summary", "Unknown")
        date_part = event.get("date_part", "")
        time_part = event.get("time_part")
        if time_part:
            lines.append(f"• {date_part} {time_part}: {summary}")
        else:
            lines.append(f"• {date_part}: {summary}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    days = _parse_bounded_int(list(context.args or []), 30, 1, 180)
    if days is None:
        await update.message.reply_text(replies.USAGE_EXPORT)
        return
    try:
        csv_body = await _backend().admin_export(update.effective_user.id, days=days)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    buf = BytesIO(csv_body.encode("utf-8"))
    buf.seek(0)
    await update.message.reply_document(
        document=buf,
        filename=f"medication_{days}d.csv",
    )


async def audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not is_authorized_admin(update.effective_user.id):
        return
    try:
        data = await _backend().admin_audit(update.effective_user.id)
    except Exception as e:
        await update.message.reply_text(_error_text(e))
        return
    entries = data.get("entries") or []
    if not entries:
        await update.message.reply_text("No audit entries yet.")
        return
    lines = ["*Audit* (newest first)"]
    for entry in entries[:20]:
        ts = entry.get("ts") or ""
        action = entry.get("action") or ""
        actor = entry.get("actor_id") or ""
        extra = ""
        if entry.get("start_date"):
            extra = f" {entry.get('start_date')}"
            if entry.get("end_date") and entry.get("end_date") != entry.get("start_date"):
                extra += f"→{entry.get('end_date')}"
        if entry.get("sent") is not None:
            extra = f" sent={entry.get('sent')}"
        lines.append(f"• {ts} {action} by {actor}{extra}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    if not is_authorized_admin(update.effective_user.id):
        await query.answer(replies.UNAUTHORIZED)
        return
    data = query.data or ""
    await query.answer()
    if data in {CB_NO_PATCH, CB_NO_UNLOG, CB_NO_TRIGGER}:
        context.user_data.pop("pending_patch", None)
        context.user_data.pop("pending_unlog", None)
        if query.message:
            await query.edit_message_text(replies.CANCELLED)
        return

    actor = update.effective_user.id
    try:
        if data == CB_OK_TRIGGER:
            result = await _backend().admin_trigger_reminder(actor)
            acked = "yes" if result.get("already_acknowledged") else "no"
            text = replies.TRIGGER_DONE.format(
                n=result.get("sent") or 0, acked=acked
            )
        elif data == CB_OK_PATCH:
            pending = context.user_data.pop("pending_patch", None)
            if not pending:
                text = "Nothing to confirm. Run /patch again."
            else:
                result = await _backend().admin_patch(
                    actor,
                    pending["start_date"],
                    pending["end_date"],
                    note=pending.get("note"),
                    dry_run=False,
                )
                text = (
                    f"Patched {len(result.get('applied') or [])} day(s). "
                    f"Streak: {result.get('streak_before')} → {result.get('streak_after')}."
                )
        elif data == CB_OK_UNLOG:
            pending = context.user_data.pop("pending_unlog", None)
            if not pending:
                text = "Nothing to confirm. Run /unlog again."
            else:
                result = await _backend().admin_unlog(
                    actor,
                    pending["start_date"],
                    pending["end_date"],
                    note=pending.get("note"),
                    dry_run=False,
                )
                text = (
                    f"Removed {len(result.get('applied') or [])} day(s). "
                    f"Streak: {result.get('streak_before')} → {result.get('streak_after')}."
                )
        else:
            return
    except Exception as e:
        if query.message:
            await query.edit_message_text(_error_text(e))
        return
    if query.message:
        await query.edit_message_text(text)


def setup_handlers(application: Application) -> None:
    """Register admin command and callback handlers."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(
        CommandHandler("reminder_status", reminder_status_command)
    )
    application.add_handler(
        CommandHandler("trigger_reminder", trigger_reminder_command)
    )
    application.add_handler(CommandHandler("patch", patch_command))
    application.add_handler(CommandHandler("unlog", unlog_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("shifts", shifts_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("audit", audit_command))
    application.add_handler(
        CallbackQueryHandler(admin_callback, pattern=r"^admin_(ok|no):")
    )


async def set_bot_commands(application: Application) -> None:
    """Set admin bot command menu in Telegram."""
    await application.bot.set_my_commands(COMMANDS)
