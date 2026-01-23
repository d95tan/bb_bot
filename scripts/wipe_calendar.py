"""
Script to wipe all calendar events for a specific month.

Usage:
    python scripts/wipe_calendar.py
    
The script will prompt for month and year, then ask for confirmation
before deleting all events in that month.
"""

import asyncio
import sys
from datetime import date
from calendar import month_name

# Add project root to path
sys.path.insert(0, str(__file__).rsplit("scripts", 1)[0])

from src.services.calendar_service import CalendarService


def get_month_input() -> int:
    """Prompt for month (1-12)."""
    while True:
        try:
            month = int(input("Enter month (1-12): "))
            if 1 <= month <= 12:
                return month
            print("❌ Month must be between 1 and 12")
        except ValueError:
            print("❌ Please enter a valid number")


def get_year_input() -> int:
    """Prompt for year."""
    current_year = date.today().year
    while True:
        try:
            year = int(input(f"Enter year (e.g., {current_year}): "))
            if 2000 <= year <= 2100:
                return year
            print("❌ Year must be between 2000 and 2100")
        except ValueError:
            print("❌ Please enter a valid number")


def confirm_action(month: int, year: int) -> bool:
    """Ask for confirmation before wiping."""
    month_str = month_name[month]
    print(f"\n⚠️  WARNING: This will delete ALL calendar events for {month_str} {year}!")
    response = input("Type 'yes' to confirm: ").strip().lower()
    return response == "yes"


async def main() -> None:
    """Main entry point."""
    print("=" * 50)
    print("📅 Calendar Wipe Tool")
    print("=" * 50)
    print()
    
    # Get month and year
    month = get_month_input()
    year = get_year_input()
    
    # Confirm
    if not confirm_action(month, year):
        print("\n❌ Cancelled")
        return
    
    print()
    
    # Initialize calendar service
    try:
        calendar_service = CalendarService()
    except Exception as e:
        print(f"❌ Failed to initialize calendar service: {e}")
        print("\nMake sure your .env file has valid Google Calendar credentials.")
        return
    
    # Wipe the month
    try:
        deleted_count = await calendar_service.wipe_month(year, month)
        month_str = month_name[month]
        print(f"\n✅ Deleted {deleted_count} events from {month_str} {year}")
    except Exception as e:
        print(f"\n❌ Error wiping calendar: {e}")


if __name__ == "__main__":
    asyncio.run(main())
