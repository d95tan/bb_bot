"""Application-wide constants."""

# Reminder service (Redis/file)
REMINDER_ACK_TTL_SECONDS = 48 * 3600  # 48h so acknowledgment keys expire

# Bound keys for header and grid dicts (image_processor, config)
HEADER_LEFT = "header_left"
HEADER_RIGHT = "header_right"
HEADER_TOP = "header_top"
HEADER_BOTTOM = "header_bottom"
GRID_LEFT = "grid_left"
GRID_RIGHT = "grid_right"
GRID_TOP = "grid_top"
GRID_BOTTOM = "grid_bottom"
