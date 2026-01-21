"""
One-time setup script to obtain Google OAuth refresh token.

Run this script once to authorize the bot and get a refresh token,
then add it to your .env file.

Usage:
    python -m src.auth_setup
"""

from google_auth_oauthlib.flow import InstalledAppFlow
from src.config import get_settings


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    """Run OAuth flow to get refresh token."""
    print("=" * 60)
    print("Google Calendar Authorization Setup")
    print("=" * 60)
    print()
    
    settings = get_settings()
    
    # Create OAuth flow
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            }
        },
        scopes=SCOPES,
    )
    
    # Run local server for OAuth callback
    print("A browser window will open for Google authorization.")
    print("Please sign in and grant access to your calendar.")
    print()
    
    try:
        credentials = flow.run_local_server(port=8080)
    except Exception:
        # Fallback to console-based auth if local server fails
        print("Local server failed. Using console-based authorization.")
        print()
        auth_url, _ = flow.authorization_url(prompt="consent")
        print(f"Please visit this URL to authorize:\n{auth_url}")
        print()
        code = input("Enter the authorization code: ").strip()
        flow.fetch_token(code=code)
        credentials = flow.credentials
    
    print()
    print("=" * 60)
    print("SUCCESS! Add this to your .env file:")
    print("=" * 60)
    print()
    print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()

