"""Google Calendar integration service."""

import logging
from datetime import date, datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import get_settings


logger = logging.getLogger(__name__)


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class CalendarService:
    """Google Calendar service for managing shift events."""
    
    def __init__(self) -> None:
        self.settings = get_settings()
        self._service = None
    
    @property
    def credentials(self) -> Credentials:
        """Get credentials from environment config."""
        if not self.settings.google_refresh_token:
            raise ValueError(
                "Google Calendar not configured. "
                "Run 'python -m src.auth_setup' to set up authorization."
            )
        
        return Credentials(
            token=None,
            refresh_token=self.settings.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.google_client_id,
            client_secret=self.settings.google_client_secret,
            scopes=SCOPES,
        )
    
    @property
    def service(self) -> build:
        """Get or create the Calendar API service."""
        if self._service is None:
            self._service = build("calendar", "v3", credentials=self.credentials)
        return self._service
    
    @property
    def calendar_id(self) -> str:
        """Get the calendar ID from settings."""
        return self.settings.google_calendar_id
    
    async def create_shift_event(
        self,
        shift_date: date,
        shift_info: dict,
        skip_existing: bool = True,
        overwrite_existing: bool = False,
    ) -> tuple[str, str]:
        """
        Create a calendar event for a shift.

        Args:
            shift_date: Date of the shift
            shift_info: Shift configuration including start, end, same_day, all_day
            skip_existing: If True, skip creating if event with same name exists
            overwrite_existing: If True, delete existing event before creating new one

        Returns:
            Tuple of (event_id, status) where status is "created", "skipped", or "updated"
        """
        shift_name = shift_info.get("name", "Shift")

        # Check for existing event with same name on same date
        existing_event = await self._find_existing_event(shift_date, shift_name)

        if existing_event:
            if skip_existing and not overwrite_existing:
                logger.info(f"Skipping existing event: {shift_name} on {shift_date}")
                return existing_event.get("id"), "skipped"

            if overwrite_existing:
                await self.delete_event(existing_event.get("id"))
                logger.info(f"Deleted existing event for overwrite: {shift_name} on {shift_date}")

        # Build event based on shift type
        event = self._build_event_body(shift_date, shift_info, self.settings.timezone)

        try:
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event,
            ).execute()

            status = "updated" if existing_event and overwrite_existing else "created"
            logger.info(f"{status.capitalize()} calendar event: {created_event.get('id')}")
            return created_event.get("id"), status

        except HttpError as e:
            logger.error(f"Failed to create calendar event: {e}")
            raise

    async def _find_existing_event(self, target_date: date, event_name: str) -> dict | None:
        """Find an existing event with the same name on a specific date."""
        events = await self.get_shifts_for_date(target_date)
        for event in events:
            if event.get("summary") == event_name:
                return event
        return None

    def _build_event_body(self, shift_date: date, shift_info: dict, timezone: str) -> dict:
        """Build the event body for Google Calendar API."""
        shift_name = shift_info.get("name", "Shift")
        description = shift_info.get("description", "")

        if shift_info.get("all_day"):
            # All-day event (Off, Annual Leave)
            return {
                "summary": shift_name,
                "description": description,
                "start": {
                    "date": shift_date.isoformat(),
                },
                "end": {
                    "date": (shift_date + timedelta(days=1)).isoformat(),
                },
            }

        # Timed event
        start_time = shift_info.get("start", "09:00")
        end_time = shift_info.get("end", "17:00")
        same_day = shift_info.get("same_day", True)

        # Parse times
        start_hour, start_min = map(int, start_time.split(":"))
        end_hour, end_min = map(int, end_time.split(":"))

        start_datetime = datetime.combine(
            shift_date,
            datetime.min.time().replace(hour=start_hour, minute=start_min)
        )

        if same_day:
            end_datetime = datetime.combine(
                shift_date,
                datetime.min.time().replace(hour=end_hour, minute=end_min)
            )
        else:
            # Overnight shift - ends next day
            end_datetime = datetime.combine(
                shift_date + timedelta(days=1),
                datetime.min.time().replace(hour=end_hour, minute=end_min)
            )

        return {
            "summary": shift_name,
            "description": description,
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": timezone,
            },
        }
    
    async def get_shifts_for_date(self, target_date: date) -> list[dict]:
        """Get all shift events for a specific date."""
        # Search for events on that date
        time_min = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"
        
        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            
            return events_result.get("items", [])
            
        except HttpError as e:
            logger.error(f"Failed to get calendar events: {e}")
            raise
    
    async def get_shifts_for_range(self, start_date: date, end_date: date) -> list[dict]:
        """Get all shift events within a date range."""
        time_min = datetime.combine(start_date, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"
        
        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            
            return events_result.get("items", [])
            
        except HttpError as e:
            logger.error(f"Failed to get calendar events: {e}")
            raise
    
    async def delete_event(self, event_id: str) -> None:
        """Delete a calendar event."""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            
            logger.info(f"Deleted calendar event: {event_id}")
            
        except HttpError as e:
            logger.error(f"Failed to delete calendar event: {e}")
            raise
