"""SWMM simulation runner via pyswmm.

pyswmm 2.x API notes:
- Simulation.__init__(inputfile, reportfile=None, outputfile=None)
- sim.execute() — run the full simulation
- sim.flow_routing_error — continuity error % for flow routing
- sim.runoff_error — continuity error % for runoff
- sim.quality_error — continuity error % for water quality
- getError() does NOT exist in pyswmm 2.x
"""

from __future__ import annotations

import os
import time
import gc
import shutil
import tempfile
from typing import Any


def _release_swmm_file_handles() -> None:
    """Best-effort release for SWMM/DLL-backed file handles on Windows."""
    gc.collect()
    if os.name == "nt":
        time.sleep(0.05)


def _prepare_runtime_inp(inp_path: str) -> tuple[str, str | None]:
    """Return INP path for SWMM runtime and optional temp copy to clean up.

    On Windows, pyswmm/SWMM can transiently hold a handle on the INP file
    after simulation completes. Running against a temporary copy prevents
    locking the caller's project file.
    """
    if os.name != "nt":
        return inp_path, None

    with tempfile.NamedTemporaryFile(prefix="swmm_runtime_", suffix=".inp", delete=False) as tmp:
        runtime_inp = tmp.name
    shutil.copyfile(inp_path, runtime_inp)
    return runtime_inp, runtime_inp


def _cleanup_runtime_inp(path: str | None) -> None:
    """Best-effort cleanup for temporary runtime INP copy."""
    if not path:
        return
    for _ in range(5):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            time.sleep(0.05)


def _prepare_runtime_outputs(rpt_path: str, output_path: str) -> tuple[str, str, list[str]]:
    """Return report/output paths for simulation runtime and cleanup list."""
    if os.name != "nt":
        return rpt_path, output_path, []

    cleanup: list[str] = []
    with tempfile.NamedTemporaryFile(prefix="swmm_runtime_", suffix=".rpt", delete=False) as tmp_rpt:
        runtime_rpt = tmp_rpt.name
    with tempfile.NamedTemporaryFile(prefix="swmm_runtime_", suffix=".out", delete=False) as tmp_out:
        runtime_out = tmp_out.name
    cleanup.extend([runtime_rpt, runtime_out])
    return runtime_rpt, runtime_out, cleanup


def _get_pyswmm():
    """Import pyswmm, raising a clear error if not installed."""
    try:
        import pyswmm
        return pyswmm
    except ImportError:
        raise RuntimeError(
            "pyswmm is not installed. Install with:\n"
            "  pip install pyswmm"
        )


def validate_inp(inp_path: str) -> dict[str, Any]:
    """Validate a .inp file by attempting to open it with pyswmm.

    Opening the Simulation object triggers SWMM's input parsing.
    Any ERROR 200 (input errors) will raise an Exception.

    Args:
        inp_path: Path to the SWMM .inp file.

    Returns:
        Dict with 'valid' bool, 'errors' list, and 'warnings' list.
    """
    if not os.path.exists(inp_path):
        return {
            "valid": False,
            "errors": [f"File not found: {inp_path}"],
            "warnings": [],
        }

    _get_pyswmm()
    from pyswmm import Simulation
    runtime_inp, runtime_copy = _prepare_runtime_inp(inp_path)

    errors: list[str] = []
    warnings: list[str] = []

    try:
        with Simulation(runtime_inp) as sim:
            # Opening performs SWMM input validation
            # Check continuity errors if simulation runs
            try:
                sim.execute()
                # Check errors via continuity metrics
                if sim.flow_routing_error and abs(sim.flow_routing_error) > 10.0:
                    warnings.append(
                        f"High flow routing continuity error: {sim.flow_routing_error:.1f}%"
                    )
                if sim.runoff_error and abs(sim.runoff_error) > 10.0:
                    warnings.append(
                        f"High runoff continuity error: {sim.runoff_error:.1f}%"
                    )
            except Exception as sim_err:
                err_msg = str(sim_err).strip()
                if err_msg:
                    errors.append(err_msg)
    except Exception as e:
        err_msg = str(e).strip()
        if err_msg:
            errors.append(err_msg)
    finally:
        _release_swmm_file_handles()
        _cleanup_runtime_inp(runtime_copy)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "inp_path": os.path.abspath(inp_path),
    }


def run_simulation(
    inp_path: str,
    rpt_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Run a SWMM simulation using pyswmm.

    Args:
        inp_path: Path to the SWMM .inp file.
        rpt_path: Path for the output .rpt report file.
                  Defaults to inp_path with .rpt extension.
        output_path: Path for the binary output .out file.
                     Defaults to inp_path with .out extension.

    Returns:
        Dict with keys:
            - status: "success" or "error"
            - error_code: 0 for success, -1 for error
            - errors: list of error strings
            - warnings: list of warning strings
            - elapsed_time: simulation wall-clock time in seconds
            - flow_routing_error: continuity error %
            - runoff_error: runoff continuity error %
            - rpt_path: path to report file
            - output_path: path to binary output file
            - inp_path: absolute path to input file

    Raises:
        FileNotFoundError: If the .inp file does not exist.
        RuntimeError: If pyswmm is not installed.
    """
    if not os.path.exists(inp_path):
        raise FileNotFoundError(f"INP file not found: {inp_path}")

    _get_pyswmm()  # Ensure pyswmm is available
    from pyswmm import Simulation

    abs_inp = os.path.abspath(inp_path)
    runtime_inp, runtime_copy = _prepare_runtime_inp(abs_inp)

    # Determine output paths
    base = os.path.splitext(abs_inp)[0]
    if rpt_path is None:
        rpt_path = base + ".rpt"
    if output_path is None:
        output_path = base + ".out"

    # Ensure output directories exist
    for path in (rpt_path, output_path):
        dname = os.path.dirname(os.path.abspath(path))
        if dname:
            os.makedirs(dname, exist_ok=True)

    runtime_rpt, runtime_out, runtime_outputs = _prepare_runtime_outputs(
        os.path.abspath(rpt_path),
        os.path.abspath(output_path),
    )

    errors: list[str] = []
    warnings: list[str] = []
    error_code = 0
    flow_routing_err = None
    runoff_err = None

    start_wall = time.time()

    try:
        with Simulation(runtime_inp, reportfile=runtime_rpt, outputfile=runtime_out) as sim:
            sim.execute()
            # Check continuity errors
            try:
                flow_routing_err = sim.flow_routing_error
                runoff_err = sim.runoff_error
            except AttributeError:
                pass  # Older pyswmm versions may not have these
    except Exception as e:
        err_msg = str(e).strip()
        if err_msg:
            errors.append(err_msg)
        error_code = -1
    finally:
        _release_swmm_file_handles()

    # Copy runtime artifacts to requested target paths after handles are released.
    try:
        if runtime_rpt != os.path.abspath(rpt_path) and os.path.exists(runtime_rpt):
            shutil.copyfile(runtime_rpt, os.path.abspath(rpt_path))
        if runtime_out != os.path.abspath(output_path) and os.path.exists(runtime_out):
            shutil.copyfile(runtime_out, os.path.abspath(output_path))
    finally:
        _cleanup_runtime_inp(runtime_copy)
        for artifact in runtime_outputs:
            _cleanup_runtime_inp(artifact)

    elapsed = time.time() - start_wall

    status = "success" if not errors else "error"

    result = {
        "status": status,
        "error_code": error_code,
        "errors": errors,
        "warnings": warnings,
        "elapsed_time": round(elapsed, 3),
        "inp_path": abs_inp,
        "rpt_path": os.path.abspath(rpt_path),
        "output_path": os.path.abspath(output_path),
    }
    if flow_routing_err is not None:
        result["flow_routing_error"] = flow_routing_err
    if runoff_err is not None:
        result["runoff_error"] = runoff_err

    return result
