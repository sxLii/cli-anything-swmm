"""SWMM network element management: nodes, links, subcatchments, raingages."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _data_lines(section_lines: list[str]) -> list[str]:
    """Return non-comment, non-empty lines from a section."""
    return [l for l in section_lines if l.strip() and not l.strip().startswith(";;")]


def _comment_lines(section_lines: list[str]) -> list[str]:
    """Return comment/empty lines from a section (the header)."""
    return [l for l in section_lines if not l.strip() or l.strip().startswith(";;")]


def _find_in_section(section_lines: list[str], name: str) -> int | None:
    """Return line index (in section_lines) of the entry with given name, or None."""
    for i, line in enumerate(section_lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(";;"):
            parts = stripped.split()
            if parts and parts[0] == name:
                return i
    return None


def _remove_from_section(section_lines: list[str], name: str) -> bool:
    """Remove the entry with the given name from section_lines in-place.

    Returns True if removed, False if not found.
    """
    idx = _find_in_section(section_lines, name)
    if idx is None:
        return False
    section_lines.pop(idx)
    return True


def _ensure_section(sections: dict[str, list[str]], name: str, header: list[str] | None = None) -> None:
    """Ensure a section exists in sections dict, creating it if needed."""
    if name not in sections:
        sections[name] = list(header or [])


# ---------------------------------------------------------------------------
# Junctions
# ---------------------------------------------------------------------------


def add_junction(
    sections: dict[str, list[str]],
    name: str,
    elevation: float,
    max_depth: float = 5.0,
    init_depth: float = 0.0,
    sur_depth: float = 0.0,
    aponded: float = 0.0,
) -> dict[str, Any]:
    """Add a junction node to the network.

    Args:
        sections: INP sections dict (modified in-place).
        name: Junction name (must be unique).
        elevation: Invert elevation (meters or feet).
        max_depth: Maximum water depth above invert.
        init_depth: Initial water depth.
        sur_depth: Additional surcharge depth allowed above crown.
        aponded: Area for ponded water when flooded.

    Returns:
        Dict describing the added junction.
    """
    _ensure_section(sections, "JUNCTIONS", [
        ";;Name           Elevation  MaxDepth   InitDepth  SurDepth   Aponded",
        ";;-------------- ---------- ---------- ---------- ---------- ----------",
    ])
    _ensure_section(sections, "COORDINATES", [
        ";;Node           X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ])

    line = f"{name:<16} {elevation:<10.3f} {max_depth:<10.3f} {init_depth:<10.3f} {sur_depth:<10.3f} {aponded:<10.3f}"
    sections["JUNCTIONS"].append(line)

    return {
        "name": name,
        "elevation": elevation,
        "max_depth": max_depth,
        "init_depth": init_depth,
        "sur_depth": sur_depth,
        "aponded": aponded,
        "type": "junction",
    }


def remove_junction(sections: dict[str, list[str]], name: str) -> bool:
    """Remove a junction by name.

    Args:
        sections: INP sections dict (modified in-place).
        name: Junction name.

    Returns:
        True if removed, False if not found.
    """
    removed = _remove_from_section(sections.get("JUNCTIONS", []), name)
    # Also remove from COORDINATES if present
    _remove_from_section(sections.get("COORDINATES", []), name)
    return removed


# ---------------------------------------------------------------------------
# Outfalls
# ---------------------------------------------------------------------------


def add_outfall(
    sections: dict[str, list[str]],
    name: str,
    elevation: float,
    outfall_type: str = "FREE",
    stage_data: str = "",
    gated: str = "NO",
    route_to: str = "",
) -> dict[str, Any]:
    """Add an outfall node.

    Args:
        sections: INP sections dict (modified in-place).
        name: Outfall name.
        elevation: Invert elevation.
        outfall_type: FREE, NORMAL, FIXED, TIDAL, TIMESERIES.
        stage_data: Stage data (for FIXED or TIMESERIES type).
        gated: YES/NO flap gate.
        route_to: Subcatchment to receive outfall flow (optional).

    Returns:
        Dict describing the added outfall.
    """
    _ensure_section(sections, "OUTFALLS", [
        ";;Name           Elevation  Type       Stage Data       Gated    Route To",
        ";;-------------- ---------- ---------- ---------------- -------- --------",
    ])
    _ensure_section(sections, "COORDINATES", [
        ";;Node           X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ])

    stage_col = stage_data if stage_data else ""
    route_col = route_to if route_to else ""
    line = f"{name:<16} {elevation:<10.3f} {outfall_type:<10} {stage_col:<16} {gated:<8} {route_col}"
    sections["OUTFALLS"].append(line.rstrip())

    return {
        "name": name,
        "elevation": elevation,
        "type": outfall_type,
        "gated": gated,
    }


# ---------------------------------------------------------------------------
# Storage nodes
# ---------------------------------------------------------------------------


def add_storage(
    sections: dict[str, list[str]],
    name: str,
    elevation: float,
    max_depth: float,
    init_depth: float = 0.0,
    shape: str = "TABULAR",
    curve_name: str = "",
    evap_frac: float = 0.0,
    psi: float = 0.0,
    ksat: float = 0.0,
    imd: float = 0.0,
) -> dict[str, Any]:
    """Add a storage unit node.

    Args:
        sections: INP sections dict (modified in-place).
        name: Storage unit name.
        elevation: Invert elevation.
        max_depth: Maximum water depth.
        init_depth: Initial water depth.
        shape: TABULAR or FUNCTIONAL.
        curve_name: Storage curve name (for TABULAR) or A1 coeff (for FUNCTIONAL).
        evap_frac: Fraction of evaporation applied.
        psi: Suction head for seepage (0 = no seepage).
        ksat: Saturated hydraulic conductivity for seepage.
        imd: Initial soil moisture deficit for seepage.

    Returns:
        Dict describing the added storage.
    """
    _ensure_section(sections, "STORAGE", [
        ";;Name           Elev.    MaxDepth   InitDepth  Shape      Curve Name/Params            N/A      Fevap    Psi      Ksat     IMD",
        ";;-------------- -------- ---------- ---------- ---------- ---------------------------- -------- -------- -------- -------- --------",
    ])

    curve_col = curve_name if curve_name else "0"
    line = (
        f"{name:<16} {elevation:<8.3f} {max_depth:<10.3f} {init_depth:<10.3f} "
        f"{shape:<10} {curve_col:<28} 0        {evap_frac:<8.3f} {psi:<8.3f} {ksat:<8.3f} {imd:<8.3f}"
    )
    sections["STORAGE"].append(line.rstrip())

    return {
        "name": name,
        "elevation": elevation,
        "max_depth": max_depth,
        "shape": shape,
        "type": "storage",
    }


# ---------------------------------------------------------------------------
# Conduits
# ---------------------------------------------------------------------------


def add_conduit(
    sections: dict[str, list[str]],
    name: str,
    from_node: str,
    to_node: str,
    length: float,
    roughness: float = 0.01,
    in_offset: float = 0.0,
    out_offset: float = 0.0,
    init_flow: float = 0.0,
    max_flow: float = 0.0,
    shape: str = "CIRCULAR",
    diameter: float = 1.0,
) -> dict[str, Any]:
    """Add a conduit (pipe) link to the network.

    Also adds a corresponding XSECTIONS entry.

    Args:
        sections: INP sections dict (modified in-place).
        name: Conduit name.
        from_node: Upstream node name.
        to_node: Downstream node name.
        length: Conduit length (m or ft).
        roughness: Manning's n roughness coefficient.
        in_offset: Upstream invert offset from node invert.
        out_offset: Downstream invert offset from node invert.
        init_flow: Initial flow rate.
        max_flow: Maximum flow rate (0 = unlimited).
        shape: Cross-section shape (CIRCULAR, RECT_CLOSED, TRAPEZOIDAL, ...).
        diameter: Full-height diameter or depth (for CIRCULAR/RECT_CLOSED).

    Returns:
        Dict describing the added conduit.
    """
    _ensure_section(sections, "CONDUITS", [
        ";;Name           From Node        To Node          Length     Roughness  InOffset   OutOffset  InitFlow   MaxFlow",
        ";;-------------- ---------------- ---------------- ---------- ---------- ---------- ---------- ---------- ----------",
    ])
    _ensure_section(sections, "XSECTIONS", [
        ";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert",
        ";;-------------- ------------ ---------------- ---------- ---------- ---------- ---------- ----------",
    ])

    conduit_line = (
        f"{name:<16} {from_node:<16} {to_node:<16} "
        f"{length:<10.3f} {roughness:<10.4f} {in_offset:<10.3f} "
        f"{out_offset:<10.3f} {init_flow:<10.3f} {max_flow:<10.3f}"
    )
    sections["CONDUITS"].append(conduit_line)

    xsec_line = f"{name:<16} {shape:<12} {diameter:<16.4f} 0          0          0          1"
    sections["XSECTIONS"].append(xsec_line)

    return {
        "name": name,
        "from_node": from_node,
        "to_node": to_node,
        "length": length,
        "roughness": roughness,
        "shape": shape,
        "diameter": diameter,
        "type": "conduit",
    }


def remove_conduit(sections: dict[str, list[str]], name: str) -> bool:
    """Remove a conduit (and its XSECTIONS entry) by name.

    Args:
        sections: INP sections dict (modified in-place).
        name: Conduit name.

    Returns:
        True if removed, False if not found.
    """
    removed = _remove_from_section(sections.get("CONDUITS", []), name)
    _remove_from_section(sections.get("XSECTIONS", []), name)
    return removed


# ---------------------------------------------------------------------------
# Subcatchments
# ---------------------------------------------------------------------------


def add_subcatchment(
    sections: dict[str, list[str]],
    name: str,
    raingage: str,
    outlet: str,
    area: float,
    pct_imperv: float = 50.0,
    width: float = 100.0,
    slope: float = 0.5,
    curb_len: float = 0.0,
    snow_pack: str = "",
    n_imperv: float = 0.01,
    n_perv: float = 0.1,
    s_imperv: float = 0.05,
    s_perv: float = 0.05,
    pct_zero: float = 25.0,
    max_rate: float = 3.0,
    min_rate: float = 0.5,
    decay: float = 4.14,
    dry_time: float = 7.0,
    max_infil: float = 0.0,
) -> dict[str, Any]:
    """Add a subcatchment with subareas and infiltration data.

    Args:
        sections: INP sections dict (modified in-place).
        name: Subcatchment name.
        raingage: Rain gage name providing rainfall.
        outlet: Outlet node or subcatchment name.
        area: Area (ha or acres).
        pct_imperv: % impervious.
        width: Characteristic width (m or ft).
        slope: Average slope (%).
        curb_len: Curb length (m or ft).
        snow_pack: Snow pack name (optional).
        n_imperv: Manning's n for impervious areas.
        n_perv: Manning's n for pervious areas.
        s_imperv: Depression storage on impervious areas (mm or in).
        s_perv: Depression storage on pervious areas (mm or in).
        pct_zero: % of impervious area with no depression storage.
        max_rate: Maximum Horton infiltration rate (mm/hr or in/hr).
        min_rate: Minimum Horton infiltration rate (mm/hr or in/hr).
        decay: Horton decay constant (1/hr).
        dry_time: Time to fully dry (days).
        max_infil: Maximum infiltration volume (0 = unlimited).

    Returns:
        Dict describing the added subcatchment.
    """
    _ensure_section(sections, "SUBCATCHMENTS", [
        ";;Name           Rain Gage  Outlet   Area     %Imperv  Width    %Slope   CurbLen  SnowPack",
        ";;-------------- ---------- -------- -------- -------- -------- -------- -------- --------",
    ])
    _ensure_section(sections, "SUBAREAS", [
        ";;Subcatchment   N-Imperv   N-Perv     S-Imperv   S-Perv     PctZero    RouteTo    PctRouted",
        ";;-------------- ---------- ---------- ---------- ---------- ---------- ---------- ----------",
    ])
    _ensure_section(sections, "INFILTRATION", [
        ";;Subcatchment   MaxRate    MinRate    Decay      DryTime    MaxInfil",
        ";;-------------- ---------- ---------- ---------- ---------- ----------",
    ])
    _ensure_section(sections, "POLYGONS", [
        ";;Subcatchment   X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ])

    snow_col = snow_pack if snow_pack else ""
    sub_line = (
        f"{name:<16} {raingage:<10} {outlet:<8} "
        f"{area:<8.3f} {pct_imperv:<8.1f} {width:<8.1f} "
        f"{slope:<8.2f} {curb_len:<8.1f} {snow_col}"
    )
    sections["SUBCATCHMENTS"].append(sub_line.rstrip())

    subarea_line = (
        f"{name:<16} {n_imperv:<10.3f} {n_perv:<10.3f} "
        f"{s_imperv:<10.3f} {s_perv:<10.3f} {pct_zero:<10.1f} OUTLET"
    )
    sections["SUBAREAS"].append(subarea_line)

    infil_line = (
        f"{name:<16} {max_rate:<10.3f} {min_rate:<10.3f} "
        f"{decay:<10.3f} {dry_time:<10.1f} {max_infil:<10.3f}"
    )
    sections["INFILTRATION"].append(infil_line)

    return {
        "name": name,
        "raingage": raingage,
        "outlet": outlet,
        "area": area,
        "pct_imperv": pct_imperv,
        "type": "subcatchment",
    }


# ---------------------------------------------------------------------------
# Raingages
# ---------------------------------------------------------------------------


def add_raingage(
    sections: dict[str, list[str]],
    name: str,
    timeseries: str = "",
    format_: str = "INTENSITY",
    interval: str = "0:05",
    scf: float = 1.0,
) -> dict[str, Any]:
    """Add a rain gage connected to a timeseries.

    The RAINGAGES section format is:
        Name  Format  Interval  SCF  Source

    Format values:
        INTENSITY   — Rainfall intensity (mm/hr or in/hr) — most common for timeseries
        VOLUME      — Rainfall volume (mm or in) per interval
        CUMULATIVE  — Cumulative rainfall depth

    The Source column specifies: TIMESERIES <name> for timeseries data.

    Args:
        sections: INP sections dict (modified in-place).
        name: Rain gage name.
        timeseries: Timeseries name providing rainfall data.
        format_: Data format (INTENSITY, VOLUME, CUMULATIVE).
                 Default is INTENSITY for timeseries-driven gages.
        interval: Recording interval (H:MM).
        scf: Snow catch factor.

    Returns:
        Dict describing the added rain gage.
    """
    # Normalize format — INTENSITY/VOLUME/CUMULATIVE are valid; TIMESERIES is a source keyword
    valid_formats = {"INTENSITY", "VOLUME", "CUMULATIVE"}
    fmt = format_.upper() if format_ else "INTENSITY"
    if fmt not in valid_formats:
        fmt = "INTENSITY"  # Default fallback

    _ensure_section(sections, "RAINGAGES", [
        ";;Name           Format    Interval  SCF       Source",
        ";;-------------- --------- --------- --------- ----------",
    ])
    _ensure_section(sections, "SYMBOLS", [
        ";;Gage           X-Coord            Y-Coord",
        ";;-------------- ------------------ ------------------",
    ])

    ts_col = f"TIMESERIES {timeseries}" if timeseries else "FILE \"rainfall.dat\" \"RG1\" IN"
    line = f"{name:<16} {fmt:<9} {interval:<9} {scf:<9.1f} {ts_col}"
    sections["RAINGAGES"].append(line)

    return {
        "name": name,
        "format": fmt,
        "interval": interval,
        "timeseries": timeseries,
        "scf": scf,
    }


# ---------------------------------------------------------------------------
# Pumps
# ---------------------------------------------------------------------------


def add_pump(
    sections: dict[str, list[str]],
    name: str,
    from_node: str,
    to_node: str,
    pump_curve: str = "*",
    status: str = "ON",
    startup_depth: float = 0.0,
    shutoff_depth: float = 0.0,
) -> dict[str, Any]:
    """Add a pump link between two nodes.

    Args:
        sections: INP sections dict (modified in-place).
        name: Pump name.
        from_node: Inlet (wet well) node name.
        to_node: Outlet node name.
        pump_curve: Pump curve name from [CURVES], or ``*`` for ideal pump.
        status: Initial status (``ON`` or ``OFF``).
        startup_depth: Node depth that turns the pump on (m or ft).
        shutoff_depth: Node depth that turns the pump off (m or ft).

    Returns:
        Dict describing the added pump.
    """
    _ensure_section(sections, "PUMPS", [
        ";;Name           From Node        To Node          Pump Curve       Status   Startup  Shutoff",
        ";;-------------- ---------------- ---------------- ---------------- -------- -------- --------",
    ])

    line = (
        f"{name:<16} {from_node:<16} {to_node:<16} "
        f"{pump_curve:<16} {status:<8} {startup_depth:<8.3f} {shutoff_depth:<8.3f}"
    )
    sections["PUMPS"].append(line.rstrip())

    return {
        "name": name,
        "from_node": from_node,
        "to_node": to_node,
        "pump_curve": pump_curve,
        "status": status,
        "startup_depth": startup_depth,
        "shutoff_depth": shutoff_depth,
        "type": "pump",
    }


def remove_pump(sections: dict[str, list[str]], name: str) -> bool:
    """Remove a pump by name.

    Args:
        sections: INP sections dict (modified in-place).
        name: Pump name.

    Returns:
        True if removed, False if not found.
    """
    return _remove_from_section(sections.get("PUMPS", []), name)


# ---------------------------------------------------------------------------
# Weirs
# ---------------------------------------------------------------------------


def add_weir(
    sections: dict[str, list[str]],
    name: str,
    from_node: str,
    to_node: str,
    weir_type: str = "TRANSVERSE",
    crest_height: float = 0.0,
    discharge_coeff: float = 3.33,
    gated: str = "NO",
    end_contractions: int = 0,
    end_coeff: float = 0.1,
    can_surcharge: str = "YES",
) -> dict[str, Any]:
    """Add a weir link between two nodes.

    Args:
        sections: INP sections dict (modified in-place).
        name: Weir name.
        from_node: Upstream node name.
        to_node: Downstream node name.
        weir_type: TRANSVERSE, SIDEFLOW, V-NOTCH, or TRAPEZOIDAL.
        crest_height: Offset height of weir crest above node invert (m or ft).
        discharge_coeff: Discharge coefficient.
        gated: YES/NO flap gate on weir opening.
        end_contractions: Number of end contractions (0-2).
        end_coeff: Discharge coefficient for triangular ends (TRAPEZOIDAL only).
        can_surcharge: YES/NO allow surcharging.

    Returns:
        Dict describing the added weir.
    """
    _ensure_section(sections, "WEIRS", [
        ";;Name           From Node        To Node          Type             CrestHt  Cd       Gated    EndCon   EndCoeff Surcharge",
        ";;-------------- ---------------- ---------------- ---------------- -------- -------- -------- -------- -------- ---------",
    ])

    line = (
        f"{name:<16} {from_node:<16} {to_node:<16} "
        f"{weir_type:<16} {crest_height:<8.3f} {discharge_coeff:<8.3f} "
        f"{gated:<8} {end_contractions:<8} {end_coeff:<8.3f} {can_surcharge}"
    )
    sections["WEIRS"].append(line.rstrip())

    return {
        "name": name,
        "from_node": from_node,
        "to_node": to_node,
        "type": weir_type,
        "crest_height": crest_height,
        "discharge_coeff": discharge_coeff,
        "gated": gated,
        "element_type": "weir",
    }


def remove_weir(sections: dict[str, list[str]], name: str) -> bool:
    """Remove a weir by name.

    Returns:
        True if removed, False if not found.
    """
    return _remove_from_section(sections.get("WEIRS", []), name)


# ---------------------------------------------------------------------------
# Orifices
# ---------------------------------------------------------------------------


def add_orifice(
    sections: dict[str, list[str]],
    name: str,
    from_node: str,
    to_node: str,
    orifice_type: str = "BOTTOM",
    offset: float = 0.0,
    discharge_coeff: float = 0.65,
    gated: str = "NO",
    close_time: float = 0.0,
) -> dict[str, Any]:
    """Add an orifice link between two nodes.

    Args:
        sections: INP sections dict (modified in-place).
        name: Orifice name.
        from_node: Upstream node name (typically a storage unit).
        to_node: Downstream node name.
        orifice_type: BOTTOM (bottom orifice) or SIDE (side orifice).
        offset: Offset of orifice centerline above node invert (m or ft).
        discharge_coeff: Discharge coefficient (typically 0.6–0.7).
        gated: YES/NO flap gate.
        close_time: Time to close a gated orifice (hours; 0 = instantaneous).

    Returns:
        Dict describing the added orifice.

    Note:
        An XSECTIONS entry (shape + geometry) must also be added for the orifice.
        This function adds a CIRCULAR cross-section of 1.0 m by default. Supply
        a custom cross-section by editing [XSECTIONS] directly afterwards.
    """
    _ensure_section(sections, "ORIFICES", [
        ";;Name           From Node        To Node          Type             Offset   Cd       Gated    CloseTime",
        ";;-------------- ---------------- ---------------- ---------------- -------- -------- -------- ----------",
    ])
    _ensure_section(sections, "XSECTIONS", [
        ";;Link           Shape        Geom1            Geom2      Geom3      Geom4      Barrels    Culvert",
        ";;-------------- ------------ ---------------- ---------- ---------- ---------- ---------- ----------",
    ])

    line = (
        f"{name:<16} {from_node:<16} {to_node:<16} "
        f"{orifice_type:<16} {offset:<8.3f} {discharge_coeff:<8.3f} "
        f"{gated:<8} {close_time:<10.1f}"
    )
    sections["ORIFICES"].append(line.rstrip())

    # Default circular cross-section (1 m diameter) — user can override
    xsec_line = f"{name:<16} CIRCULAR     {1.0:<16.4f} 0          0          0          1"
    sections["XSECTIONS"].append(xsec_line)

    return {
        "name": name,
        "from_node": from_node,
        "to_node": to_node,
        "type": orifice_type,
        "offset": offset,
        "discharge_coeff": discharge_coeff,
        "gated": gated,
        "element_type": "orifice",
    }


def remove_orifice(sections: dict[str, list[str]], name: str) -> bool:
    """Remove an orifice (and its XSECTIONS entry) by name.

    Returns:
        True if removed, False if not found.
    """
    removed = _remove_from_section(sections.get("ORIFICES", []), name)
    _remove_from_section(sections.get("XSECTIONS", []), name)
    return removed


# ---------------------------------------------------------------------------
# External inflows
# ---------------------------------------------------------------------------


def add_inflow(
    sections: dict[str, list[str]],
    node: str,
    timeseries: str,
    constituent: str = "FLOW",
    inflow_type: str = "FLOW",
    mfactor: float = 1.0,
    sfactor: float = 1.0,
    baseline: float = 0.0,
    pattern: str = "",
) -> dict[str, Any]:
    """Add an external inflow to a node from a timeseries.

    External inflows allow direct hydrograph or pollutograph inputs to any
    node in the network, bypassing the subcatchment rainfall-runoff model.

    Args:
        sections: INP sections dict (modified in-place).
        node: Node name receiving the inflow.
        timeseries: Timeseries name providing inflow magnitudes.
        constituent: Pollutant name or ``FLOW`` for a flow inflow.
        inflow_type: ``FLOW`` (direct flow in flow units) or ``CONCEN``
                     (concentration × flow) or ``MASS`` (mass rate).
        mfactor: Multiplier applied to timeseries values.
        sfactor: Scaling factor applied to timeseries values (baseline scaling).
        baseline: Constant baseline value added to scaled timeseries.
        pattern: Diurnal pattern name to scale the baseline (optional).

    Returns:
        Dict describing the added inflow.
    """
    _ensure_section(sections, "INFLOWS", [
        ";;Node           Constituent      Time Series      Type             Mfactor  Sfactor  Baseline Pattern",
        ";;-------------- ---------------- ---------------- ---------------- -------- -------- -------- --------",
    ])

    pattern_col = pattern if pattern else ""
    line = (
        f"{node:<16} {constituent:<16} {timeseries:<16} "
        f"{inflow_type:<16} {mfactor:<8.3f} {sfactor:<8.3f} {baseline:<8.3f} {pattern_col}"
    )
    sections["INFLOWS"].append(line.rstrip())

    return {
        "node": node,
        "constituent": constituent,
        "timeseries": timeseries,
        "type": inflow_type,
        "mfactor": mfactor,
        "sfactor": sfactor,
        "baseline": baseline,
    }


def remove_inflow(sections: dict[str, list[str]], node: str, constituent: str = "FLOW") -> bool:
    """Remove an inflow entry for a node/constituent pair.

    Args:
        sections: INP sections dict (modified in-place).
        node: Node name.
        constituent: Constituent name (default ``FLOW``).

    Returns:
        True if removed, False if not found.
    """
    inflow_lines = sections.get("INFLOWS", [])
    for i, line in enumerate(inflow_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(";;"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[0] == node and parts[1].upper() == constituent.upper():
            inflow_lines.pop(i)
            return True
    return False


# ---------------------------------------------------------------------------
# List network elements
# ---------------------------------------------------------------------------


def list_network(sections: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    """Return all nodes, links, and subcatchments in the network.

    Args:
        sections: INP sections dict.

    Returns:
        Dict with keys 'nodes', 'links', 'subcatchments', 'raingages'.
    """
    def _parse_section(section_lines: list[str], fields: list[str]) -> list[dict[str, Any]]:
        """Parse data lines into list of dicts."""
        result = []
        for line in section_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";;"):
                continue
            parts = stripped.split()
            item = {"name": parts[0]}
            for i, field in enumerate(fields[1:], 1):
                if i < len(parts):
                    item[field] = parts[i]
            result.append(item)
        return result

    nodes = []
    nodes.extend(_parse_section(
        sections.get("JUNCTIONS", []),
        ["name", "elevation", "max_depth", "init_depth", "sur_depth", "aponded"],
    ))
    for n in nodes:
        n["element_type"] = "junction"

    outfalls = _parse_section(
        sections.get("OUTFALLS", []),
        ["name", "elevation", "type"],
    )
    for n in outfalls:
        n["element_type"] = "outfall"
    nodes.extend(outfalls)

    storage = _parse_section(
        sections.get("STORAGE", []),
        ["name", "elevation", "max_depth", "init_depth", "shape"],
    )
    for n in storage:
        n["element_type"] = "storage"
    nodes.extend(storage)

    links = _parse_section(
        sections.get("CONDUITS", []),
        ["name", "from_node", "to_node", "length", "roughness"],
    )
    for l in links:
        l["element_type"] = "conduit"

    pumps = _parse_section(
        sections.get("PUMPS", []),
        ["name", "from_node", "to_node", "pump_curve", "status"],
    )
    for l in pumps:
        l["element_type"] = "pump"
    links.extend(pumps)

    weirs = _parse_section(
        sections.get("WEIRS", []),
        ["name", "from_node", "to_node", "type", "crest_height"],
    )
    for l in weirs:
        l["element_type"] = "weir"
    links.extend(weirs)

    orifices = _parse_section(
        sections.get("ORIFICES", []),
        ["name", "from_node", "to_node", "type", "offset"],
    )
    for l in orifices:
        l["element_type"] = "orifice"
    links.extend(orifices)

    subcatchments = _parse_section(
        sections.get("SUBCATCHMENTS", []),
        ["name", "raingage", "outlet", "area", "pct_imperv"],
    )
    for s in subcatchments:
        s["element_type"] = "subcatchment"

    raingages = _parse_section(
        sections.get("RAINGAGES", []),
        ["name", "format", "interval", "scf", "source"],
    )
    for r in raingages:
        r["element_type"] = "raingage"

    return {
        "nodes": nodes,
        "links": links,
        "subcatchments": subcatchments,
        "raingages": raingages,
    }
