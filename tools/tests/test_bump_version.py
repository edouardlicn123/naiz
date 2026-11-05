"""bump_version: compute_next_version pure-function logic (patch + minor)."""

import pytest

from naiz_build.bump_version import compute_next_version


# ---------------------------------------------------------------------------
# patch bump (default, no minor flag)
# ---------------------------------------------------------------------------

def test_patch_bump_simple():
    assert compute_next_version("0.1.001") == "0.1.002"


def test_patch_bump_zero_padding():
    assert compute_next_version("0.1.069") == "0.1.070"


def test_patch_bump_carries_leading_zeros():
    assert compute_next_version("0.2.099") == "0.2.100"


def test_patch_bump_two_digit_major():
    assert compute_next_version("10.5.007") == "10.5.008"


# ---------------------------------------------------------------------------
# minor bump (--minor flag)
# ---------------------------------------------------------------------------

def test_minor_bump_resets_patch():
    assert compute_next_version("0.1.069", minor=True) == "0.2.000"


def test_minor_bump_zeros_patch():
    assert compute_next_version("0.1.999", minor=True) == "0.2.000"


def test_minor_bump_from_zero():
    assert compute_next_version("0.0.000", minor=True) == "0.1.000"


def test_minor_bump_two_digit_minor():
    assert compute_next_version("0.9.123", minor=True) == "0.10.000"


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------

def test_malformed_version_rejected():
    with pytest.raises(ValueError):
        compute_next_version("0.1")


def test_non_numeric_patch_rejected():
    with pytest.raises(ValueError):
        compute_next_version("0.1.abc")


def test_patch_overflow_rejected():
    with pytest.raises(ValueError):
        compute_next_version("0.1.999")
