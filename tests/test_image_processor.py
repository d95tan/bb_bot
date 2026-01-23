"""Tests for image processor functions."""

import pytest

from src.services.image_processor import (
    _apply_prefix_normalization,
)


class TestPrefixNormalization:
    """Tests for _apply_prefix_normalization function."""

    def test_do_to_d0(self):
        """DO prefix should normalize to D0."""
        assert _apply_prefix_normalization("DOG8") == "D0G8"
        assert _apply_prefix_normalization("DOGG") == "D0GG"

    def test_eo_to_e0(self):
        """EO prefix should normalize to E0."""
        assert _apply_prefix_normalization("EOM8") == "E0M8"

    def test_bo_to_d0(self):
        """BO prefix should normalize to D0 (B misread as D)."""
        assert _apply_prefix_normalization("BOG8") == "D0G8"
        assert _apply_prefix_normalization("B0G8") == "D0G8"

    def test_short_codes_unchanged(self):
        """Codes with 2 or fewer characters should not be changed."""
        assert _apply_prefix_normalization("DO") == "DO"
        assert _apply_prefix_normalization("RD") == "RD"
        assert _apply_prefix_normalization("A") == "A"

    def test_normal_codes_unchanged(self):
        """Normal codes without prefix issues should not be changed."""
        assert _apply_prefix_normalization("D0G8") == "D0G8"
        assert _apply_prefix_normalization("N2111") == "N2111"
        assert _apply_prefix_normalization("RD") == "RD"
