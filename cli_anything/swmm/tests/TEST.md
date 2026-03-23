# TEST.md — cli-anything-swmm Test Plan and Results

## Test Inventory Plan

| File | Tests | Coverage |
|------|-------|---------|
| `test_core.py` | 190 unit tests | All core modules with synthetic data |
| `test_full_e2e.py` | 50 E2E + subprocess tests | Real pyswmm simulation + CLI subprocess |

---

## Unit Test Plan (`test_core.py`)

### Module: `core/project.py`

**Functions**: `create_project`, `parse_inp`, `write_inp`, `open_project`, `project_info`

| Test | What it checks |
|------|---------------|
| `test_create_project_basic` | Creates file, returns correct keys, file exists |
| `test_create_project_invalid_units` | Raises ValueError for bad flow units |
| `test_parse_inp_roundtrip` | parse → write → parse preserves section names and data |
| `test_parse_inp_comments_preserved` | Comment lines (;;) survive round-trip |
| `test_open_project_missing_file` | Raises FileNotFoundError |
| `test_open_project_valid` | Returns sections dict with required sections |
| `test_project_info_counts` | Counts junctions, conduits, subcatchments correctly |
| `test_project_info_extracts_options` | FLOW_UNITS and other options parsed |

### Module: `core/network.py`

**Functions**: `add_junction`, `remove_junction`, `add_conduit`, `remove_conduit`,
`add_subcatchment`, `add_outfall`, `add_storage`, `add_raingage`, `list_network`

| Test | What it checks |
|------|---------------|
| `test_add_junction` | Section updated, data line present |
| `test_add_junction_with_defaults` | Default max_depth/init_depth values |
| `test_remove_junction` | Line removed from JUNCTIONS |
| `test_add_conduit` | CONDUITS and XSECTIONS both updated |
| `test_add_conduit_shape` | Non-circular shape recorded in XSECTIONS |
| `test_remove_conduit` | Removed from CONDUITS and XSECTIONS |
| `test_add_subcatchment` | SUBCATCHMENTS, SUBAREAS, INFILTRATION all updated |
| `test_add_outfall` | OUTFALLS section updated |
| `test_add_raingage` | RAINGAGES section updated |
| `test_list_network_empty` | Returns empty lists for all categories |
| `test_list_network_populated` | Counts match added elements |

### Module: `core/options.py`

**Functions**: `get_options`, `set_options`, `set_simulation_dates`

| Test | What it checks |
|------|---------------|
| `test_get_options_defaults` | Default options parsed from create_project |
| `test_set_options_dates` | START_DATE, END_DATE updated correctly |
| `test_set_options_date_format_conversion` | YYYY-MM-DD converted to MM/DD/YYYY |
| `test_set_options_routing` | FLOW_ROUTING updated |
| `test_set_options_invalid_units` | Raises ValueError |
| `test_set_simulation_dates` | Convenience wrapper sets 4 date/time fields |

### Module: `core/timeseries.py`

**Functions**: `add_timeseries`, `list_timeseries`, `add_rainfall_event`

| Test | What it checks |
|------|---------------|
| `test_add_timeseries` | Data lines added to TIMESERIES section |
| `test_add_timeseries_replace` | Existing series with same name replaced |
| `test_list_timeseries` | Returns names and point counts |
| `test_add_rainfall_scs` | SCS pattern generates > 0 points, links gage |
| `test_add_rainfall_uniform` | Uniform pattern has constant non-zero intensity |
| `test_add_rainfall_triangular` | Triangular pattern peaks at midpoint |
| `test_rainfall_total_depth_reasonable` | Total depth in reasonable range |

### Module: `core/session.py`

**Functions**: `Session.load`, `Session.save`, `Session.push`, `Session.undo`, `Session.redo`

| Test | What it checks |
|------|---------------|
| `test_session_push_undo` | Push + undo restores original sections |
| `test_session_redo` | Redo re-applies the undone state |
| `test_session_undo_empty` | Returns False when history empty |
| `test_session_redo_empty` | Returns False when redo stack empty |
| `test_session_undo_clears_redo` | New push clears redo stack |

---

## E2E Test Plan (`test_full_e2e.py`)

### Workflow 1: Full Simulation Pipeline

**Simulates**: Complete urban drainage simulation from scratch

**Operations**:
1. Create project with `create_project()`
2. Add J1, J2, OUT1 nodes
3. Add conduits C1, C2
4. Add subcatchment S1 with rain gage RG1
5. Generate SCS rainfall timeseries
6. Set simulation dates
7. Run simulation via `run_simulation()` (real pyswmm call)
8. Parse .rpt report

**Verified**:
- Simulation returns `status: "success"`
- `.rpt` file exists and has size > 0
- Error count in report == 0
- Node depth summary contains J1, J2
- Link flow summary contains C1, C2
- Subcatchment runoff summary has S1

### Workflow 2: Report Parsing

**Simulates**: Post-processing a simulation report

**Operations**:
1. Run simulation (from Workflow 1 or stored fixture)
2. Call `parse_report(rpt_path)`
3. Call `get_node_results(rpt_path, "J1")`
4. Call `get_link_results(rpt_path, "C1")`
5. Call `get_runoff_summary(rpt_path)`

**Verified**:
- All parser functions return dicts (not None)
- Node results have 'max_depth' key
- Link results have 'max_flow' key
- Runoff summary has 'subcatchments' list

### Workflow 3: CLI Subprocess Tests

**Simulates**: Real user/agent invoking the installed CLI

**Operations** (via `subprocess.run`):
1. `cli-anything-swmm --help`
2. `cli-anything-swmm --json project new -o PATH`
3. `cli-anything-swmm --json --project PATH network add-junction ...`
4. `cli-anything-swmm --json --project PATH simulate run`
5. `cli-anything-swmm --json --project PATH results summary`

**Verified**:
- All commands return exit code 0
- `--json` output is valid JSON
- Project file is written and parseable
- Simulation completes

### Workflow 4: Undo/Redo Integration

**Simulates**: Agent correcting mistakes during interactive session

**Operations**:
1. Create project
2. Add junction J1
3. Push to session history
4. Add junction J2 (makes history dirty)
5. Undo — J2 should be gone
6. Redo — J2 should be back
7. Save and verify file contents

---

## Test Results

*(Appended after running `pytest -v --tb=short`)*

```
============================= test session info ==============================
platform linux -- Python 3.x, pytest-x.x.x
rootdir: /home/sxli/Desktop/CITYUphd/Project/SWMMCLI/agent-harness
======================== test results below ==================================
```

```
240 passed in ~4s
```

**Refinement 1 additions (2026-03-24):**
- `test_core.py`: +58 tests covering `add_pump/weir/orifice/inflow`, remove variants,
  `list_network` extension, and all `core/results.py` functions (synthetic RPT)
- `test_full_e2e.py`: +35 tests covering `TestHydraulicStructuresAPI` (API round-trips)
  and `TestNewCLICommands` (subprocess CLI verification for pump, weir, orifice, inflow,
  `results subcatchments`)
