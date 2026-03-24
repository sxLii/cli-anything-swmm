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

CHICAGO_DEFAULT_A = 25.0
CHICAGO_DEFAULT_C = 0.15
CHICAGO_DEFAULT_N = 0.70
CHICAGO_DEFAULT_B = 20.0
CHICAGO_DEFAULT_R = 0.37


def add_rainfall_event(
    sections: dict[str, list[str]],
    raingage_name: str,
    start_datetime: str,
    duration_hours: float,
    peak_intensity_mm_hr: float,
    pattern: str = "SCS",
    ts_name: str | None = None,
    timestep_minutes: float = 5,
    chicago_a: float | None = None,
    chicago_c: float | None = None,
    chicago_n: float | None = None,
    chicago_b: float | None = None,
    chicago_r: float | None = None,
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
            - "CHICAGO": Chicago ICM pattern (shape from a,c,n,b,r; scaled to peak)
        ts_name: Timeseries name. Defaults to "{raingage_name}_TS".
        timestep_minutes: Rainfall interval in minutes (must be positive integer).
        chicago_a: Chicago coefficient A.
        chicago_c: Chicago coefficient C.
        chicago_n: Chicago coefficient n.
        chicago_b: Chicago coefficient b.
        chicago_r: Chicago peak ratio r (0 < r < 1).

    Returns:
        Dict with timeseries name, data points, and total depth.
    """
    if ts_name is None:
        ts_name = f"{raingage_name}_TS"

    if duration_hours <= 0:
        raise ValueError("duration_hours must be > 0")
    if peak_intensity_mm_hr < 0:
        raise ValueError("peak_intensity_mm_hr must be >= 0")
    if timestep_minutes <= 0:
        raise ValueError("timestep_minutes must be > 0")
    if not float(timestep_minutes).is_integer():
        raise ValueError("timestep_minutes must be an integer number of minutes")

    interval_minutes = int(timestep_minutes)
    pattern_upper = pattern.upper()

    c_a = CHICAGO_DEFAULT_A if chicago_a is None else chicago_a
    c_c = CHICAGO_DEFAULT_C if chicago_c is None else chicago_c
    c_n = CHICAGO_DEFAULT_N if chicago_n is None else chicago_n
    c_b = CHICAGO_DEFAULT_B if chicago_b is None else chicago_b
    c_r = CHICAGO_DEFAULT_R if chicago_r is None else chicago_r

    if pattern_upper == "CHICAGO":
        if c_a <= 0 or c_n <= 0 or c_b <= 0:
            raise ValueError("CHICAGO parameters a, n, b must be > 0")
        if c_c < 0:
            raise ValueError("CHICAGO parameter c must be >= 0")
        if not 0 < c_r < 1:
            raise ValueError("CHICAGO parameter r must satisfy 0 < r < 1")

    # Parse start datetime
    start = _parse_datetime(start_datetime)

    storm_minutes = duration_hours * 60.0
    n_steps = max(1, int(math.ceil(storm_minutes / interval_minutes)))
    t_minutes = [min(i * interval_minutes, storm_minutes) for i in range(n_steps + 1)]

    chicago_raw: list[float] = [0.0] * len(t_minutes)
    if pattern_upper == "CHICAGO":
        cumulative = [
            _chicago_icm_cumulative_depth(
                t_frac=(t_min / storm_minutes) if storm_minutes > 0 else 0.0,
                duration_hours=duration_hours,
                a=c_a,
                c=c_c,
                n=c_n,
                b=c_b,
                r=c_r,
            )
            for t_min in t_minutes
        ]
        for i in range(1, len(t_minutes)):
            dt_hours = (t_minutes[i] - t_minutes[i - 1]) / 60.0
            if dt_hours <= 0:
                chicago_raw[i] = 0.0
            else:
                chicago_raw[i] = max(0.0, (cumulative[i] - cumulative[i - 1]) / dt_hours)

        max_raw = max(chicago_raw) if chicago_raw else 0.0
        chicago_scale = (peak_intensity_mm_hr / max_raw) if max_raw > 0 else 0.0
        chicago_raw = [v * chicago_scale for v in chicago_raw]

    data: list[tuple[str, str, float]] = []
    total_depth = 0.0

    for i, t_min in enumerate(t_minutes):
        t_frac = (t_min / storm_minutes) if storm_minutes > 0 else 0.0
        if pattern_upper == "CHICAGO":
            intensity = chicago_raw[i]
        else:
            intensity = _get_intensity(t_frac, peak_intensity_mm_hr, pattern_upper)

        if i > 0:
            dt_hours = (t_minutes[i] - t_minutes[i - 1]) / 60.0
            total_depth += intensity * dt_hours

        dt = start + timedelta(minutes=t_min)
        date_str = dt.strftime("%m/%d/%Y")
        time_str = f"{dt.hour}:{dt.minute:02d}"

        data.append((date_str, time_str, round(intensity, 4)))

    # Add trailing zero if last point non-zero
    last_dt = start + timedelta(minutes=t_minutes[-1] + interval_minutes)
    date_str = last_dt.strftime("%m/%d/%Y")
    time_str = f"{last_dt.hour}:{last_dt.minute:02d}"
    data.append((date_str, time_str, 0.0))

    # Add timeseries
    add_timeseries(sections, ts_name, data)

    # Update or add rain gage
    _update_raingage(sections, raingage_name, ts_name, interval_minutes)

    return {
        "timeseries": ts_name,
        "raingage": raingage_name,
        "start": start_datetime,
        "duration_hours": duration_hours,
        "peak_mm_hr": peak_intensity_mm_hr,
        "pattern": pattern_upper,
        "timestep_minutes": interval_minutes,
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

    if pattern == "UNIFORM":
        return peak if 0 < t_frac < 1 else 0.0

    elif pattern == "TRIANGULAR":
        # Ramp up to peak at midpoint, then ramp down
        if t_frac <= 0.5:
            return peak * (t_frac / 0.5)
        else:
            return peak * ((1.0 - t_frac) / 0.5)

    elif pattern == "SCS":
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
    interval_minutes: int = 5,
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

    interval_str = _format_interval(interval_minutes)

    # Add updated entry — format is INTENSITY (mm/hr values), source is TIMESERIES <name>
    line = f"{raingage_name:<16} INTENSITY  {interval_str:<9} 1.0       TIMESERIES {ts_name}"
    sections["RAINGAGES"].append(line)


def _format_interval(minutes: int) -> str:
    """Format integer minutes as H:MM for SWMM RAINGAGES interval."""
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}:{mins:02d}"


def _chicago_icm_cumulative_depth(
    t_frac: float,
    duration_hours: float,
    a: float,
    c: float,
    n: float,
    b: float,
    r: float,
) -> float:
    """Chicago ICM cumulative depth at normalized time t_frac (0..1)."""
    if t_frac <= 0:
        return 0.0
    if t_frac >= 1:
        t_frac = 1.0

    duration_minutes = duration_hours * 60.0
    t_minutes = t_frac * duration_minutes
    p = max(duration_hours, 1e-6)
    a_eff = a * (1.0 + c * math.log10(p))
    ht = a_eff * duration_minutes / (duration_minutes + b) ** n

    if t_minutes <= r * duration_minutes:
        term = 1.0 - t_minutes / (r * (duration_minutes + b))
        return ht * (r - (r - t_minutes / duration_minutes) * term ** (-n))

    term = 1.0 + (t_minutes - duration_minutes) / ((1.0 - r) * (duration_minutes + b))
    return ht * (r + (t_minutes / duration_minutes - r) * term ** (-n))
