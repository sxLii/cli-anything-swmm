"""SWMM project management: create, open, save, info, parse INP files."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Section order for canonical .inp files
# ---------------------------------------------------------------------------

_SECTION_ORDER = [
    "TITLE",
    "OPTIONS",
    "EVAPORATION",
    "RAINGAGES",
    "SUBCATCHMENTS",
    "SUBAREAS",
    "INFILTRATION",
    "LID_CONTROLS",
    "LID_USAGE",
    "AQUIFERS",
    "GROUNDWATER",
    "SNOWPACKS",
    "JUNCTIONS",
    "OUTFALLS",
    "DIVIDERS",
    "STORAGE",
    "CONDUITS",
    "PUMPS",
    "ORIFICES",
    "WEIRS",
    "OUTLETS",
    "XSECTIONS",
    "TRANSECTS",
    "LOSSES",
    "CONTROLS",
    "POLLUTANTS",
    "LANDUSES",
    "COVERAGES",
    "BUILDUP",
    "WASHOFF",
    "TREATMENT",
    "INFLOWS",
    "DWF",
    "RDII",
    "HYDROGRAPHS",
    "CURVES",
    "TIMESERIES",
    "PATTERNS",
    "REPORT",
    "TAGS",
    "MAP",
    "COORDINATES",
    "VERTICES",
    "POLYGONS",
    "SYMBOLS",
    "BACKDROP",
    "PROFILE",
    "FILE",
    "LABELS",
]

_REQUIRED_SECTIONS = [
    "TITLE",
    "OPTIONS",
    "RAINGAGES",
    "SUBCATCHMENTS",
    "SUBAREAS",
    "INFILTRATION",
    "JUNCTIONS",
    "OUTFALLS",
    "CONDUITS",
    "XSECTIONS",
    "TIMESERIES",
    "REPORT",
]


# ---------------------------------------------------------------------------
# INP Parser / Writer
# ---------------------------------------------------------------------------


def parse_inp(path: str) -> dict[str, list[str]]:
    """Parse a SWMM .inp file into a dict of {section_name: list_of_lines}.

    Lines are stored as raw strings (including comment lines starting with ;;).
    Section keys are uppercase, without brackets.

    Args:
        path: Path to the .inp file.

    Returns:
        Ordered dict mapping section names to lists of data lines.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file has no valid sections.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"INP file not found: {path}")

    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n").rstrip("\r")
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].upper()
                if current_section not in sections:
                    sections[current_section] = []
            elif current_section is not None:
                sections[current_section].append(line)

    return sections


def write_inp(sections: dict[str, list[str]], path: str) -> None:
    """Write sections dict back to an .inp file.

    Sections are written in canonical order (_SECTION_ORDER), then any
    additional sections not in the canonical list are appended.

    Args:
        sections: Dict of {section_name: list_of_lines}.
        path: Output file path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    # Build ordered list of sections
    ordered = []
    seen = set()
    for name in _SECTION_ORDER:
        if name in sections:
            ordered.append(name)
            seen.add(name)
    # Append any extras not in canonical order
    for name in sections:
        if name not in seen:
            ordered.append(name)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i, name in enumerate(ordered):
            if i > 0:
                f.write("\n")
            f.write(f"[{name}]\n")
            for line in sections[name]:
                f.write(line + "\n")


# ---------------------------------------------------------------------------
# Minimal valid INP template
# ---------------------------------------------------------------------------


def _make_default_sections(title: str, flow_units: str = "CMS") -> dict[str, list[str]]:
    """Build a minimal set of sections for a new project."""
    today = datetime.today().strftime("%m/%d/%Y")
    sections: dict[str, list[str]] = {}

    sections["TITLE"] = [
        f";;Project Title: {title}",
        f";;Created:       {today}",
    ]

    sections["OPTIONS"] = [
        ";;Option             Value",
        "FLOW_UNITS           " + flow_units,
        "INFILTRATION         HORTON",
        "FLOW_ROUTING         DYNWAVE",
        "LINK_OFFSETS         DEPTH",
        "MIN_SLOPE            0",
        "ALLOW_PONDING        NO",
        "SKIP_STEADY_STATE    NO",
        "",
        f"START_DATE           {today}",
        "START_TIME           00:00:00",
        f"REPORT_START_DATE    {today}",
        "REPORT_START_TIME    00:00:00",
        f"END_DATE             {today}",
        "END_TIME             06:00:00",
        "SWEEP_START          01/01",
        "SWEEP_END            12/31",
        "DRY_DAYS             0",
        "REPORT_STEP          00:05:00",
        "WET_STEP             00:05:00",
        "DRY_STEP             01:00:00",
        "ROUTING_STEP         0:00:30",
        "",
        "INERTIAL_DAMPING     PARTIAL",
        "NORMAL_FLOW_LIMITED  BOTH",
        "FORCE_MAIN_EQUATION  H-W",
        "VARIABLE_STEP        0.75",
        "LENGTHENING_STEP     0",
        "MIN_SURFAREA         1.167",
        "MAX_TRIALS           8",
        "HEAD_TOLERANCE       0.0015",
        "SYS_FLOW_TOL         5",
        "LAT_FLOW_TOL         5",
        "MINIMUM_STEP         0.5",
        "THREADS              1",
    ]

    sections["EVAPORATION"] = [
        ";;Data Source    Parameters",
        ";;-------------- ----------------",
        "CONSTANT         0.0",
        "DRY_ONLY         NO",
    ]

    sections["RAINGAGES"] = [
        ";;Name           Format     Interval  SCF       Source",
        ";;-------------- ---------- --------- --------- ----------",
    ]

    sections["SUBCATCHMENTS"] = [
        ";;Name           Rain Gage  Outlet   Area     %Imperv  Width    %Slope   CurbLen  SnowPack",
        ";;-------------- ---------- -------- -------- -------- -------- -------- -------- --------",
    ]

    sections["SUBAREAS"] = [
        ";;Subcatchment   N-Imperv   N-Perv     S-Imperv   S-Perv     PctZero    RouteTo    PctRouted",
        ";;-------------- ---------- ---------- ---------- ---------- ---------- ---------- ----------",
    ]

    sections["INFILTRATION"] = [
        ";;Subcatchment   MaxRate    MinRate    Decay      DryTime    MaxInfil",
        ";;-------------- ---------- ---------- ---------- ---------- ----------",
    ]

    sections["JUNCTIONS"] = [
        ";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded",
        ";;-------------- ---------- ---------- ---------- ---------- ----------",
    ]

    sections["OUTFALLS"] = [
        ";;Name           Elevation  Type       Stage Data       Gated    Route To",
        ";;-------------- ---------- ---------- ---------------- -------- --------",
    ]

    sections["CONDUITS"] = [
        ";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow",
        ";;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------",
    ]

    sections["XSECTIONS"] = [
        ";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert",
        ";;-------------- ------------ ---------------- ---------- ---------- ---------- ---------- ----------",
    ]

    sections["TIMESERIES"] = [
        ";;Name           Date       Time       Value",
        ";;-------------- ---------- ---------- ----------",
    ]

    sections["REPORT"] = [
        ";;Reporting Options",
        "SUBCATCHMENTS ALL",
        "NODES ALL",
        "LINKS ALL",
    ]

    sections["TAGS"] = []
    sections["MAP"] = [
        "DIMENSIONS 0.000 0.000 10000.000 10000.000",
        "Units      None",
    ]
    sections["COORDINATES"] = [
        ";;Node           X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ]
    sections["POLYGONS"] = [
        ";;Subcatchment   X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ]

    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_project(path: str, title: str, flow_units: str = "CMS") -> dict[str, Any]:
    """Create a new minimal valid .inp file.

    Args:
        path: Output path for the .inp file.
        title: Project title.
        flow_units: Flow unit system (CMS, LPS, CFS, GPM, MGD, IMGD, AFD).

    Returns:
        Dict with 'path', 'title', 'flow_units', 'sections' keys.
    """
    valid_units = {"CMS", "LPS", "CFS", "GPM", "MGD", "IMGD", "AFD"}
    if flow_units.upper() not in valid_units:
        raise ValueError(f"Invalid flow_units '{flow_units}'. Must be one of: {sorted(valid_units)}")

    sections = _make_default_sections(title, flow_units.upper())
    write_inp(sections, path)

    return {
        "path": os.path.abspath(path),
        "title": title,
        "flow_units": flow_units.upper(),
        "sections": list(sections.keys()),
    }


def open_project(path: str) -> dict[str, Any]:
    """Open and validate a SWMM .inp file.

    Args:
        path: Path to the .inp file.

    Returns:
        Dict with 'path', 'sections', and 'info' keys.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If required sections are missing.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project file not found: {path}")

    sections = parse_inp(path)

    # Check required sections
    missing = [s for s in _REQUIRED_SECTIONS if s not in sections]
    if missing:
        raise ValueError(f"INP file missing required sections: {missing}")

    info = project_info(path)

    return {
        "path": os.path.abspath(path),
        "sections": sections,
        "info": info,
    }


def save_project(sections: dict[str, list[str]], path: str) -> dict[str, Any]:
    """Write sections dict to a .inp file.

    Args:
        sections: Sections dict from parse_inp or create_project.
        path: Output path.

    Returns:
        Dict with 'path' and 'size' keys.
    """
    write_inp(sections, path)
    size = os.path.getsize(path)
    return {
        "path": os.path.abspath(path),
        "size": size,
    }


def project_info(path: str) -> dict[str, Any]:
    """Return a summary dict with counts of network elements.

    Args:
        path: Path to the .inp file.

    Returns:
        Dict with element counts, options, and metadata.
    """
    sections = parse_inp(path)

    def _count_data_lines(section_lines: list[str]) -> int:
        """Count non-comment, non-empty lines."""
        return sum(
            1 for line in section_lines
            if line.strip() and not line.strip().startswith(";;")
        )

    # Extract title
    title = ""
    for line in sections.get("TITLE", []):
        stripped = line.strip()
        if stripped and not stripped.startswith(";;"):
            title = stripped
            break
        if stripped.startswith(";;Project Title:"):
            title = stripped.replace(";;Project Title:", "").strip()
            break

    # Extract options
    options = {}
    for line in sections.get("OPTIONS", []):
        stripped = line.strip()
        if stripped and not stripped.startswith(";;"):
            parts = stripped.split()
            if len(parts) >= 2:
                options[parts[0]] = parts[1]

    return {
        "path": os.path.abspath(path),
        "title": title,
        "flow_units": options.get("FLOW_UNITS", ""),
        "junctions": _count_data_lines(sections.get("JUNCTIONS", [])),
        "outfalls": _count_data_lines(sections.get("OUTFALLS", [])),
        "storage": _count_data_lines(sections.get("STORAGE", [])),
        "conduits": _count_data_lines(sections.get("CONDUITS", [])),
        "subcatchments": _count_data_lines(sections.get("SUBCATCHMENTS", [])),
        "raingages": _count_data_lines(sections.get("RAINGAGES", [])),
        "timeseries": _count_data_lines(sections.get("TIMESERIES", [])),
        "sections": list(sections.keys()),
        "options": options,
    }
