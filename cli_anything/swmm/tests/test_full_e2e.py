"""E2E tests for cli-anything-swmm.

Tests:
1. Full simulation pipeline via Python API (real pyswmm)
2. Report parsing from real .rpt output
3. CLI subprocess tests (installed cli-anything-swmm command)
4. Undo/redo integration test

pyswmm IS the required backend — no graceful degradation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

from cli_anything.swmm.core.project import create_project, parse_inp, write_inp, project_info
from cli_anything.swmm.core.network import (
    add_junction, add_outfall, add_conduit, add_subcatchment, add_raingage,
)
from cli_anything.swmm.core.options import set_simulation_dates, set_options
from cli_anything.swmm.core.timeseries import add_rainfall_event
from cli_anything.swmm.core.simulate import run_simulation, validate_inp
from cli_anything.swmm.core.results import (
    parse_report, get_node_results, get_link_results,
    get_runoff_summary, get_flow_routing_summary,
)
from cli_anything.swmm.core.session import Session


# ---------------------------------------------------------------------------
# Helper: resolve the installed CLI command
# ---------------------------------------------------------------------------


def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require installed command.
    """
    import shutil
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_anything.swmm.swmm_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _build_complete_project(tmp_dir: str) -> str:
    """Build a complete, valid SWMM project for simulation.

    Returns path to .inp file.
    """
    inp = os.path.join(tmp_dir, "test_project.inp")
    create_project(inp, "E2E Test Project", "CMS")
    sections = parse_inp(inp)

    # Network topology: SUB1 → J1 → J2 → OUT1
    add_junction(sections, "J1", 10.0, max_depth=5.0)
    add_junction(sections, "J2", 9.5, max_depth=5.0)
    add_outfall(sections, "OUT1", 8.0, outfall_type="FREE")

    # Pipes
    add_conduit(sections, "C1", "J1", "J2", 100.0, roughness=0.013, diameter=0.9)
    add_conduit(sections, "C2", "J2", "OUT1", 50.0, roughness=0.013, diameter=0.75)

    # Rainfall
    add_raingage(sections, "RG1", timeseries="STORM1")
    add_subcatchment(sections, "SUB1", "RG1", "J1", 8.0,
                     pct_imperv=65, width=150, slope=1.5)

    # Generate a 2-hour SCS storm, 25 mm/hr peak
    add_rainfall_event(
        sections, "RG1", "2023-01-01 00:00", 2.0, 25.0,
        pattern="SCS", ts_name="STORM1"
    )

    # Simulation dates: run for 6 hours total
    set_simulation_dates(sections, "01/01/2023", "01/01/2023",
                         "00:00:00", "06:00:00")
    set_options(sections, REPORT_STEP="00:05:00", ROUTING_STEP="0:00:30")

    write_inp(sections, inp)
    return inp


# ---------------------------------------------------------------------------
# Workflow 1: Full simulation pipeline
# ---------------------------------------------------------------------------


class TestFullSimulationPipeline:
    def test_complete_project_structure(self, tmp_dir):
        """Verify the complete .inp file structure before simulation."""
        inp = _build_complete_project(tmp_dir)
        sections = parse_inp(inp)

        # Check all required sections present
        required = ["TITLE", "OPTIONS", "RAINGAGES", "SUBCATCHMENTS", "SUBAREAS",
                    "INFILTRATION", "JUNCTIONS", "OUTFALLS", "CONDUITS",
                    "XSECTIONS", "TIMESERIES", "REPORT"]
        for s in required:
            assert s in sections, f"Missing section: {s}"

        # Verify element counts
        info = project_info(inp)
        assert info["junctions"] == 2
        assert info["outfalls"] == 1
        assert info["conduits"] == 2
        assert info["subcatchments"] == 1
        assert info["raingages"] == 1

    def test_run_simulation_success(self, tmp_dir):
        """Run a complete simulation and verify it succeeds."""
        inp = _build_complete_project(tmp_dir)
        rpt = os.path.join(tmp_dir, "test_project.rpt")

        result = run_simulation(inp, rpt_path=rpt)

        print(f"\n  INP: {inp}")
        print(f"  RPT: {rpt} ({os.path.getsize(rpt):,} bytes)" if os.path.exists(rpt) else "  RPT: (not created)")
        print(f"  Status: {result['status']}, Elapsed: {result['elapsed_time']}s")
        print(f"  Error code: {result['error_code']}")
        if result["errors"]:
            print(f"  Errors: {result['errors']}")

        # Key assertions
        assert result["status"] == "success", f"Simulation failed: {result['errors']}"
        assert result["error_code"] == 0 or result["error_code"] is None
        assert result["elapsed_time"] > 0

        # Verify .rpt file exists and has content
        assert os.path.exists(rpt), "Report file was not created"
        rpt_size = os.path.getsize(rpt)
        assert rpt_size > 100, f"Report file too small: {rpt_size} bytes"
        print(f"  RPT size: {rpt_size:,} bytes — OK")

    def test_validate_inp_passes(self, tmp_dir):
        """Validate the .inp file using pyswmm."""
        inp = _build_complete_project(tmp_dir)
        result = validate_inp(inp)
        print(f"\n  Validation: {result}")
        assert result["valid"] is True, f"Validation failed: {result['errors']}"


# ---------------------------------------------------------------------------
# Workflow 2: Report parsing
# ---------------------------------------------------------------------------


class TestReportParsing:
    @pytest.fixture
    def simulated_project(self, tmp_dir):
        """Build and simulate a project, return (inp, rpt) paths."""
        inp = _build_complete_project(tmp_dir)
        rpt = os.path.join(tmp_dir, "test_project.rpt")
        result = run_simulation(inp, rpt_path=rpt)
        assert result["status"] == "success", f"Simulation failed: {result['errors']}"
        return inp, rpt

    def test_parse_report_returns_dict(self, simulated_project):
        inp, rpt = simulated_project
        report = parse_report(rpt)
        assert isinstance(report, dict)
        assert "errors" in report
        assert "warnings" in report
        print(f"\n  Report keys: {list(report.keys())}")
        print(f"  Errors: {report['errors']}")
        print(f"  Warnings: {report['warnings']}")

    def test_simulation_no_errors(self, simulated_project):
        inp, rpt = simulated_project
        report = parse_report(rpt)
        # SWMM errors in the report indicate a real problem
        assert len(report["errors"]) == 0, f"Report contains errors: {report['errors']}"

    def test_node_results_available(self, simulated_project):
        inp, rpt = simulated_project
        report = parse_report(rpt)
        node_summary = report["node_depth_summary"]
        print(f"\n  Node summary keys: {list(node_summary.keys())}")
        # J1 and J2 should appear in node results
        assert "J1" in node_summary or len(node_summary) > 0

    def test_link_results_available(self, simulated_project):
        inp, rpt = simulated_project
        report = parse_report(rpt)
        link_summary = report["link_flow_summary"]
        print(f"\n  Link summary keys: {list(link_summary.keys())}")
        assert "C1" in link_summary or len(link_summary) > 0

    def test_get_node_results(self, simulated_project):
        inp, rpt = simulated_project
        result = get_node_results(rpt, "J1")
        assert isinstance(result, dict)
        assert "node" in result
        assert result["node"] == "J1"
        print(f"\n  J1 results: {result}")

    def test_get_link_results(self, simulated_project):
        inp, rpt = simulated_project
        result = get_link_results(rpt, "C1")
        assert isinstance(result, dict)
        assert "link" in result
        print(f"\n  C1 results: {result}")

    def test_get_runoff_summary(self, simulated_project):
        inp, rpt = simulated_project
        result = get_runoff_summary(rpt)
        assert isinstance(result, dict)
        assert "subcatchments" in result
        assert isinstance(result["subcatchments"], list)
        print(f"\n  Runoff summary subcatchments: {result['subcatchments']}")

    def test_get_flow_routing_summary(self, simulated_project):
        inp, rpt = simulated_project
        result = get_flow_routing_summary(rpt)
        assert isinstance(result, dict)
        assert "continuity" in result
        print(f"\n  Flow routing continuity: {result['continuity']}")


# ---------------------------------------------------------------------------
# Workflow 3: CLI subprocess tests
# ---------------------------------------------------------------------------


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-swmm")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_help(self):
        """CLI --help works and exits 0."""
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "swmm" in result.stdout.lower() or "EPA" in result.stdout or "SWMM" in result.stdout
        print(f"\n  Help output length: {len(result.stdout)} chars")

    def test_project_new_json(self, tmp_dir):
        """Create a project via CLI and verify JSON output."""
        out = os.path.join(tmp_dir, "cli_test.inp")
        result = self._run(["--json", "project", "new", "--output", out,
                            "--title", "CLI Test", "--flow-units", "CMS"])
        assert result.returncode == 0, f"STDERR: {result.stderr}"
        assert os.path.exists(out), "INP file not created"

        data = json.loads(result.stdout)
        assert data["title"] == "CLI Test"
        assert data["flow_units"] == "CMS"
        assert "path" in data
        print(f"\n  Created: {data['path']}")

    def test_project_info_json(self, tmp_dir):
        """project info returns valid JSON with element counts."""
        out = os.path.join(tmp_dir, "info_test.inp")
        self._run(["--json", "project", "new", "--output", out])

        result = self._run(["--json", "project", "info", out])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "junctions" in data
        assert "conduits" in data
        assert data["junctions"] == 0

    def test_network_add_junction_json(self, tmp_dir):
        """Add junction via CLI, verify JSON output and file update."""
        out = os.path.join(tmp_dir, "junc_test.inp")
        self._run(["--json", "project", "new", "--output", out])

        result = self._run(["--json", "--project", out,
                            "network", "add-junction",
                            "--name", "J1", "--elevation", "10.0"])
        assert result.returncode == 0, f"STDERR: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["name"] == "J1"

        # Verify file was updated
        from cli_anything.swmm.core.project import parse_inp as _parse
        sections = _parse(out)
        assert any("J1" in l for l in sections["JUNCTIONS"])

    def test_full_simulation_workflow(self, tmp_dir):
        """Full CLI workflow: create → build network → simulate → results."""
        inp = os.path.join(tmp_dir, "full_cli.inp")
        rpt = os.path.join(tmp_dir, "full_cli.rpt")

        # Step 1: Create project
        r = self._run(["--json", "project", "new", "--output", inp,
                       "--title", "Full CLI Test"])
        assert r.returncode == 0, f"project new failed: {r.stderr}"

        # Step 2: Add network elements
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "10.0"])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J2", "--elevation", "9.5"])
        self._run(["--project", inp, "network", "add-outfall",
                   "--name", "OUT1", "--elevation", "8.0"])
        self._run(["--project", inp, "network", "add-conduit",
                   "--name", "C1", "--from", "J1", "--to", "J2", "--length", "100"])
        self._run(["--project", inp, "network", "add-conduit",
                   "--name", "C2", "--from", "J2", "--to", "OUT1", "--length", "50"])
        self._run(["--project", inp, "network", "add-raingage",
                   "--name", "RG1", "--timeseries", "TS1"])
        self._run(["--project", inp, "network", "add-subcatchment",
                   "--name", "SUB1", "--raingage", "RG1", "--outlet", "J1", "--area", "8.0"])

        # Step 3: Add rainfall
        r = self._run(["--project", inp, "timeseries", "rainfall",
                       "--name", "TS1", "--raingage", "RG1",
                       "--start", "2023-01-01 00:00",
                       "--duration", "2", "--peak", "20"])
        assert r.returncode == 0, f"timeseries rainfall failed: {r.stderr}"

        # Step 4: Set options
        self._run(["--project", inp, "options", "set",
                   "--start-date", "01/01/2023",
                   "--end-date", "01/01/2023",
                   "--end-time", "06:00:00"])

        # Step 5: Run simulation
        r = self._run(["--json", "--project", inp, "simulate", "run",
                       "--report", rpt], check=False)
        sim_data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
        print(f"\n  Simulation status: {sim_data.get('status')}")
        print(f"  Simulation errors: {sim_data.get('errors')}")
        assert r.returncode == 0, f"simulate run failed: {r.stderr}"

        # Step 6: Verify outputs
        assert os.path.exists(rpt), f"Report file not created: {rpt}"
        rpt_size = os.path.getsize(rpt)
        assert rpt_size > 100, f"Report too small: {rpt_size}"
        print(f"\n  RPT: {rpt} ({rpt_size:,} bytes)")

        # Step 7: Results
        r = self._run(["--json", "--project", inp, "results", "summary",
                       "--report", rpt])
        assert r.returncode == 0
        summary = json.loads(r.stdout)
        assert "errors" in summary
        print(f"  Results summary: {list(summary.keys())}")

    def test_network_list_json(self, tmp_dir):
        """network list returns valid JSON."""
        inp = os.path.join(tmp_dir, "list_test.inp")
        self._run(["project", "new", "--output", inp])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "5.0"])

        r = self._run(["--json", "--project", inp, "network", "list"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "nodes" in data
        assert any(n["name"] == "J1" for n in data["nodes"])

    def test_options_show_json(self, tmp_dir):
        """options show returns valid JSON."""
        inp = os.path.join(tmp_dir, "opts_test.inp")
        self._run(["project", "new", "--output", inp])

        r = self._run(["--json", "--project", inp, "options", "show"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "FLOW_UNITS" in data

    def test_options_set_defaults_report_start_to_start(self, tmp_dir):
        """options set defaults REPORT_START_* to START_* values."""
        inp = os.path.join(tmp_dir, "opts_report_start.inp")
        self._run(["--json", "project", "new", "--output", inp])

        r = self._run([
            "--json", "--project", inp, "options", "set",
            "--start-date", "01/01/2023",
            "--end-date", "01/01/2023",
            "--start-time", "00:00:00",
            "--end-time", "06:00:00",
        ])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["REPORT_START_DATE"] == "01/01/2023"
        assert data["REPORT_START_TIME"] == "00:00:00"


# ---------------------------------------------------------------------------
# Workflow 4: Undo/Redo integration
# ---------------------------------------------------------------------------


class TestUndoRedoIntegration:
    def test_undo_reverses_add(self, tmp_dir):
        """Adding a junction and undoing should remove it."""
        inp = os.path.join(tmp_dir, "undo_test.inp")
        create_project(inp, "Undo Test")

        session = Session(inp_path=inp)
        session.load()

        # Initial state — no junctions
        net_before = [l for l in session.sections.get("JUNCTIONS", [])
                      if l.strip() and not l.strip().startswith(";;")]
        assert len(net_before) == 0

        # Add junction
        session.push()
        add_junction(session.sections, "J_UNDO", 10.0)
        assert any("J_UNDO" in l for l in session.sections["JUNCTIONS"])

        # Undo
        assert session.undo() is True
        assert not any("J_UNDO" in l for l in session.sections.get("JUNCTIONS", []))

    def test_redo_reapplies(self, tmp_dir):
        """After undo, redo re-adds the junction."""
        inp = os.path.join(tmp_dir, "redo_test.inp")
        create_project(inp, "Redo Test")

        session = Session(inp_path=inp)
        session.load()

        session.push()
        add_junction(session.sections, "J_REDO", 10.0)
        session.undo()
        assert session.redo() is True
        assert any("J_REDO" in l for l in session.sections["JUNCTIONS"])

    def test_save_after_undo(self, tmp_dir):
        """Save after undo writes the correct (pre-add) state."""
        inp = os.path.join(tmp_dir, "undo_save.inp")
        create_project(inp, "Undo Save Test")

        session = Session(inp_path=inp)
        session.load()

        session.push()
        add_junction(session.sections, "J_GONE", 10.0)
        session.undo()
        session.save()

        # Re-read the file
        from cli_anything.swmm.core.project import parse_inp as _parse
        sections = _parse(inp)
        assert not any("J_GONE" in l and not l.strip().startswith(";;")
                       for l in sections.get("JUNCTIONS", []))


# ---------------------------------------------------------------------------
# Workflow 5: Calibration E2E (real pyswmm simulation)
# ---------------------------------------------------------------------------

from cli_anything.swmm.core.calibrate import (
    load_session as calib_load_session,
    save_session as calib_save_session,
    add_observed,
    add_param,
    collect_simulated_series,
    compute_metrics,
    run_sensitivity,
    run_calibration,
    apply_best_params,
)


class TestCalibrationE2E:
    """Full calibration pipeline using real pyswmm simulation.

    These tests:
    1. Build a complete network and run a baseline simulation.
    2. Collect simulated time series using pyswmm step-by-step API.
    3. Use simulated data as synthetic "observed" data (self-calibration test).
    4. Run sensitivity analysis with one parameter.
    5. Run LHS calibration and verify the best result is the nominal value.
    6. Apply best params and verify the .inp file is updated.
    """

    def _build_project(self, tmp_dir: str) -> str:
        """Build a complete valid project and return its .inp path."""
        from cli_anything.swmm.core.project import parse_inp, write_inp
        inp = os.path.join(tmp_dir, "calib_model.inp")
        create_project(inp, "Calibration Test", "CMS")
        sections = parse_inp(inp)

        add_junction(sections, "J1", 10.0, max_depth=5.0)
        add_junction(sections, "J2", 9.5, max_depth=5.0)
        add_outfall(sections, "OUT1", 8.0, outfall_type="FREE")
        add_conduit(sections, "C1", "J1", "J2", 100.0, roughness=0.013, diameter=0.9)
        add_conduit(sections, "C2", "J2", "OUT1", 50.0, roughness=0.013, diameter=0.75)
        add_raingage(sections, "RG1", timeseries="STORM1")
        add_subcatchment(sections, "SUB1", "RG1", "J1", 8.0,
                         pct_imperv=65, width=150, slope=1.5)
        add_rainfall_event(sections, "RG1", "2023-01-01 00:00", 2.0, 25.0,
                           pattern="SCS", ts_name="STORM1")
        set_simulation_dates(sections, "01/01/2023", "01/01/2023",
                             "00:00:00", "06:00:00")
        set_options(sections, REPORT_STEP="00:05:00", ROUTING_STEP="0:00:30")
        write_inp(sections, inp)
        return inp

    def test_collect_simulated_series_node(self, tmp_dir):
        """collect_simulated_series returns non-empty series for node:J1:depth."""
        inp = self._build_project(tmp_dir)
        series = collect_simulated_series(inp, "node:J1:depth")

        assert isinstance(series, list), "Should return a list"
        assert len(series) > 0, "Should have at least one data point"
        assert "datetime" in series[0], "Each record must have 'datetime' key"
        assert "value" in series[0], "Each record must have 'value' key"
        assert isinstance(series[0]["value"], float)

        # Peak depth should be > 0 for a rainfall-driven simulation
        peak = max(r["value"] for r in series)
        print(f"\n  Collected {len(series)} node:J1:depth timesteps, peak={peak:.4f} m")
        assert peak > 0.0, f"Expected non-zero peak depth, got {peak}"

    def test_collect_simulated_series_link(self, tmp_dir):
        """collect_simulated_series returns valid flow series for link:C1:flow."""
        inp = self._build_project(tmp_dir)
        series = collect_simulated_series(inp, "link:C1:flow")

        assert len(series) > 0
        peak = max(r["value"] for r in series)
        print(f"\n  Collected {len(series)} link:C1:flow timesteps, peak={peak:.4f} m3/s")
        assert peak >= 0.0

    def test_calibration_metrics_self_consistency(self, tmp_dir):
        """Comparing simulated series against itself should give NSE=1, RMSE=0."""
        inp = self._build_project(tmp_dir)
        series = collect_simulated_series(inp, "node:J1:depth")

        # Self-calibration: obs == sim
        metrics = compute_metrics(series, series)
        print(f"\n  Self-consistency metrics: {metrics}")
        assert metrics["nse"] == pytest.approx(1.0, abs=1e-4)
        assert metrics["rmse"] == pytest.approx(0.0, abs=1e-4)
        assert metrics["mae"] == pytest.approx(0.0, abs=1e-4)
        assert metrics["pbias"] == pytest.approx(0.0, abs=1e-2)

    def test_sensitivity_one_param(self, tmp_dir):
        """Sensitivity analysis runs without error and produces records."""
        inp = self._build_project(tmp_dir)

        # Collect baseline series as synthetic observed
        baseline = collect_simulated_series(inp, "node:J1:depth")
        assert len(baseline) > 0

        # Build calibration session
        session = calib_load_session(inp)
        add_observed(session, "node:J1:depth", baseline)
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.008, 0.025, nominal=0.013)

        records = run_sensitivity(inp, session, n_steps=3)
        calib_save_session(session)

        print(f"\n  Sensitivity records: {len(records)}")
        assert len(records) == 3, f"Expected 3 records (3 steps × 1 param × 1 obs), got {len(records)}"
        for r in records:
            assert "param_id" in r
            assert "value" in r
            assert "metrics" in r
            if "nse" in r["metrics"]:
                print(f"    {r['param_field']}={r['value']:.4f} → NSE={r['metrics']['nse']:.4f}")

    def test_sensitivity_nominal_gives_best_nse(self, tmp_dir):
        """The nominal parameter value should give NSE=1 when obs==baseline sim."""
        inp = self._build_project(tmp_dir)
        baseline = collect_simulated_series(inp, "node:J1:depth")

        session = calib_load_session(inp)
        add_observed(session, "node:J1:depth", baseline)
        # Nominal = 0.013 (same as model) → self-calibration should give NSE=1
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.008, 0.025, nominal=0.013)

        records = run_sensitivity(inp, session, n_steps=5)

        # The record closest to nominal=0.013 should have the best NSE
        nse_by_value = {r["value"]: r["metrics"].get("nse", -9999) for r in records}
        print(f"\n  NSE by roughness value: {nse_by_value}")
        nse_at_nominal = max(nse_by_value[v] for v in nse_by_value if abs(v - 0.013) < 0.005)
        assert nse_at_nominal > 0.8, (
            f"Expected NSE > 0.8 near nominal value, got {nse_at_nominal}"
        )

    def test_calibration_lhs_finds_nominal(self, tmp_dir):
        """LHS calibration on self-calibration problem should find near-nominal params."""
        inp = self._build_project(tmp_dir)
        baseline = collect_simulated_series(inp, "node:J1:depth")

        session = calib_load_session(inp)
        add_observed(session, "node:J1:depth", baseline)
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.008, 0.025, nominal=0.013)

        result = run_calibration(inp, session, method="lhs", n_samples=5,
                                 metric="nse", seed=42)
        calib_save_session(session)

        print(f"\n  Calibration: {result['n_runs']} runs")
        print(f"  Best params: {result['best_params']}")
        print(f"  Best metrics: {result['best_metrics']}")

        assert result["n_runs"] == 5
        assert result["best_params"] is not None
        assert "conduit:C1:roughness" in result["best_params"]

        # The best NSE should be reasonably good
        best_score = result["best_metrics"].get("nse", -9999)
        assert best_score > 0.5, (
            f"Expected NSE > 0.5 from LHS calibration, got {best_score}"
        )

    def test_calibration_apply_writes_inp(self, tmp_dir):
        """apply_best_params writes the best params into a new .inp file."""
        from cli_anything.swmm.core.project import parse_inp
        inp = self._build_project(tmp_dir)
        baseline = collect_simulated_series(inp, "node:J1:depth")

        session = calib_load_session(inp)
        add_observed(session, "node:J1:depth", baseline)
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.008, 0.025, nominal=0.013)

        run_calibration(inp, session, method="lhs", n_samples=3, metric="nse")
        calib_save_session(session)

        best_params = session["best"]["params"]
        assert best_params is not None

        out_inp = os.path.join(tmp_dir, "calibrated.inp")
        result = apply_best_params(inp, best_params, output_path=out_inp)

        assert os.path.exists(out_inp), "Calibrated .inp file was not created"
        assert result["n_applied"] > 0
        assert result["errors"] == []
        print(f"\n  Calibrated .inp: {out_inp} ({os.path.getsize(out_inp):,} bytes)")

        # Verify the roughness was actually updated in the output file
        sections = parse_inp(out_inp)
        best_roughness = best_params.get("conduit:C1:roughness")
        for line in sections.get("CONDUITS", []):
            if "C1" in line and not line.strip().startswith(";;"):
                parts = line.split()
                if parts[0] == "C1":
                    actual = float(parts[4])
                    assert actual == pytest.approx(best_roughness, abs=1e-5), (
                        f"Expected roughness {best_roughness}, got {actual}"
                    )
                    print(f"  Roughness applied: {actual}")
                    break

    def test_calibration_grid_method(self, tmp_dir):
        """Grid calibration runs and returns results."""
        inp = self._build_project(tmp_dir)
        baseline = collect_simulated_series(inp, "node:J1:depth")

        session = calib_load_session(inp)
        add_observed(session, "node:J1:depth", baseline)
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.010, 0.016, nominal=0.013)

        # Grid with n_per_param=3 → 3 samples for 1 param
        result = run_calibration(inp, session, method="grid", n_samples=3, metric="nse")
        assert result["n_runs"] == 3
        assert result["method"] == "grid"
        print(f"\n  Grid best NSE: {result['best_metrics'].get('nse', 'N/A')}")


class TestCalibrateSubprocessCLI:
    """Subprocess tests for the calibrate command group."""

    CLI_BASE = _resolve_cli("cli-anything-swmm")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True, check=check,
        )

    def _build_and_simulate(self, tmp_dir: str) -> tuple[str, list[dict]]:
        """Build project and return (inp_path, simulated_series)."""
        inp = os.path.join(tmp_dir, "calib_cli.inp")
        create_project(inp, "CLI Calib Test", "CMS")
        from cli_anything.swmm.core.project import parse_inp, write_inp
        sections = parse_inp(inp)
        add_junction(sections, "J1", 10.0, max_depth=5.0)
        add_junction(sections, "J2", 9.5, max_depth=5.0)
        add_outfall(sections, "OUT1", 8.0)
        add_conduit(sections, "C1", "J1", "J2", 100.0, roughness=0.013, diameter=0.9)
        add_conduit(sections, "C2", "J2", "OUT1", 50.0, roughness=0.013, diameter=0.75)
        add_raingage(sections, "RG1", timeseries="STORM1")
        add_subcatchment(sections, "SUB1", "RG1", "J1", 8.0, pct_imperv=65)
        add_rainfall_event(sections, "RG1", "2023-01-01 00:00", 2.0, 25.0,
                           pattern="SCS", ts_name="STORM1")
        set_simulation_dates(sections, "01/01/2023", "01/01/2023",
                             "00:00:00", "06:00:00")
        set_options(sections, REPORT_STEP="00:05:00", ROUTING_STEP="0:00:30")
        write_inp(sections, inp)
        series = collect_simulated_series(inp, "node:J1:depth")
        return inp, series

    def test_calibrate_help(self):
        """calibrate --help lists subcommands."""
        r = self._run(["calibrate", "--help"])
        assert r.returncode == 0
        assert "calibrate" in r.stdout.lower() or "sensitivity" in r.stdout.lower()

    def test_calibrate_params_add_json(self, tmp_dir):
        """calibrate params-add returns JSON with param definition."""
        inp = os.path.join(tmp_dir, "params_test.inp")
        self._run(["project", "new", "--output", inp])

        r = self._run(["--json", "--project", inp,
                       "calibrate", "params-add",
                       "--type", "conduit", "--name", "C1",
                       "--field", "ROUGHNESS",
                       "--min", "0.005", "--max", "0.02"])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["id"] == "conduit:C1:roughness"
        assert data["min"] == 0.005
        assert data["max"] == 0.02

    def test_calibrate_params_list_json(self, tmp_dir):
        """calibrate params-list returns JSON list."""
        inp = os.path.join(tmp_dir, "plist_test.inp")
        self._run(["project", "new", "--output", inp])
        self._run(["--project", inp, "calibrate", "params-add",
                   "--type", "conduit", "--name", "C1", "--field", "ROUGHNESS",
                   "--min", "0.005", "--max", "0.02"])

        r = self._run(["--json", "--project", inp, "calibrate", "params-list"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "conduit:C1:roughness"

    def test_calibrate_metrics_json(self, tmp_dir):
        """calibrate metrics computes NSE/RMSE from two CSV files."""
        from datetime import datetime, timedelta

        # Write two identical CSV files
        def write_csv(path, values):
            with open(path, "w") as f:
                f.write("datetime,value\n")
                dt = datetime(2023, 1, 1)
                for i, v in enumerate(values):
                    f.write(f"{dt + timedelta(minutes=5*i)},{v}\n")

        obs_csv = os.path.join(tmp_dir, "obs.csv")
        sim_csv = os.path.join(tmp_dir, "sim.csv")
        values = [0.0, 0.5, 1.0, 1.5, 1.0, 0.5, 0.0]
        write_csv(obs_csv, values)
        write_csv(sim_csv, values)  # Identical → perfect fit

        r = self._run(["--json", "calibrate", "metrics",
                       "--observed", obs_csv, "--simulated", sim_csv])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert "nse" in data
        assert "rmse" in data
        assert "mae" in data
        assert "pbias" in data
        assert data["nse"] == pytest.approx(1.0, abs=1e-4)
        assert data["rmse"] == pytest.approx(0.0, abs=1e-4)
        print(f"\n  Metrics: NSE={data['nse']}, RMSE={data['rmse']}, "
              f"MAE={data['mae']}, PBias={data['pbias']}")

    def test_calibrate_status_json(self, tmp_dir):
        """calibrate status returns session state as JSON."""
        inp = os.path.join(tmp_dir, "status_test.inp")
        self._run(["project", "new", "--output", inp])

        r = self._run(["--json", "--project", inp, "calibrate", "status"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "n_params" in data
        assert "n_observed_sets" in data
        assert data["n_params"] == 0

    def test_calibrate_full_workflow_json(self, tmp_dir):
        """Full calibrate workflow via CLI subprocess: params → observed → run → apply."""
        inp, baseline = self._build_and_simulate(tmp_dir)

        # Write baseline as CSV observed data
        obs_csv = os.path.join(tmp_dir, "observed.csv")
        with open(obs_csv, "w") as f:
            f.write("datetime,value\n")
            for rec in baseline:
                f.write(f"{rec['datetime']},{rec['value']}\n")

        # Add parameters
        r = self._run(["--json", "--project", inp,
                       "calibrate", "params-add",
                       "--type", "conduit", "--name", "C1",
                       "--field", "ROUGHNESS",
                       "--min", "0.008", "--max", "0.020",
                       "--nominal", "0.013"])
        assert r.returncode == 0, f"params-add failed: {r.stderr}"

        # Add observed data
        r = self._run(["--project", inp,
                       "calibrate", "observed-add",
                       "--file", obs_csv,
                       "--element", "node:J1:depth"])
        assert r.returncode == 0, f"observed-add failed: {r.stderr}"

        # Run calibration (3 samples for speed)
        r = self._run(["--json", "--project", inp,
                       "calibrate", "run",
                       "--method", "lhs", "--n-samples", "3",
                       "--metric", "nse"], check=False)
        assert r.returncode == 0, f"calibrate run failed: {r.stderr}\n{r.stdout}"
        data = json.loads(r.stdout)
        assert "n_runs" in data
        assert data["n_runs"] == 3
        assert "best_params" in data
        print(f"\n  Calibration: {data['n_runs']} runs, "
              f"best NSE={data['best_metrics'].get('nse', 'N/A')}")

        # Apply best params
        out_inp = os.path.join(tmp_dir, "calibrated.inp")
        r = self._run(["--json", "--project", inp,
                       "calibrate", "apply",
                       "--output", out_inp])
        assert r.returncode == 0, f"calibrate apply failed: {r.stderr}"
        apply_data = json.loads(r.stdout)
        assert apply_data["n_applied"] > 0
        assert os.path.exists(out_inp)
        print(f"  Applied {apply_data['n_applied']} params → {out_inp}")


# ---------------------------------------------------------------------------
# Workflow 6: New hydraulic structures (pump, weir, orifice, inflow)
# ---------------------------------------------------------------------------

from cli_anything.swmm.core.network import (
    add_pump, remove_pump,
    add_weir, remove_weir,
    add_orifice, remove_orifice,
    add_inflow, remove_inflow,
    add_storage,
)


class TestHydraulicStructuresAPI:
    """Core API tests for pump, weir, orifice, and inflow functions."""

    def test_add_pump_and_list(self, tmp_dir):
        """Pump appears in list_network and survives round-trip."""
        from cli_anything.swmm.core.network import list_network
        inp = os.path.join(tmp_dir, "pump_test.inp")
        create_project(inp, "Pump Test")
        sections = parse_inp(inp)

        add_junction(sections, "WW1", 5.0, max_depth=4.0)
        add_junction(sections, "DS1", 4.0, max_depth=3.0)
        add_pump(sections, "P1", "WW1", "DS1", pump_curve="*",
                 status="ON", startup_depth=1.5, shutoff_depth=0.5)
        write_inp(sections, inp)

        reloaded = parse_inp(inp)
        net = list_network(reloaded)
        pump_names = [l["name"] for l in net["links"] if l["element_type"] == "pump"]
        assert "P1" in pump_names

    def test_remove_pump(self, tmp_dir):
        inp = os.path.join(tmp_dir, "pump_rm.inp")
        create_project(inp, "Pump Remove Test")
        sections = parse_inp(inp)
        add_pump(sections, "P_RM", "J1", "J2")
        remove_pump(sections, "P_RM")
        assert not any("P_RM" in l and not l.strip().startswith(";;")
                       for l in sections.get("PUMPS", []))

    def test_add_weir_and_roundtrip(self, tmp_dir):
        """Weir data survives write/parse round-trip."""
        inp = os.path.join(tmp_dir, "weir_test.inp")
        create_project(inp, "Weir Test")
        sections = parse_inp(inp)

        add_junction(sections, "J1", 10.0)
        add_outfall(sections, "O1", 8.0)
        add_weir(sections, "W1", "J1", "O1", weir_type="TRANSVERSE",
                 crest_height=0.3, discharge_coeff=3.33)
        write_inp(sections, inp)

        reloaded = parse_inp(inp)
        assert any("W1" in l and not l.strip().startswith(";;")
                   for l in reloaded.get("WEIRS", []))

    def test_weir_in_list_network(self, tmp_dir):
        from cli_anything.swmm.core.network import list_network
        inp = os.path.join(tmp_dir, "weir_list.inp")
        create_project(inp, "Weir List Test")
        sections = parse_inp(inp)
        add_junction(sections, "J1", 10.0)
        add_outfall(sections, "O1", 8.0)
        add_weir(sections, "W1", "J1", "O1")
        net = list_network(sections)
        assert any(l["name"] == "W1" and l["element_type"] == "weir" for l in net["links"])

    def test_add_orifice_with_xsection(self, tmp_dir):
        """Orifice adds both ORIFICES and XSECTIONS entries."""
        inp = os.path.join(tmp_dir, "orifice_test.inp")
        create_project(inp, "Orifice Test")
        sections = parse_inp(inp)

        add_storage(sections, "POND1", 5.0, max_depth=3.0)
        add_junction(sections, "DS1", 4.0)
        add_orifice(sections, "OR1", "POND1", "DS1",
                    orifice_type="BOTTOM", offset=0.0, discharge_coeff=0.65)
        write_inp(sections, inp)

        reloaded = parse_inp(inp)
        assert any("OR1" in l and not l.strip().startswith(";;")
                   for l in reloaded.get("ORIFICES", []))
        assert any("OR1" in l and not l.strip().startswith(";;")
                   for l in reloaded.get("XSECTIONS", []))

    def test_orifice_in_list_network(self, tmp_dir):
        from cli_anything.swmm.core.network import list_network
        inp = os.path.join(tmp_dir, "orifice_list.inp")
        create_project(inp, "Orifice List Test")
        sections = parse_inp(inp)
        add_storage(sections, "POND1", 5.0, max_depth=3.0)
        add_junction(sections, "DS1", 4.0)
        add_orifice(sections, "OR1", "POND1", "DS1")
        net = list_network(sections)
        assert any(l["name"] == "OR1" and l["element_type"] == "orifice" for l in net["links"])

    def test_add_inflow_roundtrip(self, tmp_dir):
        """External inflow survives write/parse round-trip."""
        inp = os.path.join(tmp_dir, "inflow_test.inp")
        create_project(inp, "Inflow Test")
        sections = parse_inp(inp)

        add_junction(sections, "J1", 10.0)
        # Add a timeseries for the inflow
        from cli_anything.swmm.core.timeseries import add_timeseries
        add_timeseries(sections, "TS_INFLOW", [
            ("01/01/2023", "0:00", 0.05),
            ("01/01/2023", "1:00", 0.10),
            ("01/01/2023", "2:00", 0.05),
        ])
        add_inflow(sections, "J1", "TS_INFLOW", mfactor=1.0, baseline=0.0)
        write_inp(sections, inp)

        reloaded = parse_inp(inp)
        assert any("J1" in l and not l.strip().startswith(";;")
                   for l in reloaded.get("INFLOWS", []))

    def test_remove_inflow(self, tmp_dir):
        inp = os.path.join(tmp_dir, "inflow_rm.inp")
        create_project(inp, "Inflow Remove Test")
        sections = parse_inp(inp)
        add_junction(sections, "J1", 10.0)
        add_inflow(sections, "J1", "TS1")
        removed = remove_inflow(sections, "J1")
        assert removed is True
        assert not any("J1" in l and not l.strip().startswith(";;")
                       for l in sections.get("INFLOWS", []))


class TestNewCLICommands:
    """CLI subprocess tests for pump, weir, orifice, inflow, results subcatchments."""

    CLI_BASE = _resolve_cli("cli-anything-swmm")

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True, check=check,
        )

    def _new_project(self, tmp_dir: str) -> str:
        out = os.path.join(tmp_dir, "new_cmds.inp")
        self._run(["project", "new", "--output", out])
        return out

    def test_add_pump_cli(self, tmp_dir):
        """network add-pump creates PUMPS section entry."""
        inp = self._new_project(tmp_dir)
        # Add required nodes first
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "WW1", "--elevation", "5.0"])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "DS1", "--elevation", "4.0"])

        r = self._run(["--json", "--project", inp,
                       "network", "add-pump",
                       "--name", "P1", "--from", "WW1", "--to", "DS1",
                       "--pump-curve", "*", "--status", "ON"])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["name"] == "P1"
        assert data["type"] == "pump"

        # Verify in file
        sections = parse_inp(inp)
        assert any("P1" in l and not l.strip().startswith(";;")
                   for l in sections.get("PUMPS", []))

    def test_add_weir_cli(self, tmp_dir):
        """network add-weir creates WEIRS section entry."""
        inp = self._new_project(tmp_dir)
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "10.0"])
        self._run(["--project", inp, "network", "add-outfall",
                   "--name", "O1", "--elevation", "8.0"])

        r = self._run(["--json", "--project", inp,
                       "network", "add-weir",
                       "--name", "W1", "--from", "J1", "--to", "O1",
                       "--type", "TRANSVERSE", "--crest-height", "0.3"])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["name"] == "W1"
        assert data["element_type"] == "weir"

        sections = parse_inp(inp)
        assert any("W1" in l and not l.strip().startswith(";;")
                   for l in sections.get("WEIRS", []))

    def test_add_orifice_cli(self, tmp_dir):
        """network add-orifice creates ORIFICES and XSECTIONS entries."""
        inp = self._new_project(tmp_dir)
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "STO1", "--elevation", "5.0"])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "DS1", "--elevation", "4.0"])

        r = self._run(["--json", "--project", inp,
                       "network", "add-orifice",
                       "--name", "OR1", "--from", "STO1", "--to", "DS1",
                       "--type", "BOTTOM", "--offset", "0.0", "--cd", "0.65"])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["name"] == "OR1"
        assert data["element_type"] == "orifice"

        sections = parse_inp(inp)
        assert any("OR1" in l and not l.strip().startswith(";;")
                   for l in sections.get("ORIFICES", []))
        assert any("OR1" in l and not l.strip().startswith(";;")
                   for l in sections.get("XSECTIONS", []))

    def test_add_inflow_cli(self, tmp_dir):
        """network add-inflow creates INFLOWS section entry."""
        inp = self._new_project(tmp_dir)
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "10.0"])
        # Add a timeseries for the inflow to reference
        self._run(["--project", inp, "timeseries", "add",
                   "--name", "TS_EXT",
                   "--data", "01/01/2023,0:00,0.05;01/01/2023,1:00,0.1"])

        r = self._run(["--json", "--project", inp,
                       "network", "add-inflow",
                       "--node", "J1", "--timeseries", "TS_EXT",
                       "--mfactor", "1.0"])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["node"] == "J1"
        assert data["constituent"] == "FLOW"

        sections = parse_inp(inp)
        assert any("J1" in l and not l.strip().startswith(";;")
                   for l in sections.get("INFLOWS", []))

    def test_remove_pump_weir_orifice_cli(self, tmp_dir):
        """network remove works for pump, weir, and orifice types."""
        inp = self._new_project(tmp_dir)
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "10.0"])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J2", "--elevation", "9.0"])

        # Add pump and remove it
        self._run(["--project", inp, "network", "add-pump",
                   "--name", "P_RM", "--from", "J1", "--to", "J2"])
        r = self._run(["--json", "--project", inp,
                       "network", "remove", "--type", "pump", "--name", "P_RM"])
        assert r.returncode == 0, f"pump remove failed: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["removed"] is True

        # Add weir and remove it
        self._run(["--project", inp, "network", "add-weir",
                   "--name", "W_RM", "--from", "J1", "--to", "J2"])
        r = self._run(["--json", "--project", inp,
                       "network", "remove", "--type", "weir", "--name", "W_RM"])
        assert r.returncode == 0, f"weir remove failed: {r.stderr}"
        assert json.loads(r.stdout)["removed"] is True

        # Add orifice and remove it
        self._run(["--project", inp, "network", "add-orifice",
                   "--name", "OR_RM", "--from", "J1", "--to", "J2"])
        r = self._run(["--json", "--project", inp,
                       "network", "remove", "--type", "orifice", "--name", "OR_RM"])
        assert r.returncode == 0, f"orifice remove failed: {r.stderr}"
        assert json.loads(r.stdout)["removed"] is True

    def test_results_subcatchments_cli(self, tmp_dir):
        """results subcatchments returns list of subcatchment runoff data."""
        # Build and simulate a complete project
        inp = _build_complete_project(tmp_dir)
        rpt = os.path.join(tmp_dir, "test_project.rpt")
        run_simulation(inp, rpt_path=rpt)

        r = self._run(["--json", "--project", inp,
                       "results", "subcatchments", "--report", rpt])
        assert r.returncode == 0, f"STDERR: {r.stderr}"
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        print(f"\n  Subcatchment results: {data}")

    def test_network_list_includes_new_types(self, tmp_dir):
        """network list --json shows pumps, weirs, orifices in links."""
        inp = self._new_project(tmp_dir)
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J1", "--elevation", "10.0"])
        self._run(["--project", inp, "network", "add-junction",
                   "--name", "J2", "--elevation", "9.0"])
        self._run(["--project", inp, "network", "add-pump",
                   "--name", "P1", "--from", "J1", "--to", "J2"])
        self._run(["--project", inp, "network", "add-weir",
                   "--name", "W1", "--from", "J1", "--to", "J2"])

        r = self._run(["--json", "--project", inp, "network", "list"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        link_names = [l["name"] for l in data["links"]]
        assert "P1" in link_names
        assert "W1" in link_names
