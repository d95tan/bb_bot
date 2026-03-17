"""Configuration management for the Telegram Shift Bot."""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = Field(...,
                                    description="Telegram bot token from BotFather")
    telegram_user_ids: str = Field(
        ...,
        description="Comma-separated list of authorized Telegram user IDs"
    )

    @property
    def authorized_user_ids(self) -> list[int]:
        """Parse telegram_user_ids into a list of integers."""
        return [int(uid.strip()) for uid in self.telegram_user_ids.split(",") if uid.strip()]

    # Google Calendar
    google_client_id: str = Field(..., description="Google OAuth client ID")
    google_client_secret: str = Field(...,
                                      description="Google OAuth client secret")
    google_refresh_token: Optional[str] = Field(
        default=None,
        description="Google OAuth refresh token (obtained after first auth)"
    )
    google_calendar_id: str = Field(
        default="primary",
        description="Google Calendar ID to use"
    )

    # Timezone
    timezone: str = Field(
        default="Australia/Sydney",
        description="Timezone for calendar events"
    )

    # Feature flags
    enable_calendar_upload: bool = Field(
        default=True,
        description="Enable/disable actual calendar uploads (for testing OCR)"
    )
    debug_save_cells: bool = Field(
        default=False,
        description="Save cropped cell images to debug/ folder for debugging OCR"
    )
    color_only_mode: bool = Field(
        default=False,
        description="Use only color detection for shifts, skip OCR entirely"
    )
    wipe_calendar_before_upload: bool = Field(
        default=False,
        description="Delete all events in the month before uploading new ones (for development)"
    )

    # Reminder acknowledgment store (optional; if set, use Redis instead of file)
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis URL for shared reminder state (e.g. redis://localhost:6379/0). Enables multi-instance."
    )
    # How often the reminder job runs (seconds). This is what determines how often we check and send — job runs every N seconds.
    reminder_job_interval_seconds: int = Field(
        default=2700,
        description="Interval (seconds) between reminder job runs. We only check/send when the job runs (default 2700 = 45 min). Set lower in dev to test.",
    )
    # Throttle: after sending a reminder, we won't send the same one again for this many seconds (Redis slot TTL).
    reminder_sent_slot_ttl_seconds: int = Field(
        default=2700,
        description="TTL (seconds) for 'reminder sent' slot. Re-send the same reminder at most this often until acknowledged (default 2700 = 45 min).",
    )

    @property
    def is_calendar_configured(self) -> bool:
        """Check if Google Calendar is fully configured."""
        return bool(self.google_refresh_token)


class ShiftConfig:
    """Shift configuration with two-tier lookup: code mappings + color fallbacks."""

    def __init__(self, config_path: Path | str = "config/shifts.yaml") -> None:
        self.config_path = Path(config_path)
        self._code_mappings: dict = {}
        self._color_fallbacks: dict = {}
        self._shift_groups: dict = {}
        self.load()

    def load(self) -> None:
        """Load shift configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Shift config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_codes = data.get("code_mappings", {})
        self._code_mappings, self._code_to_category = self._flatten_code_mappings_with_categories(raw_codes)
        raw_colors = data.get("color_fallbacks", {})
        self._color_fallbacks, self._color_to_category = self._flatten_color_fallbacks_with_categories(raw_colors)
        self._shift_groups = data.get("shift_groups", {})
        self._name_to_group = self._build_name_to_group()

    @staticmethod
    def _is_shift_config(d: dict) -> bool:
        """True if d looks like a shift entry (has name/start/all_day/description)."""
        return isinstance(d, dict) and any(
            k in d for k in ("name", "start", "all_day", "description")
        )

    def _flatten_code_mappings_with_categories(self, raw: dict) -> tuple[dict, dict[str, str]]:
        """
        Flatten code_mappings to code -> config; also return code -> category name.
        Supports both flat (D0GG: {...}) and one level of categories (AM: { D0GG: {...}, ... }).
        """
        out: dict = {}
        code_to_category: dict[str, str] = {}
        for key, value in (raw or {}).items():
            if not isinstance(value, dict):
                continue
            if self._is_shift_config(value):
                out[key] = value
            else:
                category = key
                for sub_code, sub_val in value.items():
                    if isinstance(sub_val, dict) and self._is_shift_config(sub_val):
                        out[sub_code] = sub_val
                        code_to_category[sub_code] = category
        return out, code_to_category

    @staticmethod
    def _is_color_config(d: dict) -> bool:
        """True if d looks like a color fallback entry (has rgb_range or shift)."""
        return isinstance(d, dict) and ("rgb_range" in d or "shift" in d)

    def _flatten_color_fallbacks_with_categories(self, raw: dict) -> tuple[dict, dict[str, str]]:
        """
        Flatten color_fallbacks to color_name -> config; also return color_name -> category.
        Same structure as code_mappings: flat (light_green: {...}) or one level of categories (AM: { light_green: {...}, ... }).
        """
        out: dict = {}
        color_to_category: dict[str, str] = {}
        for key, value in (raw or {}).items():
            if not isinstance(value, dict):
                continue
            if self._is_color_config(value):
                out[key] = value
            else:
                category = key
                for sub_name, sub_val in value.items():
                    if isinstance(sub_val, dict) and self._is_color_config(sub_val):
                        out[sub_name] = sub_val
                        color_to_category[sub_name] = category
        return out, color_to_category

    @staticmethod
    def _normalize_shift_group(val: str | bool | None) -> str | None:
        """Return group key for reminder config. YAML may parse 'off' as bool False."""
        if val is None:
            return None
        if val is False:
            return "Off"
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    def _build_name_to_group(self) -> dict[str, str]:
        """
        Build mapping from shift display name (e.g. A1, Off, Nig) to group (AM, PM, Night, Off, etc.).
        Uses explicit shift_group on shift config if set; else category (code_mappings) or time-based.
        """
        name_to_group: dict[str, str] = {}
        for code, config in self._code_mappings.items():
            name = config.get("name")
            if not name:
                continue
            name = name.strip()
            explicit = self._normalize_shift_group(config.get("shift_group"))
            if explicit and self._get_group_config(explicit):
                name_to_group[name] = explicit
                continue
            if getattr(self, "_code_to_category", None):
                cat = self._code_to_category.get(code)
                if cat and self._get_group_config(cat):
                    name_to_group[name] = cat
                    continue
            shift_info = {
                "start": config.get("start"),
                "end": config.get("end"),
                "all_day": config.get("all_day", False),
                "same_day": config.get("same_day", True),
            }
            name_to_group[name] = self._classify_by_time(shift_info)
        for color_name, color_config in self._color_fallbacks.items():
            shift = color_config.get("shift", {})
            if not shift or color_config.get("skip", False):
                continue
            name = shift.get("name")
            if not name:
                continue
            name = name.strip()
            explicit = self._normalize_shift_group(shift.get("shift_group") or color_config.get("shift_group"))
            if explicit and self._get_group_config(explicit):
                name_to_group[name] = explicit
                continue
            if getattr(self, "_color_to_category", None):
                cat = self._color_to_category.get(color_name)
                if cat is not None:
                    if cat is False:
                        group_key = self._normalize_shift_group(cat)
                    else:
                        group_key = str(cat).strip() if isinstance(cat, str) and str(cat).strip() else None
                    if group_key and self._get_group_config(group_key):
                        name_to_group[name] = group_key
                        continue
            shift_info = {
                "start": shift.get("start"),
                "end": shift.get("end"),
                "all_day": shift.get("all_day", False),
                "same_day": shift.get("same_day", True),
            }
            name_to_group[name] = self._classify_by_time(shift_info)
        return name_to_group

    def reload(self) -> None:
        """Reload configuration from file."""
        self.load()

    @property
    def code_mappings(self) -> dict:
        """Get all code-to-shift mappings."""
        return self._code_mappings

    @property
    def color_fallbacks(self) -> dict:
        """Get all color-based fallback mappings."""
        return self._color_fallbacks

    def get_shift_by_code(self, code: str) -> dict | None:
        """
        Get shift info by code (primary lookup).
        Case-insensitive matching.
        """
        code_upper = code.upper().strip()
        for mapping_code, config in self._code_mappings.items():
            if mapping_code.upper() == code_upper:
                return {"name": mapping_code, **config}
        return None

    def get_shift_by_color(self, rgb: tuple[int, int, int]) -> dict | None:
        """
        Get shift info by color (fallback lookup).

        Args:
            rgb: Tuple of (red, green, blue) values (0-255)

        Returns:
            Shift info dict or None if no color match
        """
        r, g, b = rgb

        for color_name, color_config in self._color_fallbacks.items():
            rgb_range = color_config.get("rgb_range", {})
            r_range = rgb_range.get("r", [0, 255])
            g_range = rgb_range.get("g", [0, 255])
            b_range = rgb_range.get("b", [0, 255])

            if (
                r_range[0] <= r <= r_range[1] and
                g_range[0] <= g <= g_range[1] and
                b_range[0] <= b <= b_range[1]
            ):
                shift = color_config.get("shift", {})
                result = {"name": color_name, **shift}
                if color_config.get("skip", False):
                    result["skip"] = True
                return result

        return None

    def get_shift(self, code: str, fallback_rgb: tuple[int, int, int] | None = None) -> dict | None:
        """
        Get shift info with two-tier lookup.

        1. First tries code mapping
        2. Falls back to color detection if code not found

        Args:
            code: Shift code (e.g., "E0M8", "N2111")
            fallback_rgb: Optional RGB color tuple for fallback lookup

        Returns:
            Shift info dict or None
        """
        # Primary: try code lookup
        shift = self.get_shift_by_code(code)
        if shift:
            return shift

        # Secondary: try color fallback
        if fallback_rgb:
            shift = self.get_shift_by_color(fallback_rgb)
            if shift:
                # Add the original code to the shift info
                shift["original_code"] = code
                return shift

        return None

    def _get_off_group_config(self) -> dict:
        """Return the Off group config. Handles YAML parsing 'off' as bool False."""
        off = self._shift_groups.get("Off") or self._shift_groups.get("off")
        if off is not None and isinstance(off, dict):
            return off
        if self._shift_groups.get(False) is not None and isinstance(self._shift_groups[False], dict):
            return self._shift_groups[False]
        return next(
            (
                v
                for k, v in self._shift_groups.items()
                if isinstance(v, dict) and (k is False or (isinstance(k, str) and k.lower() == "off"))
            ),
            {},
        )

    def _classify_by_time(self, shift_info: dict) -> str:
        """
        Classify by all_day, rest_day_after_night, then start time. Returns group key (AM, PM, Night, Off).
        """
        if shift_info.get("all_day"):
            return "Off"
        off_config = self._get_off_group_config()
        rest_start = off_config.get("rest_day_after_night_start")
        rest_end = off_config.get("rest_day_after_night_end")
        if rest_start is not None and rest_end is not None:
            start_str = shift_info.get("start")
            end_str = shift_info.get("end")
            if start_str is not None and end_str is not None:
                s = str(start_str).strip()
                e = str(end_str).strip()
                rs = str(rest_start).strip()
                re = str(rest_end).strip()
                if s == rs and e == re:
                    return "Off"
        start_str = shift_info.get("start", "09:00")
        parts = str(start_str).split(":")
        hour = int(parts[0]) if parts else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        start_minutes = hour * 60 + minute
        for group_id in ("AM", "PM", "Night"):
            group_config = self._shift_groups.get(group_id, {})
            start_before = group_config.get("start_before")
            start_from = group_config.get("start_from")
            if start_before and start_from is None:
                h, m = map(int, str(start_before).split(":"))
                if start_minutes < h * 60 + m:
                    return group_id
            elif start_from is not None:
                h, m = map(int, str(start_from).split(":"))
                lo = h * 60 + m
                hi = 24 * 60
                if start_before:
                    h2, m2 = map(int, str(start_before).split(":"))
                    hi = h2 * 60 + m2
                if lo <= start_minutes < hi:
                    return group_id
        return "Off"

    def get_shift_group(self, shift_info: dict) -> str:
        """
        Classify shift into group (AM, PM, Night, Off, Swing, etc.).
        Uses event name/summary when present and matched; otherwise time-based (AM/PM/Night/Off).
        """
        name = (shift_info.get("summary") or shift_info.get("name")) and str(shift_info.get("summary") or shift_info.get("name")).strip()
        if name and name in self._name_to_group:
            return self._name_to_group[name]
        return self._classify_by_time(shift_info)

    def _get_group_config(self, group_id: str) -> dict:
        """Return config for a group. Uses _get_off_group_config when group_id is Off (YAML may use key False)."""
        if isinstance(group_id, str) and group_id.lower() == "off":
            return self._get_off_group_config()
        return self._shift_groups.get(group_id, {})

    def get_reminder_offset_minutes(self, group_id: str) -> Optional[int]:
        """
        Offset in minutes from shift start when to send reminder.
        Positive = after start, negative = before start. None = no offset (use reminder_at if set).
        """
        group = self._get_group_config(group_id)
        val = group.get("reminder_offset_minutes")
        return int(val) if val is not None else None

    def get_off_day_reminder_at(self) -> Optional[str]:
        """
        Default fixed time (HH:MM) for off-day reminders (fallback when group has no reminder_at).
        From shift_groups.Off.reminder_at.
        """
        group = self._get_off_group_config()
        val = group.get("reminder_at")
        return str(val) if val is not None else None

    def get_reminder_at(self, group_id: str) -> Optional[str]:
        """
        Fixed time (HH:MM) to send reminder for this group, if set.
        From shift_groups.<group_id>.reminder_at. Use when reminder_offset_minutes is null.
        """
        group = self._get_group_config(group_id)
        val = group.get("reminder_at")
        return str(val) if val is not None else None

    def get_all_codes(self) -> list[str]:
        """Get list of all known shift codes."""
        return list(self._code_mappings.keys())

    def get_valid_characters(self) -> str:
        """Get all unique characters used in shift codes (for OCR whitelist)."""
        all_chars = set()
        for code in self._code_mappings.keys():
            all_chars.update(code.upper())
        # Always include digits 0-9 and colon (for time parsing)
        all_chars.update("0123456789:")
        return "".join(sorted(all_chars))

    def is_all_day_shift(self, shift_info: dict) -> bool:
        """Check if a shift is an all-day event."""
        return shift_info.get("all_day", False)

    def is_overnight_shift(self, shift_info: dict) -> bool:
        """Check if a shift spans overnight."""
        return not shift_info.get("same_day", True)


class GridConfig:
    """Grid boundary configuration for screenshot processing."""

    def __init__(self, config_path: Path | str = "config/grid.yaml") -> None:
        self.config_path = Path(config_path)
        self._config: dict = {}
        self.load()

    def load(self) -> None:
        """Load grid configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Grid config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

    def reload(self) -> None:
        """Reload configuration from file."""
        self.load()

    @property
    def grid_left_pct(self) -> float:
        """Left edge of grid as percentage of image width."""
        return self._config.get("grid_left_pct", 0.02)

    @property
    def grid_right_pct(self) -> float:
        """Right edge of grid as percentage of image width."""
        return self._config.get("grid_right_pct", 0.98)

    @property
    def grid_top_pct(self) -> Optional[float]:
        """Top edge of grid as percentage of image height (None for auto-detect)."""
        return self._config.get("grid_top_pct")

    @property
    def grid_bottom_pct(self) -> float:
        """Bottom edge of grid as percentage of image height."""
        return self._config.get("grid_bottom_pct", 0.85)

    @property
    def grid_top_fallback_pct(self) -> float:
        """Fallback top edge when auto-detection fails."""
        return self._config.get("grid_top_fallback_pct", 0.38)

    @property
    def header_height_pct(self) -> float:
        """Height of header region as percentage of image height."""
        return self._config.get("header_height_pct", 0.35)

    @property
    def header_left_pct(self) -> float:
        """Left edge of header region as percentage of image width."""
        return self._config.get("header_left_pct", 0.0)

    @property
    def header_right_pct(self) -> float:
        """Right edge of header region as percentage of image width."""
        return self._config.get("header_right_pct", 1.0)

    @property
    def header_top_pct(self) -> float:
        """Top edge of header region as percentage of image height."""
        return self._config.get("header_top_pct", 0.0)

    @property
    def header_bottom_pct(self) -> float:
        """Bottom edge of header region as percentage of image height."""
        return self._config.get("header_bottom_pct", 0.35)
    
    @property
    def crop_top_pct(self) -> float:
        """Percentage of cell height to remove from top."""
        return self._config.get("crop_top_pct", 0.05)

    @property
    def crop_bottom_pct(self) -> float:
        """Percentage of cell height to remove from bottom."""
        return self._config.get("crop_bottom_pct", 0.515)

    @property
    def grid_columns(self) -> int:
        """Number of columns in the grid (days per week)."""
        return self._config.get("grid_columns", 7)

    @property
    def grid_rows(self) -> int:
        """Number of rows in the grid (max weeks displayed)."""
        return self._config.get("grid_rows", 6)


# Global instances
_settings: Settings | None = None
_shift_config: ShiftConfig | None = None
_grid_config: GridConfig | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_shift_config() -> ShiftConfig:
    """Get or create shift config instance."""
    global _shift_config
    if _shift_config is None:
        _shift_config = ShiftConfig()
    return _shift_config


def get_grid_config() -> GridConfig:
    """Get or create grid config instance."""
    global _grid_config
    if _grid_config is None:
        _grid_config = GridConfig()
    return _grid_config
