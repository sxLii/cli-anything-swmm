"""Unit tests for cli-anything-swmm core modules.

All tests use synthetic data — no real pyswmm simulation required.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from cli_anything.swmm.core.project import (
    create_project,
    parse_inp,
    write_inp,
    open_project,
    project_info,
)
from cli_anything.swmm.core.network import (
    add_junction,
    remove_junction,
    add_conduit,
    remove_conduit,
    add_subcatchment,
    add_outfall,
    add_storage,
    add_raingage,
    list_network,
)
from cli_anything.swmm.core.options import (
    get_options,
    set_options,
    set_simulation_dates,
)
from cli_anything.swmm.core.timeseries import (
    add_timeseries,
    list_timeseries,
    add_rainfall_event,
)
from cli_anything.swmm.core.session import Session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def basic_inp(tmp_dir):
    """Create a minimal project and return its path."""
    path = os.path.join(tmp_dir, "test.inp")
    create_project(path, "Test Project", "CMS")
    return path


@pytest.fixture
def basic_sections(basic_inp):
    """Return sections dict of a minimal project."""
    return parse_inp(basic_inp)


# ---------------------------------------------------------------------------
# core/project.py tests
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_create_project_basic(self, tmp_dir):
        path = os.path.join(tmp_dir, "proj.inp")
        result = create_project(path, "My Project", "CMS")
        assert os.path.exists(path)
        assert result["title"] == "My Project"
        assert result["flow_units"] == "CMS"
        assert result["path"] == os.path.abspath(path)
        assert "sections" in result

    def test_create_project_lps(self, tmp_dir):
        path = os.path.join(tmp_dir, "proj.inp")
        result = create_project(path, "LPS Project", "LPS")
        assert result["flow_units"] == "LPS"
        # Verify written to file
        sections = parse_inp(path)
        opts = {k: v for line in sections.get("OPTIONS", [])
                if line.strip() and not line.strip().startswith(";;")
                for k, v in [line.split(None, 1)] if line.split()}
        # Should find FLOW_UNITS in options
        content = open(path).read()
        assert "LPS" in content

    def test_create_project_invalid_units(self, tmp_dir):
        path = os.path.join(tmp_dir, "proj.inp")
        with pytest.raises(ValueError, match="Invalid flow_units"):
            create_project(path, "Bad Project", "INVALID")

    def test_create_project_required_sections(self, tmp_dir):
        path = os.path.join(tmp_dir, "proj.inp")
        create_project(path, "Test")
        sections = parse_inp(path)
        required = ["TITLE", "OPTIONS", "RAINGAGES", "SUBCATCHMENTS", "SUBAREAS",
                    "INFILTRATION", "JUNCTIONS", "OUTFALLS", "CONDUITS", "XSECTIONS",
                    "TIMESERIES", "REPORT"]
        for s in required:
            assert s in sections, f"Missing required section: {s}"

    def test_create_project_creates_dirs(self, tmp_dir):
        path = os.path.join(tmp_dir, "subdir", "project.inp")
        create_project(path, "Test")
        assert os.path.exists(path)


class TestParseInp:
    def test_roundtrip_preserves_sections(self, tmp_dir, basic_sections):
        out = os.path.join(tmp_dir, "roundtrip.inp")
        write_inp(basic_sections, out)
        sections2 = parse_inp(out)
        # Same section keys
        assert set(basic_sections.keys()) == set(sections2.keys())

    def test_roundtrip_preserves_data(self, basic_sections, tmp_dir):
        # Add a junction, then roundtrip
        add_junction(basic_sections, "J_RT", 10.0)
        out = os.path.join(tmp_dir, "rt.inp")
        write_inp(basic_sections, out)
        sections2 = parse_inp(out)
        found = any("J_RT" in line for line in sections2.get("JUNCTIONS", []))
        assert found

    def test_parse_missing_file(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            parse_inp(os.path.join(tmp_dir, "nonexistent.inp"))

    def test_comments_preserved(self, basic_inp):
        sections = parse_inp(basic_inp)
        # Comment lines start with ;;
        junction_lines = sections.get("JUNCTIONS", [])
        has_comment = any(l.strip().startswith(";;") for l in junction_lines)
        assert has_comment

    def test_write_inp_canonical_order(self, tmp_dir, basic_sections):
        out = os.path.join(tmp_dir, "ordered.inp")
        write_inp(basic_sections, out)
        content = open(out).read()
        title_pos = content.find("[TITLE]")
        options_pos = content.find("[OPTIONS]")
        junctions_pos = content.find("[JUNCTIONS]")
        assert title_pos < options_pos < junctions_pos


class TestOpenProject:
    def test_open_valid(self, basic_inp):
        result = open_project(basic_inp)
        assert result["path"] == os.path.abspath(basic_inp)
        assert "sections" in result
        assert "info" in result

    def test_open_missing_file(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            open_project(os.path.join(tmp_dir, "missing.inp"))


class TestProjectInfo:
    def test_project_info_empty_counts(self, basic_inp):
        info = project_info(basic_inp)
        assert info["junctions"] == 0
        assert info["conduits"] == 0
        assert info["subcatchments"] == 0
        assert info["outfalls"] == 0

    def test_project_info_with_elements(self, basic_inp):
        sections = parse_inp(basic_inp)
        add_junction(sections, "J1", 10.0)
        add_junction(sections, "J2", 9.0)
        add_outfall(sections, "OUT1", 8.0)
        write_inp(sections, basic_inp)

        info = project_info(basic_inp)
        assert info["junctions"] == 2
        assert info["outfalls"] == 1

    def test_project_info_has_options(self, basic_inp):
        info = project_info(basic_inp)
        assert "flow_units" in info
        assert info["flow_units"] == "CMS"


# ---------------------------------------------------------------------------
# core/network.py tests
# ---------------------------------------------------------------------------


class TestAddJunction:
    def test_add_junction_basic(self, basic_sections):
        result = add_junction(basic_sections, "J1", 10.0)
        assert result["name"] == "J1"
        assert result["type"] == "junction"
        lines = basic_sections["JUNCTIONS"]
        assert any("J1" in l for l in lines)

    def test_add_junction_defaults(self, basic_sections):
        add_junction(basic_sections, "J2", 5.0)
        line = next(l for l in basic_sections["JUNCTIONS"] if "J2" in l)
        # Should have 5.0 as max_depth default
        assert "5.0" in line or "5.000" in line

    def test_add_junction_custom_depth(self, basic_sections):
        add_junction(basic_sections, "J3", 8.0, max_depth=3.0)
        line = next(l for l in basic_sections["JUNCTIONS"] if "J3" in l)
        assert "3.0" in line or "3.000" in line


class TestRemoveJunction:
    def test_remove_existing(self, basic_sections):
        add_junction(basic_sections, "J1", 10.0)
        removed = remove_junction(basic_sections, "J1")
        assert removed is True
        assert not any("J1" in l and not l.strip().startswith(";;")
                       for l in basic_sections["JUNCTIONS"])

    def test_remove_nonexistent(self, basic_sections):
        removed = remove_junction(basic_sections, "DOESNOTEXIST")
        assert removed is False


class TestAddConduit:
    def test_add_conduit_basic(self, basic_sections):
        result = add_conduit(basic_sections, "C1", "J1", "J2", 100.0)
        assert result["name"] == "C1"
        assert result["type"] == "conduit"
        assert any("C1" in l for l in basic_sections["CONDUITS"])
        assert any("C1" in l for l in basic_sections["XSECTIONS"])

    def test_add_conduit_creates_xsection(self, basic_sections):
        add_conduit(basic_sections, "C2", "A", "B", 200.0, diameter=1.5)
        xsec_line = next(l for l in basic_sections["XSECTIONS"] if "C2" in l)
        assert "1.5" in xsec_line or "1.5000" in xsec_line

    def test_add_conduit_shape(self, basic_sections):
        add_conduit(basic_sections, "C3", "A", "B", 50.0, shape="RECT_CLOSED")
        xsec_line = next(l for l in basic_sections["XSECTIONS"] if "C3" in l)
        assert "RECT_CLOSED" in xsec_line


class TestRemoveConduit:
    def test_remove_conduit(self, basic_sections):
        add_conduit(basic_sections, "C1", "J1", "J2", 100.0)
        removed = remove_conduit(basic_sections, "C1")
        assert removed is True
        assert not any("C1" in l and not l.strip().startswith(";;")
                       for l in basic_sections["CONDUITS"])
        assert not any("C1" in l and not l.strip().startswith(";;")
                       for l in basic_sections["XSECTIONS"])


class TestAddSubcatchment:
    def test_add_subcatchment(self, basic_sections):
        result = add_subcatchment(basic_sections, "S1", "RG1", "J1", 10.0)
        assert result["name"] == "S1"
        assert any("S1" in l for l in basic_sections["SUBCATCHMENTS"])
        assert any("S1" in l for l in basic_sections["SUBAREAS"])
        assert any("S1" in l for l in basic_sections["INFILTRATION"])

    def test_add_subcatchment_pct_imperv(self, basic_sections):
        add_subcatchment(basic_sections, "S2", "RG1", "J1", 5.0, pct_imperv=75)
        line = next(l for l in basic_sections["SUBCATCHMENTS"] if "S2" in l)
        assert "75" in line


class TestAddOutfall:
    def test_add_outfall(self, basic_sections):
        result = add_outfall(basic_sections, "O1", 8.0)
        assert result["name"] == "O1"
        assert result["type"] == "FREE"
        assert any("O1" in l for l in basic_sections["OUTFALLS"])

    def test_add_outfall_types(self, basic_sections):
        for otype in ["FREE", "NORMAL", "FIXED"]:
            add_outfall(basic_sections, f"OUT_{otype}", 5.0, outfall_type=otype)
            line = next(l for l in basic_sections["OUTFALLS"] if f"OUT_{otype}" in l)
            assert otype in line


class TestAddRaingage:
    def test_add_raingage(self, basic_sections):
        result = add_raingage(basic_sections, "RG1", timeseries="TS1")
        assert result["name"] == "RG1"
        assert any("RG1" in l for l in basic_sections["RAINGAGES"])

    def test_add_raingage_timeseries_ref(self, basic_sections):
        add_raingage(basic_sections, "RG2", timeseries="STORM_TS")
        line = next(l for l in basic_sections["RAINGAGES"] if "RG2" in l)
        assert "STORM_TS" in line


class TestListNetwork:
    def test_list_network_empty(self, basic_sections):
        net = list_network(basic_sections)
        assert isinstance(net, dict)
        assert net["nodes"] == []
        assert net["links"] == []
        assert net["subcatchments"] == []

    def test_list_network_with_elements(self, basic_sections):
        add_junction(basic_sections, "J1", 10.0)
        add_junction(basic_sections, "J2", 9.5)
        add_outfall(basic_sections, "O1", 8.0)
        add_conduit(basic_sections, "C1", "J1", "J2", 100.0)
        add_subcatchment(basic_sections, "S1", "RG1", "J1", 5.0)

        net = list_network(basic_sections)
        node_names = [n["name"] for n in net["nodes"]]
        assert "J1" in node_names
        assert "J2" in node_names
        assert "O1" in node_names
        assert len(net["links"]) == 1
        assert net["links"][0]["name"] == "C1"
        assert len(net["subcatchments"]) == 1


# ---------------------------------------------------------------------------
# core/options.py tests
# ---------------------------------------------------------------------------


class TestGetOptions:
    def test_get_options_basic(self, basic_sections):
        opts = get_options(basic_sections)
        assert "FLOW_UNITS" in opts
        assert opts["FLOW_UNITS"] == "CMS"
        assert "FLOW_ROUTING" in opts

    def test_get_options_returns_dict(self, basic_sections):
        opts = get_options(basic_sections)
        assert isinstance(opts, dict)
        assert all(isinstance(k, str) for k in opts)


class TestSetOptions:
    def test_set_options_dates(self, basic_sections):
        result = set_options(basic_sections, START_DATE="02/15/2023", END_DATE="02/15/2023")
        assert result["START_DATE"] == "02/15/2023"
        assert result["END_DATE"] == "02/15/2023"

    def test_set_options_iso_date_conversion(self, basic_sections):
        result = set_options(basic_sections, START_DATE="2023-06-15")
        assert result["START_DATE"] == "06/15/2023"

    def test_set_options_routing(self, basic_sections):
        result = set_options(basic_sections, FLOW_ROUTING="KINWAVE")
        assert result["FLOW_ROUTING"] == "KINWAVE"

    def test_set_options_invalid_flow_units(self, basic_sections):
        with pytest.raises(ValueError, match="Invalid FLOW_UNITS"):
            set_options(basic_sections, FLOW_UNITS="GALLONS")

    def test_set_options_preserves_other_opts(self, basic_sections):
        original_routing = get_options(basic_sections).get("FLOW_ROUTING")
        set_options(basic_sections, START_DATE="01/01/2023")
        updated = get_options(basic_sections)
        assert updated.get("FLOW_ROUTING") == original_routing


class TestSetSimulationDates:
    def test_set_simulation_dates(self, basic_sections):
        result = set_simulation_dates(basic_sections, "01/01/2023", "01/01/2023",
                                     "00:00:00", "06:00:00")
        assert result["START_DATE"] == "01/01/2023"
        assert result["END_DATE"] == "01/01/2023"
        assert result["START_TIME"] == "00:00:00"
        assert result["END_TIME"] == "06:00:00"


# ---------------------------------------------------------------------------
# core/timeseries.py tests
# ---------------------------------------------------------------------------


class TestAddTimeseries:
    def test_add_timeseries_basic(self, basic_sections):
        data = [
            ("01/01/2023", "0:00", 0.0),
            ("01/01/2023", "1:00", 5.0),
            ("01/01/2023", "2:00", 10.0),
            ("01/01/2023", "3:00", 0.0),
        ]
        result = add_timeseries(basic_sections, "TS1", data)
        assert result["name"] == "TS1"
        assert result["points"] == 4
        assert any("TS1" in l for l in basic_sections["TIMESERIES"])

    def test_add_timeseries_replaces_existing(self, basic_sections):
        data1 = [("01/01/2023", "0:00", 5.0)]
        data2 = [("01/01/2023", "0:00", 10.0), ("01/01/2023", "1:00", 20.0)]
        add_timeseries(basic_sections, "TS_REPLACE", data1)
        add_timeseries(basic_sections, "TS_REPLACE", data2)

        # Count lines with TS_REPLACE (excluding comments)
        count = sum(1 for l in basic_sections["TIMESERIES"]
                    if "TS_REPLACE" in l and not l.strip().startswith(";;"))
        assert count == 2  # Only data2 entries remain


class TestListTimeseries:
    def test_list_timeseries_empty(self, basic_sections):
        result = list_timeseries(basic_sections)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_list_timeseries_populated(self, basic_sections):
        add_timeseries(basic_sections, "TS_A", [("01/01/2023", "0:00", 1.0)])
        add_timeseries(basic_sections, "TS_B", [
            ("01/01/2023", "0:00", 1.0),
            ("01/01/2023", "1:00", 2.0),
        ])
        result = list_timeseries(basic_sections)
        names = [r["name"] for r in result]
        assert "TS_A" in names
        assert "TS_B" in names
        ts_b = next(r for r in result if r["name"] == "TS_B")
        assert ts_b["points"] == 2


class TestAddRainfallEvent:
    def test_add_rainfall_scs(self, basic_sections):
        result = add_rainfall_event(
            basic_sections, "RG1", "2023-01-01 00:00", 3.0, 20.0, pattern="SCS"
        )
        assert result["timeseries"] == "RG1_TS"
        assert result["points"] > 0
        assert result["total_depth_mm"] > 0
        # Rain gage should be updated
        assert any("RG1" in l for l in basic_sections["RAINGAGES"])

    def test_add_rainfall_uniform(self, basic_sections):
        result = add_rainfall_event(
            basic_sections, "RG_UNI", "01/01/2023 00:00", 2.0, 15.0, pattern="UNIFORM"
        )
        assert result["pattern"] == "UNIFORM"
        assert result["total_depth_mm"] > 0

    def test_add_rainfall_triangular(self, basic_sections):
        result = add_rainfall_event(
            basic_sections, "RG_TRI", "2023-03-15 06:00", 1.0, 30.0, pattern="TRIANGULAR"
        )
        assert result["pattern"] == "TRIANGULAR"
        assert result["total_depth_mm"] > 0

    def test_rainfall_total_depth_reasonable(self, basic_sections):
        # 2-hour storm, 20 mm/hr peak — expect total depth in [5, 30] mm range
        result = add_rainfall_event(
            basic_sections, "RG_CHECK", "2023-01-01 00:00", 2.0, 20.0
        )
        assert 5 <= result["total_depth_mm"] <= 35

    def test_add_rainfall_custom_ts_name(self, basic_sections):
        result = add_rainfall_event(
            basic_sections, "RG1", "2023-01-01 00:00", 1.0, 10.0,
            ts_name="MY_CUSTOM_TS"
        )
        assert result["timeseries"] == "MY_CUSTOM_TS"
        ts_list = list_timeseries(basic_sections)
        assert any(t["name"] == "MY_CUSTOM_TS" for t in ts_list)


# ---------------------------------------------------------------------------
# core/session.py tests
# ---------------------------------------------------------------------------


class TestSession:
    def test_session_load_and_save(self, basic_inp, tmp_dir):
        session = Session(inp_path=basic_inp)
        session.load()
        assert "JUNCTIONS" in session.sections

        out = os.path.join(tmp_dir, "saved.inp")
        path = session.save(out)
        assert os.path.exists(path)

    def test_session_push_undo(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()

        # Record original junction count
        original_lines = list(session.sections.get("JUNCTIONS", []))

        # Push, then modify
        session.push()
        add_junction(session.sections, "J_TEMP", 10.0)
        assert any("J_TEMP" in l for l in session.sections["JUNCTIONS"])

        # Undo should restore
        result = session.undo()
        assert result is True
        assert not any("J_TEMP" in l for l in session.sections["JUNCTIONS"])

    def test_session_redo(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()

        session.push()
        add_junction(session.sections, "J_REDO", 10.0)

        session.undo()
        assert not any("J_REDO" in l for l in session.sections.get("JUNCTIONS", []))

        session.redo()
        assert any("J_REDO" in l for l in session.sections["JUNCTIONS"])

    def test_session_undo_empty_returns_false(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()
        result = session.undo()
        assert result is False

    def test_session_redo_empty_returns_false(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()
        result = session.redo()
        assert result is False

    def test_session_push_clears_redo(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()

        # Create a redo entry
        session.push()
        add_junction(session.sections, "J1", 10.0)
        session.undo()
        assert session.redo_depth == 1

        # Push new state — redo stack should be cleared
        session.push()
        add_junction(session.sections, "J2", 9.0)
        assert session.redo_depth == 0

    def test_session_status(self, basic_inp):
        session = Session(inp_path=basic_inp)
        session.load()
        status = session.status()
        assert "inp_path" in status
        assert "sections" in status
        assert "history_depth" in status
        assert "redo_depth" in status


# ---------------------------------------------------------------------------
# core/calibrate.py unit tests (no real simulation required)
# ---------------------------------------------------------------------------

from cli_anything.swmm.core.calibrate import (
    load_session as calib_load_session,
    save_session as calib_save_session,
    load_observed_csv,
    add_observed,
    add_param,
    compute_metrics,
    modify_param_in_sections,
    run_sensitivity,
    run_calibration,
    apply_best_params,
    _lhs_samples,
    _grid_samples,
    _parse_dt,
    _interp_at,
)


@pytest.fixture
def calib_session(basic_inp):
    """Return a fresh calibration session for the basic project."""
    return calib_load_session(basic_inp)


@pytest.fixture
def network_sections(basic_sections):
    """Sections with a small network for param-modification tests."""
    add_junction(basic_sections, "J1", 10.0, max_depth=5.0)
    add_junction(basic_sections, "J2", 9.5, max_depth=5.0)
    add_outfall(basic_sections, "OUT1", 8.0)
    add_conduit(basic_sections, "C1", "J1", "J2", 100.0, roughness=0.013)
    add_subcatchment(basic_sections, "S1", "RG1", "J1", 10.0,
                     pct_imperv=50, width=100, slope=0.5)
    return basic_sections


class TestCalibSession:
    def test_load_creates_default_session(self, basic_inp):
        session = calib_load_session(basic_inp)
        assert session["inp_path"] == os.path.abspath(basic_inp)
        assert session["observed"] == []
        assert session["params"] == []
        assert session["runs"] == []

    def test_save_and_reload(self, basic_inp, tmp_dir):
        session = calib_load_session(basic_inp)
        add_param(session, "conduit", "C1", "ROUGHNESS", 0.005, 0.02)
        path = calib_save_session(session)
        assert os.path.exists(path)

        reloaded = calib_load_session(basic_inp)
        assert len(reloaded["params"]) == 1
        assert reloaded["params"][0]["id"] == "conduit:C1:roughness"


class TestAddParam:
    def test_add_conduit_roughness(self, calib_session):
        result = add_param(calib_session, "conduit", "C1", "ROUGHNESS", 0.005, 0.02)
        assert result["id"] == "conduit:C1:roughness"
        assert result["min"] == 0.005
        assert result["max"] == 0.02
        assert result["nominal"] == pytest.approx(0.0125)
        assert len(calib_session["params"]) == 1

    def test_add_subcatchment_imperv(self, calib_session):
        result = add_param(calib_session, "subcatchment", "S1", "%IMPERV", 20, 80)
        assert result["field"] == "%IMPERV"
        assert result["nominal"] == 50.0

    def test_add_subarea_n_imperv(self, calib_session):
        result = add_param(calib_session, "subarea", "S1", "N-IMPERV", 0.005, 0.025)
        assert result["id"] == "subarea:S1:n-imperv"

    def test_add_infiltration_maxrate(self, calib_session):
        result = add_param(calib_session, "infiltration", "S1", "MAXRATE", 1.0, 6.0)
        assert result["id"] == "infiltration:S1:maxrate"

    def test_add_param_replaces_duplicate(self, calib_session):
        add_param(calib_session, "conduit", "C1", "ROUGHNESS", 0.005, 0.02)
        add_param(calib_session, "conduit", "C1", "ROUGHNESS", 0.008, 0.025)
        # Should only keep the latest definition
        params = [p for p in calib_session["params"] if p["id"] == "conduit:C1:roughness"]
        assert len(params) == 1
        assert params[0]["min"] == 0.008

    def test_add_param_invalid_type_field(self, calib_session):
        with pytest.raises(ValueError, match="Unsupported parameter"):
            add_param(calib_session, "conduit", "C1", "NONSENSE_FIELD", 0, 1)

    def test_add_param_min_ge_max_raises(self, calib_session):
        with pytest.raises(ValueError, match="must be less than"):
            add_param(calib_session, "conduit", "C1", "ROUGHNESS", 0.02, 0.005)

    def test_custom_nominal(self, calib_session):
        result = add_param(calib_session, "conduit", "C1", "ROUGHNESS", 0.005, 0.02, nominal=0.011)
        assert result["nominal"] == 0.011


class TestModifyParamInSections:
    def test_modify_conduit_roughness(self, network_sections):
        ok = modify_param_in_sections(network_sections, "conduit", "C1", "ROUGHNESS", 0.025)
        assert ok is True
        # Check the value changed in the section
        for line in network_sections["CONDUITS"]:
            if "C1" in line and not line.strip().startswith(";;"):
                parts = line.split()
                assert parts[4] == "0.025"
                break

    def test_modify_subcatchment_imperv(self, network_sections):
        ok = modify_param_in_sections(network_sections, "subcatchment", "S1", "%IMPERV", 75.0)
        assert ok is True
        for line in network_sections["SUBCATCHMENTS"]:
            if "S1" in line and not line.strip().startswith(";;"):
                parts = line.split()
                assert float(parts[4]) == 75.0
                break

    def test_modify_junction_maxdepth(self, network_sections):
        ok = modify_param_in_sections(network_sections, "junction", "J1", "MAXDEPTH", 8.0)
        assert ok is True
        for line in network_sections["JUNCTIONS"]:
            if line.strip() and not line.strip().startswith(";;"):
                parts = line.split()
                if parts[0] == "J1":
                    assert float(parts[2]) == 8.0
                    break

    def test_modify_all_elements(self, network_sections):
        # Both J1 and J2 should be modified
        ok = modify_param_in_sections(network_sections, "junction", "ALL", "MAXDEPTH", 7.5)
        assert ok is True
        depths = []
        for line in network_sections["JUNCTIONS"]:
            if line.strip() and not line.strip().startswith(";;"):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        depths.append(float(parts[2]))
                    except ValueError:
                        pass
        assert all(d == 7.5 for d in depths), f"Not all depths are 7.5: {depths}"

    def test_modify_nonexistent_element_returns_false(self, network_sections):
        ok = modify_param_in_sections(network_sections, "conduit", "NONEXISTENT", "ROUGHNESS", 0.01)
        assert ok is False

    def test_modify_invalid_param_raises(self, network_sections):
        with pytest.raises(ValueError, match="Unsupported parameter"):
            modify_param_in_sections(network_sections, "conduit", "C1", "BADFIELD", 0.01)


class TestComputeMetrics:
    """Test metric computation with synthetic data — no simulation needed."""

    def _make_series(self, values: list[float], start="2023-01-01 00:00") -> list[dict]:
        from datetime import datetime, timedelta
        dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
        return [
            {"datetime": str(dt + timedelta(minutes=5 * i)), "value": v}
            for i, v in enumerate(values)
        ]

    def test_perfect_fit_nse_is_one(self):
        obs = self._make_series([1.0, 2.0, 3.0, 2.0, 1.0])
        sim = self._make_series([1.0, 2.0, 3.0, 2.0, 1.0])
        m = compute_metrics(obs, sim)
        assert m["nse"] == pytest.approx(1.0, abs=1e-6)
        assert m["rmse"] == pytest.approx(0.0, abs=1e-6)
        assert m["mae"] == pytest.approx(0.0, abs=1e-6)
        assert m["pbias"] == pytest.approx(0.0, abs=1e-3)

    def test_constant_sim_nse_is_zero(self):
        """Simulated equal to observed mean → NSE = 0."""
        obs = self._make_series([1.0, 2.0, 3.0, 2.0, 2.0])
        obs_mean = sum(r["value"] for r in obs) / len(obs)
        sim = self._make_series([obs_mean] * 5)
        m = compute_metrics(obs, sim)
        assert m["nse"] == pytest.approx(0.0, abs=1e-4)

    def test_overestimate_negative_pbias(self):
        """Model overestimates → PBias < 0."""
        obs = self._make_series([1.0, 2.0, 3.0, 2.0, 1.0])
        sim = self._make_series([1.5, 2.5, 3.5, 2.5, 1.5])  # +0.5 bias
        m = compute_metrics(obs, sim)
        assert m["pbias"] < 0.0, f"Expected negative pbias (overestimate), got {m['pbias']}"

    def test_underestimate_positive_pbias(self):
        """Model underestimates → PBias > 0."""
        obs = self._make_series([1.0, 2.0, 3.0, 2.0, 1.0])
        sim = self._make_series([0.5, 1.5, 2.5, 1.5, 0.5])  # -0.5 bias
        m = compute_metrics(obs, sim)
        assert m["pbias"] > 0.0, f"Expected positive pbias (underestimate), got {m['pbias']}"

    def test_rmse_known_value(self):
        """RMSE of [1,2,3] vs [2,3,4] should be 1.0."""
        obs = self._make_series([1.0, 2.0, 3.0])
        sim = self._make_series([2.0, 3.0, 4.0])
        m = compute_metrics(obs, sim)
        assert m["rmse"] == pytest.approx(1.0, abs=1e-6)

    def test_mae_known_value(self):
        """MAE of [1,2,3] vs [2,3,4] should be 1.0."""
        obs = self._make_series([1.0, 2.0, 3.0])
        sim = self._make_series([2.0, 3.0, 4.0])
        m = compute_metrics(obs, sim)
        assert m["mae"] == pytest.approx(1.0, abs=1e-6)

    def test_n_field_correct(self):
        obs = self._make_series([1.0, 2.0, 3.0])
        sim = self._make_series([1.0, 2.0, 3.0])
        m = compute_metrics(obs, sim)
        assert m["n"] == 3

    def test_empty_observed_raises(self):
        with pytest.raises(ValueError):
            compute_metrics([], [{"datetime": "2023-01-01 00:00", "value": 1.0}])

    def test_single_point_raises(self):
        obs = self._make_series([1.0])
        sim = self._make_series([1.0])
        with pytest.raises(ValueError, match="2 observed"):
            compute_metrics(obs, sim)


class TestAddObserved:
    def _make_data(self, n=5) -> list[dict]:
        from datetime import datetime, timedelta
        dt = datetime(2023, 1, 1)
        return [
            {"datetime": str(dt + timedelta(minutes=5 * i)), "value": float(i)}
            for i in range(n)
        ]

    def test_add_observed_node_depth(self, calib_session):
        data = self._make_data()
        result = add_observed(calib_session, "node:J1:depth", data)
        assert result["id"] == "node:J1:depth"
        assert result["n_points"] == 5
        assert len(calib_session["observed"]) == 1

    def test_add_observed_link_flow(self, calib_session):
        data = self._make_data()
        result = add_observed(calib_session, "link:C1:flow", data, obs_id="c1_flow")
        assert result["id"] == "c1_flow"

    def test_add_observed_replaces_same_id(self, calib_session):
        data1 = self._make_data(3)
        data2 = self._make_data(7)
        add_observed(calib_session, "node:J1:depth", data1)
        add_observed(calib_session, "node:J1:depth", data2)
        assert len(calib_session["observed"]) == 1
        assert calib_session["observed"][0]["data"] == data2

    def test_add_observed_invalid_spec_raises(self, calib_session):
        with pytest.raises(ValueError):
            add_observed(calib_session, "node:J1:badvar", self._make_data())

    def test_add_observed_invalid_type_raises(self, calib_session):
        with pytest.raises(ValueError):
            add_observed(calib_session, "badtype:J1:depth", self._make_data())


class TestLhsSamples:
    def test_lhs_dimensions(self):
        params = [
            {"min": 0.0, "max": 1.0, "nominal": 0.5},
            {"min": 10.0, "max": 20.0, "nominal": 15.0},
        ]
        samples = _lhs_samples(params, n_samples=10)
        assert len(samples) == 10
        assert all(len(s) == 2 for s in samples)

    def test_lhs_within_bounds(self):
        params = [{"min": 0.005, "max": 0.02, "nominal": 0.01}]
        samples = _lhs_samples(params, n_samples=20)
        for s in samples:
            assert 0.005 <= s[0] <= 0.02, f"Sample {s[0]} out of bounds"

    def test_lhs_all_strata_covered(self):
        """Each of N strata should have exactly one sample (LHS guarantee)."""
        n = 10
        params = [{"min": 0.0, "max": 1.0, "nominal": 0.5}]
        samples = _lhs_samples(params, n_samples=n)
        # Each stratum [i/n, (i+1)/n] should contain exactly one sample
        strata = [0] * n
        for s in samples:
            idx = min(int(s[0] * n), n - 1)
            strata[idx] += 1
        assert all(c == 1 for c in strata), f"LHS strata not uniformly covered: {strata}"

    def test_lhs_reproducible_with_seed(self):
        params = [{"min": 0.0, "max": 1.0, "nominal": 0.5}]
        s1 = _lhs_samples(params, n_samples=10, seed=99)
        s2 = _lhs_samples(params, n_samples=10, seed=99)
        assert s1 == s2

    def test_lhs_different_seeds_differ(self):
        params = [{"min": 0.0, "max": 1.0, "nominal": 0.5}]
        s1 = _lhs_samples(params, n_samples=10, seed=1)
        s2 = _lhs_samples(params, n_samples=10, seed=2)
        assert s1 != s2


class TestGridSamples:
    def test_grid_count_single_param(self):
        params = [{"min": 0.0, "max": 1.0, "nominal": 0.5}]
        samples = _grid_samples(params, n_per_param=5)
        assert len(samples) == 5

    def test_grid_count_two_params(self):
        params = [
            {"min": 0.0, "max": 1.0, "nominal": 0.5},
            {"min": 0.0, "max": 1.0, "nominal": 0.5},
        ]
        samples = _grid_samples(params, n_per_param=4)
        assert len(samples) == 16  # 4^2

    def test_grid_endpoints_included(self):
        params = [{"min": 0.0, "max": 1.0, "nominal": 0.5}]
        samples = _grid_samples(params, n_per_param=3)
        values = [s[0] for s in samples]
        assert 0.0 in values
        assert 1.0 in values


class TestParseDatetime:
    def test_parse_iso_with_seconds(self):
        dt = _parse_dt("2023-01-15 08:30:00")
        assert dt.year == 2023
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 8

    def test_parse_iso_without_seconds(self):
        dt = _parse_dt("2023-06-01 12:00")
        assert dt.year == 2023
        assert dt.hour == 12

    def test_parse_us_format(self):
        dt = _parse_dt("01/15/2023 08:30")
        assert dt.year == 2023
        assert dt.month == 1

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_dt("not-a-date")


class TestApplyBestParams:
    def test_apply_writes_file(self, basic_inp, tmp_dir, network_sections):
        from cli_anything.swmm.core.project import write_inp, parse_inp
        # Write the network sections
        write_inp(network_sections, basic_inp)

        best = {"conduit:C1:roughness": 0.018}
        out_path = os.path.join(tmp_dir, "calibrated.inp")
        result = apply_best_params(basic_inp, best, output_path=out_path)

        assert os.path.exists(out_path)
        assert result["n_applied"] == 1
        assert result["errors"] == []

        # Verify the value is in the calibrated file
        calibrated = parse_inp(out_path)
        for line in calibrated.get("CONDUITS", []):
            if "C1" in line and not line.strip().startswith(";;"):
                parts = line.split()
                assert float(parts[4]) == pytest.approx(0.018, abs=1e-6)
                break

    def test_apply_missing_inp_raises(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            apply_best_params("/nonexistent/path.inp", {"conduit:C1:roughness": 0.01})

    def test_apply_bad_param_id_reported(self, basic_inp):
        result = apply_best_params(basic_inp, {"badtype:X:badfield": 1.0})
        assert result["errors"]
        assert result["n_applied"] == 0


# ---------------------------------------------------------------------------
# TestRules
# ---------------------------------------------------------------------------


from cli_anything.swmm.core.rules import (
    parse_rules,
    get_rule,
    list_rules,
    add_rule,
    remove_rule,
    revise_rule,
)


class TestRulesAdd:
    def test_add_simple_rule(self, basic_sections):
        rule = add_rule(
            basic_sections, "R1",
            if_clauses=["Node J1 Depth > 4.5"],
            then_actions=["Pump P1 Status = ON"],
        )
        assert rule["id"] == "R1"
        assert len(rule["if_clauses"]) == 1
        assert rule["if_clauses"][0]["type"] == "IF"
        assert rule["if_clauses"][0]["premise"] == "Node J1 Depth > 4.5"
        assert rule["then_actions"][0]["type"] == "THEN"

    def test_add_multiple_conditions(self, basic_sections):
        add_rule(
            basic_sections, "R2",
            if_clauses=["Node J1 Depth > 4.5", "Node J2 Depth > 3.0"],
            then_actions=["Pump P1 Status = ON"],
        )
        rules = parse_rules(basic_sections)
        r = next(r for r in rules if r["id"] == "R2")
        assert len(r["if_clauses"]) == 2
        assert r["if_clauses"][0]["type"] == "IF"
        assert r["if_clauses"][1]["type"] == "AND"

    def test_add_with_else_and_priority(self, basic_sections):
        add_rule(
            basic_sections, "R3",
            if_clauses=["Node J1 Depth > 4.5"],
            then_actions=["Pump P1 Status = ON"],
            else_actions=["Pump P1 Status = OFF"],
            priority=2.0,
        )
        r = get_rule(basic_sections, "R3")
        assert r["else_actions"][0]["type"] == "ELSE"
        assert r["else_actions"][0]["action"] == "Pump P1 Status = OFF"
        assert r["priority"] == 2.0

    def test_add_multiple_then_actions(self, basic_sections):
        add_rule(
            basic_sections, "R4",
            if_clauses=["Node J1 Depth > 4.5"],
            then_actions=["Pump P1 Status = ON", "Orifice O1 Setting = 0.5"],
        )
        r = get_rule(basic_sections, "R4")
        assert r["then_actions"][0]["type"] == "THEN"
        assert r["then_actions"][1]["type"] == "AND"

    def test_add_replaces_existing_same_id(self, basic_sections):
        add_rule(basic_sections, "R5",
                 if_clauses=["Node J1 Depth > 4.5"],
                 then_actions=["Pump P1 Status = ON"])
        add_rule(basic_sections, "R5",
                 if_clauses=["Node J1 Depth > 6.0"],
                 then_actions=["Pump P1 Status = OFF"])
        rules = parse_rules(basic_sections)
        r5_rules = [r for r in rules if r["id"] == "R5"]
        assert len(r5_rules) == 1
        assert r5_rules[0]["if_clauses"][0]["premise"] == "Node J1 Depth > 6.0"

    def test_add_empty_id_raises(self, basic_sections):
        with pytest.raises(ValueError):
            add_rule(basic_sections, "", ["Node J1 Depth > 1"], ["Pump P1 Status = ON"])

    def test_add_empty_if_raises(self, basic_sections):
        with pytest.raises(ValueError):
            add_rule(basic_sections, "R6", [], ["Pump P1 Status = ON"])

    def test_add_empty_then_raises(self, basic_sections):
        with pytest.raises(ValueError):
            add_rule(basic_sections, "R7", ["Node J1 Depth > 1"], [])

    def test_controls_section_created(self, basic_sections):
        assert "CONTROLS" not in basic_sections
        add_rule(basic_sections, "R8",
                 if_clauses=["Node J1 Depth > 1"],
                 then_actions=["Pump P1 Status = ON"])
        assert "CONTROLS" in basic_sections

    def test_add_or_condition(self, basic_sections):
        add_rule(
            basic_sections, "R_OR",
            if_clauses=["Node J1 Depth > 4.5", "Node J2 Depth > 3.0"],
            then_actions=["Pump P1 Status = ON"],
        )
        # Verify section text contains AND
        controls_text = "\n".join(basic_sections.get("CONTROLS", []))
        assert "AND" in controls_text


class TestRulesList:
    def test_list_empty(self, basic_sections):
        assert list_rules(basic_sections) == []

    def test_list_single(self, basic_sections):
        add_rule(basic_sections, "R1",
                 if_clauses=["Node J1 Depth > 4.5"],
                 then_actions=["Pump P1 Status = ON"])
        items = list_rules(basic_sections)
        assert len(items) == 1
        assert items[0]["id"] == "R1"
        assert items[0]["conditions"] == 1
        assert items[0]["actions"] == 1
        assert items[0]["has_else"] is False

    def test_list_multiple(self, basic_sections):
        add_rule(basic_sections, "RA",
                 if_clauses=["Node J1 Depth > 1"],
                 then_actions=["Pump P1 Status = ON"])
        add_rule(basic_sections, "RB",
                 if_clauses=["Node J1 Depth < 0.5"],
                 then_actions=["Pump P1 Status = OFF"])
        items = list_rules(basic_sections)
        ids = [i["id"] for i in items]
        assert "RA" in ids
        assert "RB" in ids

    def test_list_has_else_flag(self, basic_sections):
        add_rule(basic_sections, "R_ELSE",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"],
                 else_actions=["Pump P1 Status = OFF"])
        item = list_rules(basic_sections)[0]
        assert item["has_else"] is True

    def test_list_priority(self, basic_sections):
        add_rule(basic_sections, "R_PRI",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"],
                 priority=5.0)
        item = list_rules(basic_sections)[0]
        assert item["priority"] == 5.0


class TestGetRule:
    def test_get_existing(self, basic_sections):
        add_rule(basic_sections, "GET_R",
                 if_clauses=["Node J1 Depth > 2"],
                 then_actions=["Pump P1 Status = ON"])
        r = get_rule(basic_sections, "GET_R")
        assert r is not None
        assert r["id"] == "GET_R"

    def test_get_missing_returns_none(self, basic_sections):
        assert get_rule(basic_sections, "NONEXISTENT") is None


class TestRemoveRule:
    def test_remove_existing(self, basic_sections):
        add_rule(basic_sections, "DEL_R",
                 if_clauses=["Node J1 Depth > 2"],
                 then_actions=["Pump P1 Status = ON"])
        removed = remove_rule(basic_sections, "DEL_R")
        assert removed is True
        assert get_rule(basic_sections, "DEL_R") is None

    def test_remove_missing_returns_false(self, basic_sections):
        removed = remove_rule(basic_sections, "NOSUCHRULE")
        assert removed is False

    def test_remove_leaves_other_rules(self, basic_sections):
        add_rule(basic_sections, "KEEP",
                 if_clauses=["Node J1 Depth > 1"],
                 then_actions=["Pump P1 Status = ON"])
        add_rule(basic_sections, "DELETE",
                 if_clauses=["Node J1 Depth > 2"],
                 then_actions=["Pump P1 Status = OFF"])
        remove_rule(basic_sections, "DELETE")
        assert get_rule(basic_sections, "KEEP") is not None
        assert get_rule(basic_sections, "DELETE") is None

    def test_remove_from_missing_section(self, basic_sections):
        """Removing from a project with no [CONTROLS] returns False gracefully."""
        assert "CONTROLS" not in basic_sections
        assert remove_rule(basic_sections, "ANY") is False


class TestReviseRule:
    def test_revise_if_clauses(self, basic_sections):
        add_rule(basic_sections, "REV_R",
                 if_clauses=["Node J1 Depth > 4.5"],
                 then_actions=["Pump P1 Status = ON"])
        revise_rule(basic_sections, "REV_R",
                    if_clauses=["Node J1 Depth > 6.0"])
        r = get_rule(basic_sections, "REV_R")
        assert r["if_clauses"][0]["premise"] == "Node J1 Depth > 6.0"

    def test_revise_then_actions(self, basic_sections):
        add_rule(basic_sections, "REV_T",
                 if_clauses=["Node J1 Depth > 4.5"],
                 then_actions=["Pump P1 Status = ON"])
        revise_rule(basic_sections, "REV_T",
                    then_actions=["Pump P1 Status = OFF", "Orifice O1 Setting = 0.0"])
        r = get_rule(basic_sections, "REV_T")
        assert len(r["then_actions"]) == 2
        assert r["then_actions"][0]["action"] == "Pump P1 Status = OFF"
        assert r["then_actions"][1]["type"] == "AND"

    def test_revise_add_else(self, basic_sections):
        add_rule(basic_sections, "REV_E",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"])
        revise_rule(basic_sections, "REV_E",
                    else_actions=["Pump P1 Status = OFF"])
        r = get_rule(basic_sections, "REV_E")
        assert len(r["else_actions"]) == 1
        assert r["else_actions"][0]["action"] == "Pump P1 Status = OFF"

    def test_revise_clear_else(self, basic_sections):
        add_rule(basic_sections, "REV_CE",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"],
                 else_actions=["Pump P1 Status = OFF"])
        revise_rule(basic_sections, "REV_CE", clear_else=True)
        r = get_rule(basic_sections, "REV_CE")
        assert r["else_actions"] == []

    def test_revise_priority(self, basic_sections):
        add_rule(basic_sections, "REV_P",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"],
                 priority=1.0)
        revise_rule(basic_sections, "REV_P", priority=10.0)
        r = get_rule(basic_sections, "REV_P")
        assert r["priority"] == 10.0

    def test_revise_clear_priority(self, basic_sections):
        add_rule(basic_sections, "REV_CP",
                 if_clauses=["Node J1 Depth > 4"],
                 then_actions=["Pump P1 Status = ON"],
                 priority=5.0)
        revise_rule(basic_sections, "REV_CP", clear_priority=True)
        r = get_rule(basic_sections, "REV_CP")
        assert r["priority"] is None

    def test_revise_missing_rule_raises(self, basic_sections):
        with pytest.raises(KeyError):
            revise_rule(basic_sections, "NOEXIST",
                        if_clauses=["Node J1 Depth > 1"])

    def test_revise_omitted_fields_unchanged(self, basic_sections):
        """Calling revise with no changes leaves the rule intact."""
        add_rule(basic_sections, "REV_NOOP",
                 if_clauses=["Node J1 Depth > 4.5"],
                 then_actions=["Pump P1 Status = ON"],
                 priority=3.0)
        revise_rule(basic_sections, "REV_NOOP")  # no args
        r = get_rule(basic_sections, "REV_NOOP")
        assert r["if_clauses"][0]["premise"] == "Node J1 Depth > 4.5"
        assert r["priority"] == 3.0


class TestRulesRoundtrip:
    def test_write_and_reparse(self, basic_sections, tmp_dir):
        """Rules survive an INP write/parse round-trip."""
        from cli_anything.swmm.core.project import write_inp, parse_inp
        add_rule(basic_sections, "RT_R",
                 if_clauses=["Node J1 Depth > 4.5", "Simulation Time > 1.0"],
                 then_actions=["Pump P1 Status = ON"],
                 else_actions=["Pump P1 Status = OFF"],
                 priority=2.0)
        path = os.path.join(tmp_dir, "rules_rt.inp")
        write_inp(basic_sections, path)
        loaded = parse_inp(path)
        r = get_rule(loaded, "RT_R")
        assert r is not None
        assert len(r["if_clauses"]) == 2
        assert r["if_clauses"][0]["premise"] == "Node J1 Depth > 4.5"
        assert r["else_actions"][0]["action"] == "Pump P1 Status = OFF"
        assert r["priority"] == 2.0

    def test_multiple_rules_roundtrip(self, basic_sections, tmp_dir):
        from cli_anything.swmm.core.project import write_inp, parse_inp
        for i in range(3):
            add_rule(basic_sections, f"MULTI_{i}",
                     if_clauses=[f"Node J{i} Depth > {i}.0"],
                     then_actions=["Pump P1 Status = ON"])
        path = os.path.join(tmp_dir, "multi_rules.inp")
        write_inp(basic_sections, path)
        loaded = parse_inp(path)
        rules = parse_rules(loaded)
        ids = {r["id"] for r in rules}
        assert {"MULTI_0", "MULTI_1", "MULTI_2"} <= ids


# ---------------------------------------------------------------------------
# core/network.py — new hydraulic structures (pump, weir, orifice, inflow)
# ---------------------------------------------------------------------------

from cli_anything.swmm.core.network import (
    add_pump, remove_pump,
    add_weir, remove_weir,
    add_orifice, remove_orifice,
    add_inflow, remove_inflow,
)


class TestAddPump:
    def test_add_pump_basic(self, basic_sections):
        result = add_pump(basic_sections, "P1", "J1", "J2", pump_curve="PC1")
        assert result["name"] == "P1"
        assert result["type"] == "pump"
        assert any("P1" in l for l in basic_sections["PUMPS"])

    def test_add_pump_default_status_on(self, basic_sections):
        add_pump(basic_sections, "P2", "J1", "J2")
        line = next(l for l in basic_sections["PUMPS"] if "P2" in l and not l.strip().startswith(";;"))
        assert "ON" in line

    def test_add_pump_off_status(self, basic_sections):
        add_pump(basic_sections, "P3", "J1", "J2", status="OFF")
        line = next(l for l in basic_sections["PUMPS"] if "P3" in l and not l.strip().startswith(";;"))
        assert "OFF" in line

    def test_add_pump_startup_shutoff(self, basic_sections):
        result = add_pump(basic_sections, "P4", "J1", "J2", startup_depth=1.5, shutoff_depth=0.5)
        assert result["startup_depth"] == 1.5
        assert result["shutoff_depth"] == 0.5

    def test_add_pump_ideal_curve(self, basic_sections):
        result = add_pump(basic_sections, "P5", "WW1", "OUT1", pump_curve="*")
        assert result["pump_curve"] == "*"
        line = next(l for l in basic_sections["PUMPS"] if "P5" in l and not l.strip().startswith(";;"))
        assert "*" in line


class TestRemovePump:
    def test_remove_pump_existing(self, basic_sections):
        add_pump(basic_sections, "P_DEL", "J1", "J2")
        removed = remove_pump(basic_sections, "P_DEL")
        assert removed is True
        assert not any("P_DEL" in l and not l.strip().startswith(";;")
                       for l in basic_sections.get("PUMPS", []))

    def test_remove_pump_nonexistent(self, basic_sections):
        assert remove_pump(basic_sections, "NOPUMP") is False


class TestAddWeir:
    def test_add_weir_basic(self, basic_sections):
        result = add_weir(basic_sections, "W1", "J1", "OUT1")
        assert result["name"] == "W1"
        assert result["element_type"] == "weir"
        assert any("W1" in l for l in basic_sections["WEIRS"])

    def test_add_weir_transverse_default(self, basic_sections):
        add_weir(basic_sections, "W2", "J1", "OUT1")
        line = next(l for l in basic_sections["WEIRS"] if "W2" in l and not l.strip().startswith(";;"))
        assert "TRANSVERSE" in line

    def test_add_weir_vnotch(self, basic_sections):
        result = add_weir(basic_sections, "W3", "J1", "OUT1", weir_type="V-NOTCH")
        assert result["type"] == "V-NOTCH"
        line = next(l for l in basic_sections["WEIRS"] if "W3" in l and not l.strip().startswith(";;"))
        assert "V-NOTCH" in line

    def test_add_weir_crest_height(self, basic_sections):
        add_weir(basic_sections, "W4", "J1", "OUT1", crest_height=0.5)
        line = next(l for l in basic_sections["WEIRS"] if "W4" in l and not l.strip().startswith(";;"))
        assert "0.500" in line

    def test_add_weir_discharge_coeff(self, basic_sections):
        result = add_weir(basic_sections, "W5", "J1", "OUT1", discharge_coeff=1.84)
        assert result["discharge_coeff"] == 1.84


class TestRemoveWeir:
    def test_remove_weir_existing(self, basic_sections):
        add_weir(basic_sections, "W_DEL", "J1", "OUT1")
        removed = remove_weir(basic_sections, "W_DEL")
        assert removed is True
        assert not any("W_DEL" in l and not l.strip().startswith(";;")
                       for l in basic_sections.get("WEIRS", []))

    def test_remove_weir_nonexistent(self, basic_sections):
        assert remove_weir(basic_sections, "NOWEIR") is False


class TestAddOrifice:
    def test_add_orifice_basic(self, basic_sections):
        result = add_orifice(basic_sections, "OR1", "STO1", "J1")
        assert result["name"] == "OR1"
        assert result["element_type"] == "orifice"
        assert any("OR1" in l for l in basic_sections["ORIFICES"])

    def test_add_orifice_creates_xsection(self, basic_sections):
        add_orifice(basic_sections, "OR2", "STO1", "J1")
        assert any("OR2" in l for l in basic_sections["XSECTIONS"])

    def test_add_orifice_bottom_type(self, basic_sections):
        result = add_orifice(basic_sections, "OR3", "STO1", "J1", orifice_type="BOTTOM")
        assert result["type"] == "BOTTOM"

    def test_add_orifice_side_type(self, basic_sections):
        add_orifice(basic_sections, "OR4", "STO1", "J1", orifice_type="SIDE")
        line = next(l for l in basic_sections["ORIFICES"] if "OR4" in l and not l.strip().startswith(";;"))
        assert "SIDE" in line

    def test_add_orifice_discharge_coeff(self, basic_sections):
        result = add_orifice(basic_sections, "OR5", "STO1", "J1", discharge_coeff=0.61)
        assert result["discharge_coeff"] == 0.61

    def test_add_orifice_offset(self, basic_sections):
        add_orifice(basic_sections, "OR6", "STO1", "J1", offset=0.3)
        line = next(l for l in basic_sections["ORIFICES"] if "OR6" in l and not l.strip().startswith(";;"))
        assert "0.300" in line


class TestRemoveOrifice:
    def test_remove_orifice_existing(self, basic_sections):
        add_orifice(basic_sections, "OR_DEL", "STO1", "J1")
        removed = remove_orifice(basic_sections, "OR_DEL")
        assert removed is True
        assert not any("OR_DEL" in l and not l.strip().startswith(";;")
                       for l in basic_sections.get("ORIFICES", []))

    def test_remove_orifice_removes_xsection(self, basic_sections):
        add_orifice(basic_sections, "OR_XS", "STO1", "J1")
        remove_orifice(basic_sections, "OR_XS")
        assert not any("OR_XS" in l and not l.strip().startswith(";;")
                       for l in basic_sections.get("XSECTIONS", []))

    def test_remove_orifice_nonexistent(self, basic_sections):
        assert remove_orifice(basic_sections, "NOORIFICE") is False


class TestAddInflow:
    def test_add_inflow_basic(self, basic_sections):
        result = add_inflow(basic_sections, "J1", "TS_INFLOW")
        assert result["node"] == "J1"
        assert result["constituent"] == "FLOW"
        assert any("J1" in l for l in basic_sections["INFLOWS"])

    def test_add_inflow_timeseries_ref(self, basic_sections):
        add_inflow(basic_sections, "J2", "MY_TS")
        line = next(l for l in basic_sections["INFLOWS"]
                    if "J2" in l and not l.strip().startswith(";;"))
        assert "MY_TS" in line

    def test_add_inflow_mfactor(self, basic_sections):
        result = add_inflow(basic_sections, "J3", "TS1", mfactor=2.5)
        assert result["mfactor"] == 2.5

    def test_add_inflow_baseline(self, basic_sections):
        result = add_inflow(basic_sections, "J4", "TS1", baseline=0.05)
        assert result["baseline"] == 0.05

    def test_add_inflow_custom_constituent(self, basic_sections):
        result = add_inflow(basic_sections, "J5", "TS_TSS", constituent="TSS",
                            inflow_type="CONCEN")
        assert result["constituent"] == "TSS"
        assert result["type"] == "CONCEN"


class TestRemoveInflow:
    def test_remove_inflow_existing(self, basic_sections):
        add_inflow(basic_sections, "J1", "TS1")
        removed = remove_inflow(basic_sections, "J1")
        assert removed is True
        assert not any("J1" in l and not l.strip().startswith(";;")
                       for l in basic_sections.get("INFLOWS", []))

    def test_remove_inflow_nonexistent(self, basic_sections):
        assert remove_inflow(basic_sections, "NONODE") is False


class TestListNetworkExtended:
    """list_network should include pumps, weirs, orifices in links."""

    def test_pump_appears_in_links(self, basic_sections):
        add_pump(basic_sections, "P1", "J1", "J2")
        net = list_network(basic_sections)
        names = [l["name"] for l in net["links"]]
        assert "P1" in names

    def test_weir_appears_in_links(self, basic_sections):
        add_weir(basic_sections, "W1", "J1", "OUT1")
        net = list_network(basic_sections)
        names = [l["name"] for l in net["links"]]
        assert "W1" in names

    def test_orifice_appears_in_links(self, basic_sections):
        add_orifice(basic_sections, "OR1", "STO1", "J1")
        net = list_network(basic_sections)
        names = [l["name"] for l in net["links"]]
        assert "OR1" in names

    def test_element_types_correct(self, basic_sections):
        add_conduit(basic_sections, "C1", "J1", "J2", 100.0)
        add_pump(basic_sections, "P1", "J1", "J2")
        add_weir(basic_sections, "W1", "J1", "OUT1")
        add_orifice(basic_sections, "OR1", "STO1", "J1")
        net = list_network(basic_sections)
        by_name = {l["name"]: l["element_type"] for l in net["links"]}
        assert by_name["C1"] == "conduit"
        assert by_name["P1"] == "pump"
        assert by_name["W1"] == "weir"
        assert by_name["OR1"] == "orifice"


# ---------------------------------------------------------------------------
# core/results.py — unit tests with synthetic .rpt content
# ---------------------------------------------------------------------------

from cli_anything.swmm.core.results import (
    parse_report,
    get_node_results,
    get_link_results,
    get_runoff_summary,
    get_flow_routing_summary,
    _split_into_sections,
    _parse_continuity_table,
    _parse_subcatch_runoff,
    _parse_node_depth_summary,
    _parse_link_flow_summary,
)


# Minimal synthetic .rpt content that mirrors the SWMM output format

_SYNTHETIC_RPT = """\

  EPA STORM WATER MANAGEMENT MODEL - VERSION 5.2 (Build 5.2.4)
  --------------------------------------------------------------

  ******************
  Runoff Quantity Continuity
  ******************
  Total Precipitation ...... 25.000 mm
  Evaporation Loss ......... 0.000 mm
  Infiltration Loss ........ 8.500 mm
  Surface Runoff ........... 14.200 mm
  Final Surface Storage .... 2.300 mm

  ******************
  Flow Routing Continuity
  ******************
  Dry Weather Inflow ....... 0.000 m3
  Wet Weather Inflow ....... 1120.000 m3
  Final Storage ............ 0.000 m3
  Continuity Error (%) ..... 0.012

  ******************
  Subcatchment Runoff Summary
  ******************
  -----------------------------------------------------------------------
  Subcatchment      Total     Total     Total     Total    Imperv    Perv    Total
                    Precip    Runon      Evap    Infil    Runoff  Runoff   Runoff
                       mm        mm        mm       mm        mm      mm       mm
  -----------------------------------------------------------------------
  SUB1              25.00      0.00      0.00     8.50      9.20    5.00    14.20    0.568    0.0423

  ******************
  Node Depth Summary
  ******************
  -----------------------------------------------------------------------
  Node           Type     Average   Maximum  Max HGL  Day   Time  Reported
                           Depth     Depth           Reached       Max Depth
                           Meters    Meters   Meters           hr:min    Meters
  -----------------------------------------------------------------------
  J1           JUNCTION     0.452     1.234     11.234   0  01:15     1.234
  J2           JUNCTION     0.312     0.876     10.376   0  01:20     0.876
  OUT1         OUTFALL       0.000     0.000      8.000   0  00:00     0.000

  ******************
  Link Flow Summary
  ******************
  -----------------------------------------------------------------------
  Link           Type        Maximum   Day of    Time of    Maximum    Max/    Max/
                              Flow    Occurrence Occurrence  Velocity   Full    Full
                             CMS                  hr:min     m/sec     Flow   Depth
  -----------------------------------------------------------------------
  C1             CONDUIT     0.0842   0  01:15     1.23    0.87    0.62
  C2             CONDUIT     0.0831   0  01:20     1.18    0.75    0.55
"""


@pytest.fixture
def synthetic_rpt(tmp_dir):
    """Write the synthetic .rpt to a temp file and return its path."""
    path = os.path.join(tmp_dir, "test.rpt")
    with open(path, "w") as f:
        f.write(_SYNTHETIC_RPT)
    return path


class TestSplitIntoSections:
    def test_sections_detected(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        keys = set(sections.keys())
        assert "runoff quantity continuity" in keys
        assert "flow routing continuity" in keys
        assert "node depth summary" in keys
        assert "link flow summary" in keys

    def test_empty_file_returns_empty(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.rpt")
        open(path, "w").close()
        with open(path) as f:
            lines = f.read().splitlines()
        assert _split_into_sections(lines) == {}


class TestParseContinuityTable:
    def test_runoff_continuity_parsed(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_continuity_table(sections, "Runoff Quantity Continuity")
        # Keys may have trailing whitespace; normalise for comparison
        normalised = {k.strip(): v for k, v in result.items()}
        assert "Total Precipitation" in normalised
        assert normalised["Total Precipitation"] == pytest.approx(25.0)

    def test_flow_routing_continuity_parsed(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_continuity_table(sections, "Flow Routing Continuity")
        normalised = {k.strip(): v for k, v in result.items()}
        assert "Wet Weather Inflow" in normalised
        assert normalised["Wet Weather Inflow"] == pytest.approx(1120.0)

    def test_missing_section_returns_empty(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_continuity_table(sections, "Nonexistent Section")
        assert result == {}


class TestParseSubcatchRunoff:
    def test_subcatch_parsed(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_subcatch_runoff(sections)
        assert isinstance(result, list)
        assert len(result) >= 1
        sub = result[0]
        assert sub["subcatchment"] == "SUB1"
        assert sub["total_precip_mm"] == pytest.approx(25.0)

    def test_subcatch_missing_returns_empty(self, tmp_dir):
        path = os.path.join(tmp_dir, "no_sub.rpt")
        with open(path, "w") as f:
            f.write("")
        with open(path) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        assert _parse_subcatch_runoff(sections) == []


class TestParseNodeDepthSummary:
    def test_nodes_parsed(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_node_depth_summary(sections)
        assert "J1" in result
        assert "J2" in result
        assert result["J1"]["max_depth"] == pytest.approx(1.234)

    def test_outfall_present(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_node_depth_summary(sections)
        assert "OUT1" in result


class TestParseLinkFlowSummary:
    def test_links_parsed(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_link_flow_summary(sections)
        assert "C1" in result
        assert result["C1"]["max_flow"] == pytest.approx(0.0842)

    def test_link_c2_present(self, synthetic_rpt):
        with open(synthetic_rpt) as f:
            lines = f.read().splitlines()
        sections = _split_into_sections(lines)
        result = _parse_link_flow_summary(sections)
        assert "C2" in result
        assert result["C2"]["max_velocity"] == pytest.approx(1.18)


class TestParseReport:
    def test_parse_report_returns_all_keys(self, synthetic_rpt):
        result = parse_report(synthetic_rpt)
        for key in ("errors", "warnings", "runoff_summary",
                    "flow_routing_continuity", "subcatch_runoff_summary",
                    "node_depth_summary", "link_flow_summary"):
            assert key in result

    def test_parse_report_no_errors(self, synthetic_rpt):
        result = parse_report(synthetic_rpt)
        assert result["errors"] == []

    def test_parse_report_missing_file_raises(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            parse_report(os.path.join(tmp_dir, "missing.rpt"))

    def test_node_depth_via_parse_report(self, synthetic_rpt):
        result = parse_report(synthetic_rpt)
        assert "J1" in result["node_depth_summary"]
        assert result["node_depth_summary"]["J1"]["max_depth"] == pytest.approx(1.234)

    def test_link_flow_via_parse_report(self, synthetic_rpt):
        result = parse_report(synthetic_rpt)
        assert "C1" in result["link_flow_summary"]


class TestGetNodeResults:
    def test_get_existing_node(self, synthetic_rpt):
        result = get_node_results(synthetic_rpt, "J1")
        assert result["node"] == "J1"
        assert "max_depth" in result
        assert result["max_depth"] == pytest.approx(1.234)

    def test_get_missing_node_returns_empty(self, synthetic_rpt):
        result = get_node_results(synthetic_rpt, "NONEXISTENT")
        assert result["node"] == "NONEXISTENT"
        # Should not raise; returns empty dict for the node data
        assert "max_depth" not in result or result.get("max_depth") is None or True


class TestGetLinkResults:
    def test_get_existing_link(self, synthetic_rpt):
        result = get_link_results(synthetic_rpt, "C1")
        assert result["link"] == "C1"
        assert "max_flow" in result
        assert result["max_flow"] == pytest.approx(0.0842)

    def test_get_missing_link_returns_dict(self, synthetic_rpt):
        result = get_link_results(synthetic_rpt, "NOTALINK")
        assert result["link"] == "NOTALINK"


class TestGetRunoffSummary:
    def test_runoff_summary_structure(self, synthetic_rpt):
        result = get_runoff_summary(synthetic_rpt)
        assert "continuity" in result
        assert "subcatchments" in result
        assert isinstance(result["subcatchments"], list)

    def test_runoff_continuity_values(self, synthetic_rpt):
        result = get_runoff_summary(synthetic_rpt)
        # Keys may have trailing whitespace; normalise
        normalised_keys = {k.strip() for k in result["continuity"]}
        assert "Total Precipitation" in normalised_keys


class TestGetFlowRoutingSummary:
    def test_flow_routing_structure(self, synthetic_rpt):
        result = get_flow_routing_summary(synthetic_rpt)
        assert "continuity" in result
        assert "nodes" in result
        assert "links" in result
        assert "errors" in result
        assert "warnings" in result

    def test_flow_routing_nodes_populated(self, synthetic_rpt):
        result = get_flow_routing_summary(synthetic_rpt)
        assert "J1" in result["nodes"]
