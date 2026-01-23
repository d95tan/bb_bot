"""Development runner with auto-reload on file changes."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run the bot with auto-reload using watchfiles."""
    # Check if watchfiles is installed
    try:
        import watchfiles  # noqa: F401
    except ImportError:
        print("watchfiles not installed. Run: pip install watchfiles")
        sys.exit(1)

    print("🔄 Starting bot in development mode (auto-reload enabled)...")
    print("   Watching for changes in ./src and ./config")
    print("   Press Ctrl+C to stop.\n")

    # Use the current Python interpreter (from venv) for the subprocess
    python_path = sys.executable
    project_root = Path(__file__).parent.parent

    subprocess.run(
        [
            python_path, "-m", "watchfiles",
            "--filter", "python",
            f"{python_path} -m src.main",
            "src", "config"
        ],
        cwd=project_root,
    )


if __name__ == "__main__":
    main()
