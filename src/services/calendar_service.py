"""Google Calendar integration service."""

import asyncio
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
    ) -> tuple[str, str]:
        """
        Create a calendar event for a shift.

        Args:
            shift_date: Date of the shift
            shift_info: Shift configuration including start, end, same_day, all_day

        Returns:
            Tuple of (event_id, status) where status is "created"
        """
        shift_name = shift_info.get("name", "Shift")

        # Build event based on shift type
        event = self._build_event_body(shift_date, shift_info, self.settings.timezone)

        try:
            # Run blocking Google API call in thread pool
            created_event = await asyncio.to_thread(
                self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event,
                ).execute
            )

            logger.info(f"Created calendar event: {shift_name} on {shift_date}")
            return created_event.get("id"), "created"

        except HttpError as e:
            logger.error(f"Failed to create calendar event: {e}")
            raise

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
            # Run blocking Google API call in thread pool
            events_result = await asyncio.to_thread(
                self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute
            )
            
            return events_result.get("items", [])
            
        except HttpError as e:
            logger.error(f"Failed to get calendar events: {e}")
            raise
    
    async def get_shifts_for_range(self, start_date: date, end_date: date) -> list[dict]:
        """Get all shift events within a date range."""
        time_min = datetime.combine(start_date, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"
        
        try:
            # Run blocking Google API call in thread pool
            events_result = await asyncio.to_thread(
                self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute
            )
            
            return events_result.get("items", [])
            
        except HttpError as e:
            logger.error(f"Failed to get calendar events: {e}")
            raise
    
    async def clear_date_range(
        self,
        start_date: date,
        end_date: date,
        preserve_overnight_from_previous: bool = True,
    ) -> int:
        """
        Delete all events in a date range before uploading new shifts.
        
        Args:
            start_date: First date to clear
            end_date: Last date to clear
            preserve_overnight_from_previous: If True, don't delete events that
                started on the day before start_date (e.g., night shifts)
                
        Returns:
            Number of events deleted
        """
        logger.info(f"Clearing calendar events from {start_date} to {end_date}")
        
        events = await self.get_shifts_for_range(start_date, end_date)
        
        deleted_count = 0
        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue
                
            # Check if we should preserve overnight events from previous day
            if preserve_overnight_from_previous:
                event_start = event.get("start", {})
                # Get the event's start date (handle both all-day and timed events)
                start_str = event_start.get("dateTime") or event_start.get("date")
                if start_str:
                    # Parse the date portion
                    event_start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00")).date()
                    if event_start_date < start_date:
                        logger.debug(f"Preserving overnight event from {event_start_date}: {event.get('summary')}")
                        continue
            
            try:
                await self.delete_event(event_id)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete event {event_id}: {e}")
        
        logger.info(f"Cleared {deleted_count} events from {start_date} to {end_date}")
        return deleted_count

    async def delete_event(self, event_id: str) -> None:
        """Delete a calendar event."""
        try:
            # Run blocking Google API call in thread pool
            await asyncio.to_thread(
                self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                ).execute
            )
            
            logger.debug(f"Deleted calendar event: {event_id}")
            
        except HttpError as e:
            logger.error(f"Failed to delete calendar event: {e}")
            raise

    async def wipe_month(self, year: int, month: int) -> int:
        """
        Delete all events in a specific month.
        
        Args:
            year: Year (e.g., 2025)
            month: Month (1-12)
            
        Returns:
            Number of events deleted
        """
        from calendar import monthrange
        
        # Get first and last day of month
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)
        
        logger.warning(f"Wiping calendar events for {year}-{month:02d}")
        
        # Get all events in the month
        events = await self.get_shifts_for_range(start_date, end_date)
        
        # Delete each event
        deleted_count = 0
        for event in events:
            event_id = event.get("id")
            if event_id:
                try:
                    await self.delete_event(event_id)
                    deleted_count += 1
                except HttpError as e:
                    logger.error(f"Failed to delete event {event_id}: {e}")
        
        logger.info(f"Deleted {deleted_count} events from {year}-{month:02d}")
        return deleted_count
