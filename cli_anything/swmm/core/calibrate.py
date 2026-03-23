"""SWMM model calibration: parameter sensitivity, multi-run optimization, metric computation.

Calibration workflow
--------------------
1. Load observed time-series data (CSV: datetime,value).
2. Define calibration parameters with min/max bounds.
3. Run either:
   - sensitivity analysis (one-at-a-time)
   - calibration (grid search or Latin Hypercube Sampling)
4. Compute NSE / RMSE / MAE / PBias vs. observed.
5. Optionally apply the best parameter set back to the .inp file.

All state is stored in a *calibration session* JSON file alongside the
project: ``<project_base>_calib.json``.

Supported parameter types and fields
--------------------------------------
subcatchment : %IMPERV, AREA, WIDTH, %SLOPE
subarea      : N-IMPERV, N-PERV, S-IMPERV, S-PERV
conduit      : ROUGHNESS, LENGTH
infiltration : MAXRATE, MINRATE, DECAY, DRYTIME
junction     : MAXDEPTH

Simulated variable specs
------------------------
  ``node:<name>:<var>``       where var ∈ {depth, total_inflow, overflow, head, lateral_inflow}
  ``link:<name>:<var>``       where var ∈ {flow, depth, velocity}
  ``subcatch:<name>:<var>``   where var ∈ {runoff, rainfall, infiltration_loss, evaporation_loss}
"""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import random
import shutil
import tempfile
import time as _time
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Parameter map: (type, field_lower) -> (SECTION_NAME, col_index)
# ---------------------------------------------------------------------------

PARAM_MAP: dict[tuple[str, str], tuple[str, int]] = {
    ("subcatchment", "%imperv"):    ("SUBCATCHMENTS", 4),
    ("subcatchment", "area"):       ("SUBCATCHMENTS", 3),
    ("subcatchment", "width"):      ("SUBCATCHMENTS", 5),
    ("subcatchment", "%slope"):     ("SUBCATCHMENTS", 6),
    ("subarea", "n-imperv"):        ("SUBAREAS", 1),
    ("subarea", "n-perv"):          ("SUBAREAS", 2),
    ("subarea", "s-imperv"):        ("SUBAREAS", 3),
    ("subarea", "s-perv"):          ("SUBAREAS", 4),
    ("conduit", "roughness"):       ("CONDUITS", 4),
    ("conduit", "length"):          ("CONDUITS", 3),
    ("infiltration", "maxrate"):    ("INFILTRATION", 1),
    ("infiltration", "minrate"):    ("INFILTRATION", 2),
    ("infiltration", "decay"):      ("INFILTRATION", 3),
    ("infiltration", "drytime"):    ("INFILTRATION", 4),
    ("junction", "maxdepth"):       ("JUNCTIONS", 2),
}

VALID_NODE_VARS = {"depth", "total_inflow", "overflow", "head", "lateral_inflow"}
VALID_LINK_VARS = {"flow", "depth", "velocity"}
VALID_SUBCATCH_VARS = {"runoff", "rainfall", "infiltration_loss", "evaporation_loss"}


# ---------------------------------------------------------------------------
# Calibration session file
# ---------------------------------------------------------------------------

def _calib_path(inp_path: str) -> str:
    base = os.path.splitext(os.path.abspath(inp_path))[0]
    return base + "_calib.json"


def load_session(inp_path: str) -> dict[str, Any]:
    """Load or create a calibration session for the given .inp file."""
    path = _calib_path(inp_path)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "inp_path": os.path.abspath(inp_path),
        "observed": [],
        "params": [],
        "runs": [],
        "best": None,
    }


def save_session(session: dict[str, Any]) -> str:
    """Save the calibration session to its JSON file. Returns path."""
    inp_path = session["inp_path"]
    path = _calib_path(inp_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# Observed data
# ---------------------------------------------------------------------------

def load_observed_csv(csv_path: str) -> list[dict[str, Any]]:
    """Load observed data from a CSV file.

    Expected format (header on first row)::

        datetime,value
        2023-01-01 00:00,0.1
        2023-01-01 00:05,0.15

    Returns:
        List of {"datetime": <str>, "value": <float>} dicts, sorted by datetime.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV cannot be parsed.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Observed data file not found: {csv_path}")

    records: list[dict[str, Any]] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header row.")
        # Accept 'datetime' or 'date' or 'time' as the timestamp column
        ts_col = None
        val_col = None
        for col in reader.fieldnames:
            cl = col.strip().lower()
            if ts_col is None and cl in ("datetime", "date", "timestamp", "time"):
                ts_col = col
            if val_col is None and cl in ("value", "flow", "depth", "runoff", "obs"):
                val_col = col
        if ts_col is None or val_col is None:
            raise ValueError(
                f"CSV must have 'datetime' and 'value' columns. Found: {reader.fieldnames}"
            )
        for row in reader:
            try:
                val = float(row[val_col].strip())
                records.append({"datetime": row[ts_col].strip(), "value": val})
            except (ValueError, KeyError):
                pass  # skip malformed rows

    if not records:
        raise ValueError("No valid data rows found in CSV.")

    # Sort by datetime string (works when format is consistent)
    records.sort(key=lambda r: r["datetime"])
    return records


def add_observed(
    session: dict[str, Any],
    element_spec: str,
    data: list[dict[str, Any]],
    obs_id: str | None = None,
) -> dict[str, Any]:
    """Add or replace an observed dataset in the calibration session.

    Args:
        session:      Calibration session dict (modified in place).
        element_spec: Simulated variable to compare against, e.g. ``"node:J1:depth"``.
        data:         List of ``{"datetime": str, "value": float}`` records.
        obs_id:       Optional unique ID for this observation set; defaults to element_spec.

    Returns:
        Dict with summary info.
    """
    _validate_element_spec(element_spec)
    if obs_id is None:
        obs_id = element_spec

    # Remove existing entry with same id
    session["observed"] = [o for o in session["observed"] if o["id"] != obs_id]
    entry = {"id": obs_id, "element": element_spec, "data": data}
    session["observed"].append(entry)

    return {"id": obs_id, "element": element_spec, "n_points": len(data)}


def _validate_element_spec(spec: str) -> tuple[str, str, str]:
    """Validate and split an element spec like 'node:J1:depth'.

    Returns:
        (elem_type, elem_name, variable) tuple.

    Raises:
        ValueError: If the spec is malformed or the variable is unsupported.
    """
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid element spec: {spec!r}. Expected format: 'type:name:variable'"
        )
    elem_type, elem_name, variable = parts[0].lower(), parts[1], parts[2].lower()
    if elem_type == "node" and variable not in VALID_NODE_VARS:
        raise ValueError(
            f"Invalid node variable: {variable!r}. Choose from: {VALID_NODE_VARS}"
        )
    if elem_type == "link" and variable not in VALID_LINK_VARS:
        raise ValueError(
            f"Invalid link variable: {variable!r}. Choose from: {VALID_LINK_VARS}"
        )
    if elem_type == "subcatch" and variable not in VALID_SUBCATCH_VARS:
        raise ValueError(
            f"Invalid subcatch variable: {variable!r}. Choose from: {VALID_SUBCATCH_VARS}"
        )
    if elem_type not in ("node", "link", "subcatch"):
        raise ValueError(
            f"Invalid element type: {elem_type!r}. Choose from: node, link, subcatch"
        )
    return elem_type, elem_name, variable


# ---------------------------------------------------------------------------
# Parameter management
# ---------------------------------------------------------------------------

def add_param(
    session: dict[str, Any],
    param_type: str,
    name: str,
    field: str,
    min_val: float,
    max_val: float,
    nominal: float | None = None,
) -> dict[str, Any]:
    """Add a calibration parameter definition to the session.

    Args:
        session:    Calibration session dict.
        param_type: Element type: "subcatchment", "subarea", "conduit",
                    "infiltration", or "junction".
        name:       Element name (e.g., "C1", "S1") or "ALL" for all elements of that type.
        field:      Parameter field to calibrate (case-insensitive), e.g., "ROUGHNESS".
        min_val:    Minimum value.
        max_val:    Maximum value.
        nominal:    Nominal (baseline) value. Defaults to midpoint.

    Returns:
        Dict describing the added parameter.

    Raises:
        ValueError: If the param_type+field combination is unsupported.
    """
    key = (param_type.lower(), field.lower())
    if key not in PARAM_MAP:
        valid = [f"{t}:{f}" for t, f in PARAM_MAP]
        raise ValueError(
            f"Unsupported parameter: {param_type}:{field}. "
            f"Supported: {', '.join(valid)}"
        )
    if min_val >= max_val:
        raise ValueError(f"min_val ({min_val}) must be less than max_val ({max_val}).")

    if nominal is None:
        nominal = (min_val + max_val) / 2.0

    param_id = f"{param_type.lower()}:{name}:{field.lower()}"
    # Remove if already exists
    session["params"] = [p for p in session["params"] if p["id"] != param_id]

    entry = {
        "id": param_id,
        "type": param_type.lower(),
        "name": name,
        "field": field.upper(),
        "min": min_val,
        "max": max_val,
        "nominal": nominal,
    }
    session["params"].append(entry)
    return entry


# ---------------------------------------------------------------------------
# Parameter application (modify sections in-place)
# ---------------------------------------------------------------------------

def modify_param_in_sections(
    sections: dict[str, list[str]],
    param_type: str,
    elem_name: str,
    field: str,
    value: float,
) -> bool:
    """Set a single parameter value in a sections dict.

    Modifies `sections` in place.

    Args:
        sections:   INP sections dict (from parse_inp).
        param_type: "subcatchment", "subarea", "conduit", "infiltration", "junction".
        elem_name:  Element name, or "ALL" to modify every element in the section.
        field:      Field name (case-insensitive).
        value:      New numeric value.

    Returns:
        True if at least one element was modified, False if none found.
    """
    key = (param_type.lower(), field.lower())
    if key not in PARAM_MAP:
        raise ValueError(f"Unsupported parameter: {param_type}:{field}")

    section_name, col_idx = PARAM_MAP[key]
    section_lines = sections.get(section_name, [])
    modified = False

    for i, line in enumerate(section_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(";;"):
            continue
        parts = stripped.split()
        if not parts:
            continue
        row_name = parts[0]
        if elem_name.upper() != "ALL" and row_name != elem_name:
            continue
        if col_idx >= len(parts):
            continue

        # Replace the target column value
        parts[col_idx] = _fmt_float(value)
        # Re-join preserving alignment: simple space join
        section_lines[i] = "  " + "  ".join(parts)
        modified = True

    return modified


def _fmt_float(v: float) -> str:
    """Format a float for INP output (no unnecessary trailing zeros)."""
    if v == int(v):
        return str(int(v))
    return f"{v:.6g}"


def _apply_param_set(
    sections: dict[str, list[str]],
    param_defs: list[dict[str, Any]],
    values: list[float],
) -> None:
    """Apply a list of parameter values to a sections dict in place."""
    for param, val in zip(param_defs, values):
        modify_param_in_sections(
            sections,
            param["type"],
            param["name"],
            param["field"],
            val,
        )


# ---------------------------------------------------------------------------
# Simulated time-series collection via pyswmm
# ---------------------------------------------------------------------------

def collect_simulated_series(
    inp_path: str,
    element_spec: str,
) -> list[dict[str, Any]]:
    """Run a SWMM simulation and collect a time series for one element variable.

    Args:
        inp_path:     Path to the SWMM .inp file.
        element_spec: Variable spec, e.g. ``"node:J1:depth"``.

    Returns:
        List of ``{"datetime": str, "value": float}`` records.

    Raises:
        RuntimeError: If pyswmm is not installed.
        FileNotFoundError: If the .inp file does not exist.
    """
    if not os.path.exists(inp_path):
        raise FileNotFoundError(f"INP file not found: {inp_path}")

    try:
        from pyswmm import Simulation, Nodes, Links, Subcatchments
    except ImportError:
        raise RuntimeError(
            "pyswmm is not installed. Install with:\n  pip install pyswmm"
        )

    elem_type, elem_name, variable = _validate_element_spec(element_spec)

    # pyswmm attribute mapping
    _NODE_ATTR = {
        "depth": "depth",
        "total_inflow": "total_inflow",
        "overflow": "flooding",
        "head": "head",
        "lateral_inflow": "lateral_inflow",
    }
    _LINK_ATTR = {
        "flow": "flow",
        "depth": "depth",
        "velocity": "velocity",
    }
    _SUBCATCH_ATTR = {
        "runoff": "runoff",
        "rainfall": "rainfall",
        "infiltration_loss": "infiltration_loss",
        "evaporation_loss": "evaporation_loss",
    }

    series: list[dict[str, Any]] = []

    with Simulation(inp_path) as sim:
        if elem_type == "node":
            collector = Nodes(sim)[elem_name]
            attr = _NODE_ATTR[variable]
            for _ in sim:
                series.append({
                    "datetime": str(sim.current_time),
                    "value": getattr(collector, attr),
                })
        elif elem_type == "link":
            collector = Links(sim)[elem_name]
            attr = _LINK_ATTR[variable]
            for _ in sim:
                series.append({
                    "datetime": str(sim.current_time),
                    "value": getattr(collector, attr),
                })
        elif elem_type == "subcatch":
            collector = Subcatchments(sim)[elem_name]
            attr = _SUBCATCH_ATTR[variable]
            for _ in sim:
                series.append({
                    "datetime": str(sim.current_time),
                    "value": getattr(collector, attr),
                })

    return series


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    observed: list[dict[str, Any]],
    simulated: list[dict[str, Any]],
) -> dict[str, float]:
    """Compute calibration metrics between observed and simulated series.

    Both series are aligned by index (or by nearest-datetime matching if needed).
    Observed timestamps drive the alignment — simulated is interpolated to match.

    Args:
        observed:   List of ``{"datetime": str, "value": float}`` (reference).
        simulated:  List of ``{"datetime": str, "value": float}`` (model output).

    Returns:
        Dict with:
            - ``nse``   Nash-Sutcliffe Efficiency (higher is better; 1 = perfect)
            - ``rmse``  Root Mean Square Error (lower is better)
            - ``mae``   Mean Absolute Error (lower is better)
            - ``pbias`` Percent Bias in % (near 0 is best; + = underestimate, - = over)
            - ``n``     Number of comparison points

    Raises:
        ValueError: If there are fewer than 2 matching data points.
    """
    if not observed or not simulated:
        raise ValueError("Both observed and simulated series must be non-empty.")

    # Align: interpolate simulated to each observed timestamp
    sim_pairs = _parse_series(simulated)  # list of (datetime, value)
    obs_pairs = _parse_series(observed)

    if len(obs_pairs) < 2:
        raise ValueError("Need at least 2 observed data points to compute metrics.")

    obs_values = []
    sim_values = []

    for obs_t, obs_v in obs_pairs:
        sim_v = _interp_at(sim_pairs, obs_t)
        if sim_v is not None:
            obs_values.append(obs_v)
            sim_values.append(sim_v)

    n = len(obs_values)
    if n < 2:
        raise ValueError(
            f"Only {n} matching data point(s) after alignment. "
            "Check that observed and simulated time ranges overlap."
        )

    obs_mean = sum(obs_values) / n
    obs_sum = sum(obs_values)

    ss_res = sum((o - s) ** 2 for o, s in zip(obs_values, sim_values))
    ss_tot = sum((o - obs_mean) ** 2 for o in obs_values)

    nse = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else float("-inf")
    rmse = math.sqrt(ss_res / n)
    mae = sum(abs(o - s) for o, s in zip(obs_values, sim_values)) / n
    pbias = (
        100.0 * sum(o - s for o, s in zip(obs_values, sim_values)) / obs_sum
        if abs(obs_sum) > 1e-12
        else 0.0
    )

    return {
        "nse": round(nse, 6),
        "rmse": round(rmse, 6),
        "mae": round(mae, 6),
        "pbias": round(pbias, 4),
        "n": n,
    }


def _parse_series(
    series: list[dict[str, Any]],
) -> list[tuple[datetime, float]]:
    """Convert list of {datetime: str, value: float} to sorted list of (datetime, float)."""
    result = []
    for rec in series:
        dt_str = rec.get("datetime", "")
        val = rec.get("value", 0.0)
        try:
            dt = _parse_dt(dt_str)
            result.append((dt, float(val)))
        except (ValueError, TypeError):
            pass
    result.sort(key=lambda x: x[0])
    return result


def _parse_dt(s: str) -> datetime:
    """Parse a datetime string in several common formats."""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"Cannot parse datetime: {s!r}")


def _interp_at(
    pairs: list[tuple[datetime, float]],
    target: datetime,
) -> float | None:
    """Linear interpolation of series value at target datetime.

    Returns None if target is outside the series range.
    """
    if not pairs:
        return None
    if target <= pairs[0][0]:
        return pairs[0][1]
    if target >= pairs[-1][0]:
        return pairs[-1][1]

    # Binary search for the bracketing interval
    lo, hi = 0, len(pairs) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if pairs[mid][0] <= target:
            lo = mid
        else:
            hi = mid

    t0, v0 = pairs[lo]
    t1, v1 = pairs[hi]
    dt_total = (t1 - t0).total_seconds()
    if dt_total < 1e-6:
        return v0
    frac = (target - t0).total_seconds() / dt_total
    return v0 + frac * (v1 - v0)


# ---------------------------------------------------------------------------
# Parameter set generation
# ---------------------------------------------------------------------------

def _grid_samples(
    param_defs: list[dict[str, Any]],
    n_per_param: int,
) -> list[list[float]]:
    """Generate a full factorial grid of parameter values.

    Total samples = n_per_param ^ len(param_defs). Use with care for large
    numbers of parameters.
    """
    if not param_defs:
        return [[]]

    axes = []
    for p in param_defs:
        lo, hi = p["min"], p["max"]
        if n_per_param == 1:
            axes.append([p["nominal"]])
        else:
            step = (hi - lo) / (n_per_param - 1)
            axes.append([lo + i * step for i in range(n_per_param)])

    # Cartesian product
    result = [[]]
    for axis in axes:
        result = [prev + [v] for prev in result for v in axis]
    return result


def _lhs_samples(
    param_defs: list[dict[str, Any]],
    n_samples: int,
    seed: int = 42,
) -> list[list[float]]:
    """Generate Latin Hypercube samples.

    Each parameter's [min, max] is divided into n_samples equal strata.
    One sample is drawn from each stratum; strata are shuffled independently
    per parameter (no numpy required).
    """
    rng = random.Random(seed)
    cols = []
    for p in param_defs:
        lo, hi = p["min"], p["max"]
        width = (hi - lo) / n_samples
        intervals = [(lo + i * width, lo + (i + 1) * width) for i in range(n_samples)]
        rng.shuffle(intervals)
        col = [rng.uniform(a, b) for a, b in intervals]
        cols.append(col)

    # Transpose: cols[param][sample] -> samples[sample][param]
    return [list(row) for row in zip(*cols)] if cols else [[]] * n_samples


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------

def run_sensitivity(
    inp_path: str,
    session: dict[str, Any],
    n_steps: int = 5,
) -> list[dict[str, Any]]:
    """One-at-a-time (OAT) sensitivity analysis.

    For each calibration parameter, varies it across its [min, max] range in
    n_steps steps while holding all others at their nominal values. Runs a
    simulation for each step and computes metrics against each observed dataset.

    Args:
        inp_path:  Path to the base .inp file.
        session:   Calibration session dict (must have at least one param and one
                   observed dataset).
        n_steps:   Number of steps per parameter (default 5).

    Returns:
        List of sensitivity records::

            [
              {
                "param_id": "conduit:C1:ROUGHNESS",
                "value": 0.01,
                "element": "node:J1:depth",
                "metrics": {"nse": ..., "rmse": ..., "mae": ..., "pbias": ...}
              },
              ...
            ]

    Raises:
        ValueError: If no parameters or no observed data are defined in the session.
        FileNotFoundError: If the .inp file does not exist.
    """
    param_defs = session.get("params", [])
    observed_list = session.get("observed", [])

    if not param_defs:
        raise ValueError("No calibration parameters defined. Add params first.")
    if not observed_list:
        raise ValueError("No observed data defined. Add observed data first.")
    if not os.path.exists(inp_path):
        raise FileNotFoundError(f"INP file not found: {inp_path}")

    from cli_anything.swmm.core.project import parse_inp, write_inp

    records: list[dict[str, Any]] = []

    for target_param in param_defs:
        lo, hi = target_param["min"], target_param["max"]
        step_vals = []
        if n_steps == 1:
            step_vals = [target_param["nominal"]]
        else:
            span = hi - lo
            step_vals = [lo + span * i / (n_steps - 1) for i in range(n_steps)]

        for val in step_vals:
            # Build sections with all params at nominal, target at val
            base_sections = parse_inp(inp_path)
            # Apply nominals for all other params
            for p in param_defs:
                if p["id"] != target_param["id"]:
                    modify_param_in_sections(
                        base_sections, p["type"], p["name"], p["field"], p["nominal"]
                    )
            # Apply current step value for target param
            modify_param_in_sections(
                base_sections,
                target_param["type"],
                target_param["name"],
                target_param["field"],
                val,
            )

            with tempfile.NamedTemporaryFile(suffix=".inp", delete=False, mode="w") as tf:
                tmp_inp = tf.name
            try:
                write_inp(base_sections, tmp_inp)
                for obs in observed_list:
                    element_spec = obs["element"]
                    try:
                        sim_series = collect_simulated_series(tmp_inp, element_spec)
                        metrics = compute_metrics(obs["data"], sim_series)
                    except Exception as exc:
                        metrics = {"error": str(exc)}

                    records.append({
                        "param_id": target_param["id"],
                        "param_type": target_param["type"],
                        "param_name": target_param["name"],
                        "param_field": target_param["field"],
                        "value": val,
                        "element": element_spec,
                        "metrics": metrics,
                    })
            finally:
                if os.path.exists(tmp_inp):
                    os.unlink(tmp_inp)

    return records


# ---------------------------------------------------------------------------
# Calibration (multi-run optimization)
# ---------------------------------------------------------------------------

def run_calibration(
    inp_path: str,
    session: dict[str, Any],
    method: str = "lhs",
    n_samples: int = 20,
    metric: str = "nse",
    seed: int = 42,
) -> dict[str, Any]:
    """Run multi-parameter calibration.

    Generates ``n_samples`` parameter sets using ``method`` (grid or lhs),
    runs a SWMM simulation for each, computes metrics vs. all observed datasets,
    and returns the best-performing parameter set.

    Args:
        inp_path:  Path to the base .inp file.
        session:   Calibration session dict.
        method:    Sampling method: ``"grid"`` or ``"lhs"`` (default: ``"lhs"``).
        n_samples: Number of parameter sets to evaluate. For grid method, this
                   is treated as points per parameter axis.
        metric:    Objective function to optimise: ``"nse"`` (maximise),
                   ``"rmse"`` or ``"mae"`` (minimise).
        seed:      Random seed for reproducibility (LHS only).

    Returns:
        Dict with::

            {
              "best_params": {"conduit:C1:ROUGHNESS": 0.012, ...},
              "best_metrics": {"nse": 0.87, "rmse": ..., ...},
              "n_runs": 20,
              "method": "lhs",
              "all_runs": [...]
            }

    Raises:
        ValueError: If no parameters or observed data are defined, or if the
                    method is unknown.
    """
    param_defs = session.get("params", [])
    observed_list = session.get("observed", [])

    if not param_defs:
        raise ValueError("No calibration parameters defined.")
    if not observed_list:
        raise ValueError("No observed data defined.")
    if method not in ("grid", "lhs"):
        raise ValueError(f"Unknown method: {method!r}. Choose 'grid' or 'lhs'.")
    if metric not in ("nse", "rmse", "mae"):
        raise ValueError(f"Unknown metric: {metric!r}. Choose 'nse', 'rmse', or 'mae'.")

    from cli_anything.swmm.core.project import parse_inp, write_inp

    # Generate parameter sets
    if method == "grid":
        param_sets = _grid_samples(param_defs, n_samples)
    else:
        param_sets = _lhs_samples(param_defs, n_samples, seed=seed)

    # Determine better-is-higher for the chosen metric
    higher_is_better = metric == "nse"

    best_params: dict[str, float] | None = None
    best_score: float = float("-inf") if higher_is_better else float("inf")
    best_metrics: dict[str, Any] = {}
    all_runs: list[dict[str, Any]] = []

    for run_idx, values in enumerate(param_sets):
        # Build a temporary .inp with these parameter values
        base_sections = parse_inp(inp_path)
        _apply_param_set(base_sections, param_defs, values)

        with tempfile.NamedTemporaryFile(suffix=".inp", delete=False, mode="w") as tf:
            tmp_inp = tf.name
        try:
            write_inp(base_sections, tmp_inp)

            # Collect simulated series and compute metrics for each observed set
            run_metrics_list: list[dict[str, Any]] = []
            for obs in observed_list:
                element_spec = obs["element"]
                try:
                    sim_series = collect_simulated_series(tmp_inp, element_spec)
                    m = compute_metrics(obs["data"], sim_series)
                    run_metrics_list.append({"element": element_spec, "metrics": m})
                except Exception as exc:
                    run_metrics_list.append({"element": element_spec, "error": str(exc)})

        finally:
            if os.path.exists(tmp_inp):
                os.unlink(tmp_inp)

        # Aggregate metric across all observed sets (mean)
        scores = [
            rm["metrics"][metric]
            for rm in run_metrics_list
            if "metrics" in rm and metric in rm["metrics"]
        ]
        if not scores:
            agg_score = float("-inf") if higher_is_better else float("inf")
        else:
            agg_score = sum(scores) / len(scores)

        param_vals = {p["id"]: v for p, v in zip(param_defs, values)}

        run_record = {
            "run": run_idx,
            "params": param_vals,
            "observed_metrics": run_metrics_list,
            "aggregate_score": agg_score,
            "metric": metric,
        }
        all_runs.append(run_record)

        # Update best
        is_better = (
            agg_score > best_score if higher_is_better else agg_score < best_score
        )
        if is_better and math.isfinite(agg_score):
            best_score = agg_score
            best_params = param_vals
            best_metrics = {
                metric: agg_score,
                "run": run_idx,
                "observed_metrics": run_metrics_list,
            }

    result = {
        "best_params": best_params,
        "best_metrics": best_metrics,
        "n_runs": len(param_sets),
        "method": method,
        "metric": metric,
        "all_runs": all_runs,
    }

    # Persist best into session
    session["runs"].extend(all_runs)
    session["best"] = {"params": best_params, "metrics": best_metrics}

    return result


# ---------------------------------------------------------------------------
# Apply best parameters
# ---------------------------------------------------------------------------

def apply_best_params(
    inp_path: str,
    best_params: dict[str, float],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Write the best calibration parameters back into a .inp file.

    Args:
        inp_path:    Path to the source .inp file.
        best_params: Dict mapping param_id -> value,
                     e.g. ``{"conduit:C1:ROUGHNESS": 0.012}``.
        output_path: Where to write the calibrated .inp file.
                     Defaults to inp_path (overwrites in place).

    Returns:
        Dict with applied parameters and output path.

    Raises:
        FileNotFoundError: If inp_path does not exist.
        ValueError: If a param_id cannot be parsed.
    """
    if not os.path.exists(inp_path):
        raise FileNotFoundError(f"INP file not found: {inp_path}")

    from cli_anything.swmm.core.project import parse_inp, write_inp

    sections = parse_inp(inp_path)
    applied = []
    errors = []

    for param_id, value in best_params.items():
        parts = param_id.split(":", 2)
        if len(parts) != 3:
            errors.append(f"Cannot parse param_id: {param_id!r}")
            continue
        ptype, pname, pfield = parts
        try:
            ok = modify_param_in_sections(sections, ptype, pname, pfield, value)
            if ok:
                applied.append({"id": param_id, "value": value})
            else:
                errors.append(f"Element not found for {param_id}")
        except ValueError as e:
            errors.append(str(e))

    out = output_path or inp_path
    write_inp(sections, out)

    return {
        "output": os.path.abspath(out),
        "applied": applied,
        "errors": errors,
        "n_applied": len(applied),
    }
