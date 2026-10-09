"""Run API, family bot, and admin bot in one container (TrueNAS Custom App)."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_LOCAL_API = "http://127.0.0.1:8000"
_API_WAIT_SECONDS = 60


def _wait_for_api(timeout_seconds: int = _API_WAIT_SECONDS) -> None:
    """
    Args:
     timeout_seconds(int): How long to wait for ``GET /health``.

    Raises:
     RuntimeError: When the API does not become ready in time.
    """
    deadline = time.monotonic() + timeout_seconds
    url = f"{_LOCAL_API}/health"
    last_error = "no attempt"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"API did not become ready at {url}: {last_error}")


def _stop_all(procs: list[subprocess.Popen[bytes]]) -> None:
    """
    Args:
     procs(list[subprocess.Popen[bytes]]): Child processes to terminate.
    """
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> None:
    """Start API, then family bot and admin bot, all in this container."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    os.environ["API_BASE_URL"] = _LOCAL_API
    logger.info("Starting combined stack (API_BASE_URL=%s)", _LOCAL_API)

    procs: list[subprocess.Popen[bytes]] = []
    stopping = False

    def _handle_stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        logger.info("Received signal %s; stopping children.", signum)
        stopping = True

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    try:
        procs.append(
            subprocess.Popen([sys.executable, "-m", "src.api.main"])
        )
        _wait_for_api()
        logger.info("API is ready.")
        procs.append(subprocess.Popen([sys.executable, "-m", "src.main"]))
        procs.append(
            subprocess.Popen([sys.executable, "-m", "src.admin_bot.main"])
        )

        while not stopping:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    logger.error("Child %s exited with %s", proc.args, code)
                    stopping = True
                    break
            else:
                time.sleep(1)
                continue
            break
    except Exception:
        logger.exception("Combined stack failed.")
        _stop_all(procs)
        sys.exit(1)

    _stop_all(procs)
    sys.exit(0)


if __name__ == "__main__":
    main()
