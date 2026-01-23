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
        self.load()

    def load(self) -> None:
        """Load shift configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Shift config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._code_mappings = data.get("code_mappings", {})
        self._color_fallbacks = data.get("color_fallbacks", {})

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
                return {"name": color_name, **shift}

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
