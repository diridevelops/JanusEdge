"""Common validation helpers."""

import re


def is_valid_timezone(tz_string: str) -> bool:
    """
    Check if a timezone string is valid.

    Parameters:
        tz_string: A timezone string like 'America/New_York'.

    Returns:
        True if valid, False otherwise.
    """
    try:
        import pytz
        pytz.timezone(tz_string)
        return True
    except (pytz.UnknownTimeZoneError, AttributeError):
        return False


def is_valid_hex_color(color: str) -> bool:
    """
    Validate a hex color code string.

    Parameters:
        color: A string like '#FF5733'.

    Returns:
        True if valid hex color.
    """
    return bool(re.match(r'^#[0-9A-Fa-f]{6}$', color))
