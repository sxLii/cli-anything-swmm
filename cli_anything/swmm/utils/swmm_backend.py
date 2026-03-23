"""SWMM backend: wraps pyswmm for simulation execution.

pyswmm IS the backend for EPA SWMM 5. It provides Python bindings
to the SWMM5 engine shared library (libswmm5.so / swmm5.dll).
"""

from __future__ import annotations

from typing import Any


def find_pyswmm():
    """Locate and import pyswmm, raising a clear error if not installed.

    Returns:
        The pyswmm module.

    Raises:
        RuntimeError: If pyswmm is not installed.
    """
    try:
        import pyswmm
        return pyswmm
    except ImportError:
        raise RuntimeError(
            "pyswmm is not installed. Install with:\n"
            "  pip install pyswmm\n\n"
            "pyswmm provides Python bindings to the EPA SWMM 5 engine\n"
            "and is required for running simulations."
        )


def get_pyswmm_version() -> str:
    """Return the installed pyswmm version string.

    Returns:
        Version string, or 'not installed'.
    """
    try:
        import pyswmm
        return getattr(pyswmm, "__version__", "unknown")
    except ImportError:
        return "not installed"


def run_via_pyswmm(
    inp_path: str,
    rpt_path: str | None = None,
    binfile: str | None = None,
) -> dict[str, Any]:
    """Execute a SWMM simulation using pyswmm.Simulation.

    This is the primary execution path. pyswmm wraps the compiled
    SWMM 5 engine (libswmm5.so) and runs the full simulation.

    Args:
        inp_path: Path to the SWMM .inp input file.
        rpt_path: Path for the .rpt report output file.
        binfile: Path for the binary .out output file.

    Returns:
        Dict with execution results including error code and paths.
    """
    pyswmm = find_pyswmm()
    from pyswmm import Simulation

    kwargs: dict[str, str] = {}
    if rpt_path:
        kwargs["reportfile"] = rpt_path
    if binfile:
        kwargs["outputfile"] = binfile

    error_code = 0
    errors: list[str] = []

    try:
        with Simulation(inp_path, **kwargs) as sim:
            sim.execute()
            # pyswmm 2.x uses flow_routing_error / runoff_error instead of getError()
    except Exception as e:
        err_msg = str(e).strip()
        if err_msg:
            errors.append(err_msg)
        error_code = -1

    return {
        "error_code": error_code,
        "errors": errors,
        "backend": "pyswmm",
        "pyswmm_version": get_pyswmm_version(),
    }


def query_simulation_live(inp_path: str) -> dict[str, Any]:
    """Run a simulation with live data extraction at each timestep.

    Demonstrates the pyswmm step-by-step API for real-time monitoring.

    Args:
        inp_path: Path to the .inp file.

    Returns:
        Dict with time-series data for all nodes and links.
    """
    pyswmm = find_pyswmm()
    from pyswmm import Simulation, Nodes, Links, Subcatchments

    node_ts: dict[str, list[dict]] = {}
    link_ts: dict[str, list[dict]] = {}
    subcatch_ts: dict[str, list[dict]] = {}

    with Simulation(inp_path) as sim:
        nodes = Nodes(sim)
        links = Links(sim)
        subcatchments = Subcatchments(sim)

        for step in sim:
            t = sim.current_time

            for node in nodes:
                if node.nodeid not in node_ts:
                    node_ts[node.nodeid] = []
                node_ts[node.nodeid].append({
                    "time": str(t),
                    "depth": node.depth,
                    "head": node.head,
                    "inflow": node.total_inflow,
                    "flooding": node.flooding,
                })

            for link in links:
                if link.linkid not in link_ts:
                    link_ts[link.linkid] = []
                link_ts[link.linkid].append({
                    "time": str(t),
                    "flow": link.flow,
                    "depth": link.depth,
                    "velocity": link.velocity,
                })

            for sub in subcatchments:
                if sub.subcatchmentid not in subcatch_ts:
                    subcatch_ts[sub.subcatchmentid] = []
                subcatch_ts[sub.subcatchmentid].append({
                    "time": str(t),
                    "runoff": sub.runoff,
                    "rainfall": sub.rainfall,
                })

    return {
        "nodes": node_ts,
        "links": link_ts,
        "subcatchments": subcatch_ts,
    }
