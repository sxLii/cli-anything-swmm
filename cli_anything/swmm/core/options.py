"""SWMM simulation options management."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Options key normalization
# ---------------------------------------------------------------------------

_OPTION_ALIASES = {
    "start_date": "START_DATE",
    "start_time": "START_TIME",
    "end_date": "END_DATE",
    "end_time": "END_TIME",
    "report_start_date": "REPORT_START_DATE",
    "report_start_time": "REPORT_START_TIME",
    "flow_units": "FLOW_UNITS",
    "flow_routing": "FLOW_ROUTING",
    "routing": "FLOW_ROUTING",
    "infiltration": "INFILTRATION",
    "report_step": "REPORT_STEP",
    "wet_step": "WET_STEP",
    "dry_step": "DRY_STEP",
    "routing_step": "ROUTING_STEP",
    "allow_ponding": "ALLOW_PONDING",
    "inertial_damping": "INERTIAL_DAMPING",
    "variable_step": "VARIABLE_STEP",
    "min_slope": "MIN_SLOPE",
    "threads": "THREADS",
}

_VALID_FLOW_UNITS = {"CMS", "LPS", "CFS", "GPM", "MGD", "IMGD", "AFD"}
_VALID_ROUTING = {"DYNWAVE", "KINWAVE", "STEADYSTATE"}
_VALID_INFILTRATION = {"HORTON", "MODIFIED_HORTON", "GREEN_AMPT", "MODIFIED_GREEN_AMPT", "CURVE_NUMBER"}


def _normalize_key(key: str) -> str:
    """Normalize an option key to SWMM uppercase format."""
    lower = key.lower()
    return _OPTION_ALIASES.get(lower, key.upper())


def get_options(sections: dict[str, list[str]]) -> dict[str, str]:
    """Get current simulation options as a dict.

    Args:
        sections: INP sections dict.

    Returns:
        Dict of option_name -> value (all uppercase keys).
    """
    options: dict[str, str] = {}
    for line in sections.get("OPTIONS", []):
        stripped = line.strip()
        if stripped and not stripped.startswith(";;"):
            parts = stripped.split()
            if len(parts) >= 2:
                options[parts[0].upper()] = " ".join(parts[1:])
    return options


def set_options(sections: dict[str, list[str]], **kwargs: str) -> dict[str, str]:
    """Set simulation options.

    Any keyword argument will update the corresponding option. Common options:

        start_date: "MM/DD/YYYY" or "YYYY-MM-DD"
        end_date:   "MM/DD/YYYY" or "YYYY-MM-DD"
        start_time: "HH:MM:SS"
        end_time:   "HH:MM:SS"
        ! TODO: Set REPORT_START_DATE and REPORT_START_TIME to control when reporting begins (defaults to simulation start)
        flow_units: CMS | LPS | CFS | GPM | MGD | IMGD | AFD
        routing:    DYNWAVE | KINWAVE | STEADYSTATE
        report_step: "HH:MM:SS"
        routing_step: "H:MM:SS"

    Args:
        sections: INP sections dict (modified in-place).
        **kwargs: Option key-value pairs.

    Returns:
        Updated options dict.
    """
    def _normalize_date(val: str) -> str:
        """Convert YYYY-MM-DD to MM/DD/YYYY if needed."""
        val = val.strip()
        if len(val) == 10 and val[4] == "-":
            parts = val.split("-")
            if len(parts) == 3:
                return f"{parts[1]}/{parts[2]}/{parts[0]}"
        return val

    # Build current options dict
    current: dict[str, str] = {}
    comment_lines: list[str] = []
    for line in sections.get("OPTIONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";;"):
            comment_lines.append(line)
        else:
            parts = stripped.split()
            if len(parts) >= 2:
                current[parts[0].upper()] = " ".join(parts[1:])

    # Apply updates
    for key, val in kwargs.items():
        canonical = _normalize_key(key)
        val_str = str(val)

        # Normalize dates
        if canonical in ("START_DATE", "END_DATE", "REPORT_START_DATE"):
            val_str = _normalize_date(val_str)

        # Validate where possible
        if canonical == "FLOW_UNITS" and val_str.upper() not in _VALID_FLOW_UNITS:
            raise ValueError(f"Invalid FLOW_UNITS '{val_str}'. Must be one of: {sorted(_VALID_FLOW_UNITS)}")
        if canonical == "FLOW_ROUTING" and val_str.upper() not in _VALID_ROUTING:
            raise ValueError(f"Invalid FLOW_ROUTING '{val_str}'. Must be one of: {sorted(_VALID_ROUTING)}")

        current[canonical] = val_str.upper() if canonical in ("FLOW_UNITS", "FLOW_ROUTING", "INFILTRATION") else val_str

    # Rebuild OPTIONS section preserving comment header
    new_lines: list[str] = []
    seen_keys: set[str] = set()

    # Write back comments first (header)
    for line in sections.get("OPTIONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";;"):
            new_lines.append(line)
        else:
            # We'll rebuild data lines below
            break
    else:
        # All lines were comments/empty — no data lines found
        pass

    # Rebuild all option lines in a consistent order
    _KEY_ORDER = [
        "FLOW_UNITS", "INFILTRATION", "FLOW_ROUTING", "LINK_OFFSETS",
        "MIN_SLOPE", "ALLOW_PONDING", "SKIP_STEADY_STATE",
        "", # blank line
        "START_DATE", "START_TIME", "REPORT_START_DATE", "REPORT_START_TIME",
        "END_DATE", "END_TIME", "SWEEP_START", "SWEEP_END",
        "DRY_DAYS", "REPORT_STEP", "WET_STEP", "DRY_STEP", "ROUTING_STEP",
        "",
        "INERTIAL_DAMPING", "NORMAL_FLOW_LIMITED", "FORCE_MAIN_EQUATION",
        "VARIABLE_STEP", "LENGTHENING_STEP", "MIN_SURFAREA", "MAX_TRIALS",
        "HEAD_TOLERANCE", "SYS_FLOW_TOL", "LAT_FLOW_TOL", "MINIMUM_STEP", "THREADS",
    ]

    written: set[str] = set()
    for key in _KEY_ORDER:
        if key == "":
            new_lines.append("")
        elif key in current:
            new_lines.append(f"{key:<20} {current[key]}")
            written.add(key)

    # Append any remaining keys not in canonical order
    for key, val in current.items():
        if key not in written:
            new_lines.append(f"{key:<20} {val}")

    sections["OPTIONS"] = new_lines
    return get_options(sections)


def set_simulation_dates(
    sections: dict[str, list[str]],
    start_date: str,
    end_date: str,
    start_time: str = "00:00:00",
    end_time: str = "24:00:00",
) -> dict[str, str]:
    """Convenience wrapper to set simulation date range.

    Args:
        sections: INP sections dict (modified in-place).
        start_date: Start date in MM/DD/YYYY or YYYY-MM-DD format.
        end_date: End date in MM/DD/YYYY or YYYY-MM-DD format.
        start_time: Start time in HH:MM:SS format.
        end_time: End time in HH:MM:SS format.

    Returns:
        Updated options dict.
    """
    return set_options(
        sections,
        START_DATE=start_date,
        END_DATE=end_date,
        START_TIME=start_time,
        END_TIME=end_time,
        REPORT_START_DATE=start_date,
        REPORT_START_TIME=start_time,
    )
