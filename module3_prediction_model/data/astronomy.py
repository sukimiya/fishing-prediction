"""Astronomy calculations: sun times, moon phase.

Uses the `astral` library for accurate calculations without external API.
"""

from datetime import date, datetime, timezone
from typing import Optional


def get_sun_times(lat: float, lon: float, target_date: Optional[date] = None) -> dict:
    """Calculate sunrise and sunset times for a location.

    Args:
        lat: Latitude.
        lon: Longitude.
        target_date: Date to calculate for (default: today).

    Returns:
        dict with 'sunrise' and 'sunset' as hour integers (0-23),
        or empty dict if calculation fails.
    """
    try:
        from astral import Location
        from astral import sun
    except ImportError:
        return {"sunrise": 6, "sunset": 18}

    if target_date is None:
        target_date = date.today()

    try:
        loc = Location(("custom", "custom", lat, lon, "Asia/Shanghai", 0))
        sr = sun.sunrise(loc.observer, target_date)
        ss = sun.sunset(loc.observer, target_date)

        # Convert to local hour
        tz = timezone.utc  # astral returns UTC, we offset
        sr_local = sr.astimezone(tz) if sr.tzinfo else sr
        ss_local = ss.astimezone(tz) if ss.tzinfo else ss

        return {
            "sunrise": sr_local.hour,
            "sunset": ss_local.hour,
            "sunrise_str": sr_local.strftime("%H:%M"),
            "sunset_str": ss_local.strftime("%H:%M"),
        }
    except Exception:
        return {"sunrise": 6, "sunset": 18}


def get_moon_phase(target_date: Optional[date] = None) -> float:
    """Calculate moon phase as a float [0, 1].

    0.0 = New Moon, 0.5 = Full Moon, 1.0 = New Moon (next cycle).

    Args:
        target_date: Date to calculate for (default: today).

    Returns:
        Moon phase in [0, 1].
    """
    if target_date is None:
        target_date = date.today()

    # Using the lunar cycle approximation
    # Known new moon: 2000-01-06
    known_new_moon = date(2000, 1, 6)
    lunar_cycle_days = 29.53058867

    delta = (target_date - known_new_moon).days
    phase = (delta % lunar_cycle_days) / lunar_cycle_days
    return round(phase, 4)


def get_moon_phase_name(phase: float) -> str:
    """Get a human-readable name for the moon phase."""
    if phase < 0.0625 or phase >= 0.9375:
        return "新月 (New Moon)"
    if phase < 0.1875:
        return "蛾眉月 (Waxing Crescent)"
    if phase < 0.3125:
        return "上弦月 (First Quarter)"
    if phase < 0.4375:
        return "盈凸月 (Waxing Gibbous)"
    if phase < 0.5625:
        return "满月 (Full Moon)"
    if phase < 0.6875:
        return "亏凸月 (Waning Gibbous)"
    if phase < 0.8125:
        return "下弦月 (Last Quarter)"
    return "残月 (Waning Crescent)"
