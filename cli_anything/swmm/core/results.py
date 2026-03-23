"""SWMM results parsing: .rpt report file parser."""

from __future__ import annotations

import os
import re
from typing import Any


# ---------------------------------------------------------------------------
# Report file parser
# ---------------------------------------------------------------------------


def parse_report(rpt_path: str) -> dict[str, Any]:
    """Parse a SWMM .rpt report file into a structured dict.

    Args:
        rpt_path: Path to the .rpt file.

    Returns:
        Dict with sections: 'header', 'summary', 'errors', 'warnings',
        'node_depth_summary', 'link_flow_summary', 'runoff_summary',
        'flow_routing_continuity', 'subcatch_runoff_summary'.

    Raises:
        FileNotFoundError: If the report file does not exist.
    """
    if not os.path.exists(rpt_path):
        raise FileNotFoundError(f"Report file not found: {rpt_path}")

    with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.splitlines()

    result: dict[str, Any] = {
        "rpt_path": os.path.abspath(rpt_path),
        "errors": [],
        "warnings": [],
        "header": {},
        "runoff_summary": {},
        "flow_routing_continuity": {},
        "node_depth_summary": {},
        "link_flow_summary": {},
        "subcatch_runoff_summary": [],
        "node_results_table": [],
        "link_results_table": [],
        "raw_sections": {},
    }

    # Extract errors and warnings
    for line in lines:
        lstrip = line.strip()
        if lstrip.lower().startswith("error"):
            result["errors"].append(lstrip)
        elif lstrip.lower().startswith("warning"):
            result["warnings"].append(lstrip)

    # Parse into named sections using the *** header pattern
    sections = _split_into_sections(lines)
    result["raw_sections"] = {k: v[:5] for k, v in sections.items()}  # truncate for display

    # Extract key tables
    result["runoff_summary"] = _parse_continuity_table(
        sections, "Runoff Quantity Continuity"
    )
    result["flow_routing_continuity"] = _parse_continuity_table(
        sections, "Flow Routing Continuity"
    )
    result["subcatch_runoff_summary"] = _parse_subcatch_runoff(sections)
    result["node_depth_summary"] = _parse_node_depth_summary(sections)
    result["link_flow_summary"] = _parse_link_flow_summary(sections)

    return result


def _normalize_section_key(title: str) -> str:
    """Normalize a section title for dictionary lookup."""
    return re.sub(r'\s+', ' ', title.strip()).lower()


def _split_into_sections(lines: list[str]) -> dict[str, list[str]]:
    """Split .rpt file into named sections.

    SWMM .rpt sections are delimited by lines of *** characters
    with a title between them:
        ******************
        Node Depth Summary
        ******************
    """
    sections: dict[str, list[str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect section header: a line of all * characters
        if stripped and all(c == '*' for c in stripped) and len(stripped) >= 4:
            # The title is the NEXT non-empty line
            title = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                title = lines[j].strip()
            # Check if next line after title is also all-*
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if (k < len(lines) and
                    lines[k].strip() and
                    all(c == '*' for c in lines[k].strip())):
                # This is a valid section header
                if current_name and current_lines:
                    sections[_normalize_section_key(current_name)] = current_lines

                current_name = title
                current_lines = []
                i = k + 1  # Skip past the closing ***
                continue

        if current_name is not None:
            current_lines.append(line)

        i += 1

    if current_name and current_lines:
        sections[_normalize_section_key(current_name)] = current_lines

    return sections


def _parse_continuity_table(
    sections: dict[str, list[str]], title: str
) -> dict[str, Any]:
    """Parse a continuity table with '...' separators."""
    key = _normalize_section_key(title)
    lines = sections.get(key, [])
    result: dict[str, Any] = {}

    for line in lines:
        stripped = line.strip()
        if "..." in stripped:
            # Format: "Label ...... value unit"
            parts = stripped.rsplit("...", 1)
            if len(parts) == 2:
                label = parts[0].strip().rstrip(".")
                remainder = parts[1].strip()
                tokens = remainder.split()
                if tokens:
                    try:
                        value = float(tokens[0])
                        result[label] = value
                    except ValueError:
                        result[label] = remainder

    return result


def _parse_subcatch_runoff(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Parse the Subcatchment Runoff Summary table."""
    key = _normalize_section_key("Subcatchment Runoff Summary")
    lines = sections.get(key, [])
    results = []
    in_data = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Data separator: line of dashes
        if re.match(r'^-{10,}', stripped):
            in_data = True
            continue
        if in_data and stripped:
            # Skip header lines (contain 'Subcatchment' keyword)
            if "Subcatchment" in stripped or "mm" in stripped or "Precip" in stripped:
                continue
            parts = stripped.split()
            if len(parts) >= 7:
                try:
                    results.append({
                        "subcatchment": parts[0],
                        "total_precip_mm": float(parts[1]),
                        "total_runon_mm": float(parts[2]),
                        "total_evap_mm": float(parts[3]),
                        "total_infil_mm": float(parts[4]),
                        "imperv_runoff_mm": float(parts[5]),
                        "perv_runoff_mm": float(parts[6]),
                        "total_runoff_mm": float(parts[7]) if len(parts) > 7 else 0.0,
                        "peak_runoff_cms": float(parts[9]) if len(parts) > 9 else 0.0,
                    })
                except (ValueError, IndexError):
                    pass

    return results


def _parse_node_depth_summary(sections: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Parse Node Depth Summary table."""
    key = _normalize_section_key("Node Depth Summary")
    lines = sections.get(key, [])
    results: dict[str, dict[str, Any]] = {}
    in_data = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Data separator: line of dashes
        if re.match(r'^-{10,}', stripped):
            in_data = True
            continue
        if in_data and stripped:
            # Skip header lines
            if any(kw in stripped for kw in ("Average", "Maximum", "Node", "Depth", "Type", "Meters")):
                continue
            parts = stripped.split()
            # Format: Name  Type  AvgDepth  MaxDepth  MaxHGL  Day  Time  ReportedMax
            if len(parts) >= 5:
                try:
                    name = parts[0]
                    node_type = parts[1] if len(parts) > 1 else ""
                    results[name] = {
                        "type": node_type,
                        "avg_depth": float(parts[2]) if len(parts) > 2 else 0.0,
                        "max_depth": float(parts[3]) if len(parts) > 3 else 0.0,
                        "max_hgl": float(parts[4]) if len(parts) > 4 else 0.0,
                        "time_max": f"{parts[5]}  {parts[6]}" if len(parts) > 6 else "",
                        "reported_max_depth": float(parts[7]) if len(parts) > 7 else 0.0,
                    }
                except (ValueError, IndexError):
                    pass

    return results


def _parse_link_flow_summary(sections: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Parse Link Flow Summary table."""
    key = _normalize_section_key("Link Flow Summary")
    lines = sections.get(key, [])
    results: dict[str, dict[str, Any]] = {}
    in_data = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Data separator
        if re.match(r'^-{10,}', stripped):
            in_data = True
            continue
        if in_data and stripped:
            # Skip header lines
            if any(kw in stripped for kw in ("Maximum", "Link", "Type", "CMS", "m/sec", "Flow", "Veloc")):
                continue
            parts = stripped.split()
            # Format: Name  Type  MaxFlow  Day  Time  MaxVeloc  MaxFullFlow  MaxFullDepth
            if len(parts) >= 5:
                try:
                    name = parts[0]
                    link_type = parts[1] if len(parts) > 1 else ""
                    results[name] = {
                        "type": link_type,
                        "max_flow": float(parts[2]) if len(parts) > 2 else 0.0,
                        "time_max": f"{parts[3]}  {parts[4]}" if len(parts) > 4 else "",
                        "max_velocity": float(parts[5]) if len(parts) > 5 else 0.0,
                        "max_full_flow_frac": float(parts[6]) if len(parts) > 6 else 0.0,
                        "max_full_depth_frac": float(parts[7]) if len(parts) > 7 else 0.0,
                    }
                except (ValueError, IndexError):
                    pass

    return results


# ---------------------------------------------------------------------------
# Targeted query functions
# ---------------------------------------------------------------------------


def get_node_results(rpt_path: str, node_name: str) -> dict[str, Any]:
    """Get summary results for a specific node from the report."""
    report = parse_report(rpt_path)
    node_data = report["node_depth_summary"].get(node_name, {})
    return {
        "node": node_name,
        "rpt_path": rpt_path,
        **node_data,
    }


def get_link_results(rpt_path: str, link_name: str) -> dict[str, Any]:
    """Get summary results for a specific link from the report."""
    report = parse_report(rpt_path)
    link_data = report["link_flow_summary"].get(link_name, {})
    return {
        "link": link_name,
        "rpt_path": rpt_path,
        **link_data,
    }


def get_runoff_summary(rpt_path: str) -> dict[str, Any]:
    """Get runoff quantity continuity summary."""
    report = parse_report(rpt_path)
    return {
        "rpt_path": rpt_path,
        "continuity": report["runoff_summary"],
        "subcatchments": report["subcatch_runoff_summary"],
    }


def get_flow_routing_summary(rpt_path: str) -> dict[str, Any]:
    """Get flow routing continuity summary."""
    report = parse_report(rpt_path)
    return {
        "rpt_path": rpt_path,
        "continuity": report["flow_routing_continuity"],
        "nodes": report["node_depth_summary"],
        "links": report["link_flow_summary"],
        "errors": report["errors"],
        "warnings": report["warnings"],
    }
