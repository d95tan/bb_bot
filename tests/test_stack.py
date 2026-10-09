"""Combined-stack helpers used by the TrueNAS single-container image CMD."""

import pytest

from src.stack import _wait_for_api


def test_wait_for_api_times_out_when_nothing_listens() -> None:
    with pytest.raises(RuntimeError, match="API did not become ready"):
        _wait_for_api(timeout_seconds=1)
