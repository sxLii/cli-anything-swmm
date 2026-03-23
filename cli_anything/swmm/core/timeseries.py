"""SWMM timeseries management: rainfall data, synthetic events."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Raw timeseries manipulation
# ---------------------------------------------------------------------------


def add_timeseries(
    sections: dict[str, list[str]],
    name: str,
    data: list[tuple[str, str, float]],
) -> dict[str, Any]:
    """Add or replace a timeseries in the INP file.

    If a timeseries with the same name already exists, it is removed first.

    Args:
        sections: INP sections dict (modified in-place).
        name: Timeseries name (used in rain gages).
        data: List of (date, time, value) tuples.
              date format: "MM/DD/YYYY" or blank (uses previous date)
              time format: "H:MM" or "HH:MM"
              value: rainfall depth/intensity

    Returns:
        Dict with name and number of data points.
    """
    if "TIMESERIES" not in sections:
        sections["TIMESERIES"] = [
            ";;Name           Date       Time       Value",
            ";;-------------- ---------- ---------- ----------",
        ]

    # Remove existing entries with this name
    sections["TIMESERIES"] = [
        line for line in sections["TIMESERIES"]
        if line.strip().startswith(";;") or not line.strip()
        or line.strip().split()[0] != name
    ]

    # Add new data
    for date_str, time_str, value in data:
        line = f"{name:<16} {date_str:<10} {time_str:<10} {value}"
        sections["TIMESERIES"].append(line)

    return {"name": name, "points": len(data)}


def list_timeseries(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    """List all timeseries names and their data point counts.

    Args:
        sections: INP sections dict.

    Returns:
        List of dicts with 'name' and 'points' keys.
    """
    ts_map: dict[str, int] = {}
    for line in sections.get("TIMESERIES", []):
        stripped = line.strip()
        if stripped and not stripped.startswith(";;"):
            parts = stripped.split()
            if parts:
                name = parts[0]
                ts_map[name] = ts_map.get(name, 0) + 1

    return [{"name": k, "points": v} for k, v in ts_map.items()]


# ---------------------------------------------------------------------------
# Synthetic rainfall generation
# ---------------------------------------------------------------------------


def add_rainfall_event(
    sections: dict[str, list[str]],
    raingage_name: str,
    start_datetime: str,
    duration_hours: float,
    peak_intensity_mm_hr: float,
    pattern: str = "SCS",
    ts_name: str | None = None,
) -> dict[str, Any]:
    """Generate synthetic rainfall and add to TIMESERIES + RAINGAGES.

    Creates a synthetic storm and associates it with a rain gage.

    Args:
        sections: INP sections dict (modified in-place).
        raingage_name: Name of the rain gage to link the timeseries to.
        start_datetime: Storm start in "YYYY-MM-DD HH:MM" or "MM/DD/YYYY HH:MM" format.
        duration_hours: Total storm duration in hours.
        peak_intensity_mm_hr: Peak rainfall intensity in mm/hr.
        pattern: Rainfall distribution pattern:
            - "SCS": SCS Type II (peak at 60% of duration)
            - "UNIFORM": Constant intensity throughout
            - "TRIANGULAR": Linear increase to peak then decrease
        ts_name: Timeseries name. Defaults to "{raingage_name}_TS".

    Returns:
        Dict with timeseries name, data points, and total depth.
    """
    if ts_name is None:
        ts_name = f"{raingage_name}_TS"

    # Parse start datetime
    start = _parse_datetime(start_datetime)

    # Generate data points at 5-minute intervals
    interval_minutes = 5
    n_points = int(duration_hours * 60 / interval_minutes) + 1

    data: list[tuple[str, str, float]] = []
    total_depth = 0.0

    for i in range(n_points + 1):
        t_min = i * interval_minutes
        t_frac = t_min / (duration_hours * 60)  # 0..1

        intensity = _get_intensity(t_frac, peak_intensity_mm_hr, pattern)

        # Depth per interval = intensity * interval_hours
        interval_hours = interval_minutes / 60.0
        depth = intensity * interval_hours
        total_depth += depth

        dt = start + timedelta(minutes=t_min)
        date_str = dt.strftime("%m/%d/%Y")
        time_str = f"{dt.hour}:{dt.minute:02d}"

        data.append((date_str, time_str, round(intensity, 4)))

    # Add trailing zero if last point non-zero
    last_dt = start + timedelta(minutes=n_points * interval_minutes + interval_minutes)
    date_str = last_dt.strftime("%m/%d/%Y")
    time_str = f"{last_dt.hour}:{last_dt.minute:02d}"
    data.append((date_str, time_str, 0.0))

    # Add timeseries
    add_timeseries(sections, ts_name, data)

    # Update or add rain gage
    _update_raingage(sections, raingage_name, ts_name)

    return {
        "timeseries": ts_name,
        "raingage": raingage_name,
        "start": start_datetime,
        "duration_hours": duration_hours,
        "peak_mm_hr": peak_intensity_mm_hr,
        "pattern": pattern,
        "points": len(data),
        "total_depth_mm": round(total_depth, 2),
    }


def _parse_datetime(s: str) -> datetime:
    """Parse various datetime string formats."""
    s = s.strip()
    formats = [
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s!r}. Use 'YYYY-MM-DD HH:MM' or 'MM/DD/YYYY HH:MM'")


def _get_intensity(t_frac: float, peak: float, pattern: str) -> float:
    """Calculate rainfall intensity at normalized time t_frac (0..1).

    Args:
        t_frac: Time fraction from 0 (start) to 1 (end).
        peak: Peak intensity in mm/hr.
        pattern: Distribution pattern.

    Returns:
        Intensity in mm/hr.
    """
    if t_frac < 0 or t_frac > 1:
        return 0.0

    p = pattern.upper()

    if p == "UNIFORM":
        return peak if 0 < t_frac < 1 else 0.0

    elif p == "TRIANGULAR":
        # Ramp up to peak at midpoint, then ramp down
        if t_frac <= 0.5:
            return peak * (t_frac / 0.5)
        else:
            return peak * ((1.0 - t_frac) / 0.5)

    elif p == "SCS":
        # Approximate SCS Type II: peak at ~60% of duration
        # Use a beta-distribution-like curve
        peak_frac = 0.60
        if t_frac <= peak_frac:
            x = t_frac / peak_frac
            return peak * (3 * x**2 - 2 * x**3)  # smooth ramp
        else:
            x = (t_frac - peak_frac) / (1.0 - peak_frac)
            return peak * (1.0 - x)**2  # exponential decay

    else:
        # Default to triangular
        return _get_intensity(t_frac, peak, "TRIANGULAR")


def _update_raingage(
    sections: dict[str, list[str]],
    raingage_name: str,
    ts_name: str,
) -> None:
    """Update an existing rain gage's timeseries, or add a new one."""
    if "RAINGAGES" not in sections:
        sections["RAINGAGES"] = [
            ";;Name           Format    Interval  SCF       Source",
            ";;-------------- --------- --------- --------- ----------",
        ]

    # Remove existing entry for this gage
    sections["RAINGAGES"] = [
        line for line in sections["RAINGAGES"]
        if line.strip().startswith(";;") or not line.strip()
        or line.strip().split()[0] != raingage_name
    ]

    # Add updated entry — format is INTENSITY (mm/hr values), source is TIMESERIES <name>
    line = f"{raingage_name:<16} INTENSITY  0:05      1.0       TIMESERIES {ts_name}"
    sections["RAINGAGES"].append(line)
