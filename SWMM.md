# SWMM CLI Harness — Software-Specific SOP

## Overview

EPA SWMM 5 (Storm Water Management Model) is the industry-standard hydrological and hydraulic
simulator for urban drainage networks. It models rainfall-runoff processes, pipe network
flow routing, and water quality throughout a drainage system.

**Version**: SWMM 5.2.4
**License**: Public Domain (US EPA)
**Backend**: `pyswmm` 2.x — Python bindings to the compiled SWMM 5 engine (`libswmm5.so`)

---

## Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────────────────┐
│   cli-anything-swmm CLI (Click + REPL)              │  ← This harness
├─────────────────────────────────────────────────────┤
│   pyswmm 2.x Python API                             │  ← Required backend
├─────────────────────────────────────────────────────┤
│   SWMM 5.2.4 Engine (libswmm5.so, C compiled)       │  ← Real software
└─────────────────────────────────────────────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `swmm524_engine/` | C source code for the SWMM 5 engine |
| `swmm524_gui/` | Delphi/Pascal GUI (Windows-only, NOT used by this CLI) |
| `pyswmm` | Python wrapper — the backend this CLI uses |
| `swmm-toolkit` | Lower-level toolkit with binary output parsing |
| `.inp` files | The native project format (text, section-based) |
| `.rpt` files | Human-readable simulation reports |
| `.out` files | Binary time-series output (queryable via swmm-toolkit) |

---

## The .inp File Format

SWMM input files are structured text files with bracketed section headers. Each section
contains tabular data with comment lines prefixed by `;;`.

### Required Sections

| Section | Purpose |
|---------|---------|
| `[TITLE]` | Project name and description |
| `[OPTIONS]` | Simulation settings (dates, routing method, flow units) |
| `[RAINGAGES]` | Rainfall measurement stations |
| `[SUBCATCHMENTS]` | Catchment areas draining to nodes |
| `[SUBAREAS]` | Subcatchment surface characteristics |
| `[INFILTRATION]` | Soil infiltration parameters (Horton, Green-Ampt, CN) |
| `[JUNCTIONS]` | Internal network nodes (manholes, inlets) |
| `[OUTFALLS]` | Terminal discharge points |
| `[CONDUITS]` | Pipes and channels connecting nodes |
| `[XSECTIONS]` | Cross-sectional shape for conduits |
| `[TIMESERIES]` | Time-varying rainfall/flow input data |
| `[REPORT]` | Reporting options |

### Optional Sections

| Section | Purpose |
|---------|---------|
| `[STORAGE]` | Detention basins, ponds |
| `[PUMPS]` | Pump stations |
| `[ORIFICES]` | Orifice structures |
| `[WEIRS]` | Weir structures |
| `[DIVIDERS]` | Flow splitters |
| `[CONTROLS]` | Rule-based control logic |
| `[INFLOWS]` | External hydrograph/pollutograph inputs |
| `[CURVES]` | Storage curves, rating curves, pump curves |
| `[PATTERNS]` | Diurnal patterns for DWF |
| `[COORDINATES]` | Node X-Y coordinates (for map display) |
| `[POLYGONS]` | Subcatchment boundary polygons |

### Example Options Section

```
[OPTIONS]
FLOW_UNITS           CMS
INFILTRATION         HORTON
FLOW_ROUTING         DYNWAVE
START_DATE           01/01/2023
START_TIME           00:00:00
END_DATE             01/01/2023
END_TIME             06:00:00
REPORT_STEP          00:05:00
WET_STEP             00:05:00
DRY_STEP             01:00:00
ROUTING_STEP         0:00:30
```

---

## Flow Routing Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| `DYNWAVE` | Dynamic wave (full St. Venant equations) | Backwater, surcharge, complex networks |
| `KINWAVE` | Kinematic wave | Simple dendritic networks |
| `STEADYSTATE` | Steady state | Static design flows |

**Recommendation**: Use `DYNWAVE` for realistic urban drainage modeling.

---

## Infiltration Methods

| Method | Description |
|--------|-------------|
| `HORTON` | Horton's exponential decay (Max rate, Min rate, Decay constant) |
| `MODIFIED_HORTON` | Horton with volume-based recovery |
| `GREEN_AMPT` | Green-Ampt ponding model |
| `MODIFIED_GREEN_AMPT` | Green-Ampt with capillary ponding |
| `CURVE_NUMBER` | SCS Curve Number method |

---

## pyswmm API Patterns

### Basic Simulation Run

```python
from pyswmm import Simulation

# Execute the full simulation
with Simulation("project.inp", rptfile="project.rpt") as sim:
    sim.execute()
    error_code = sim.getError()  # 0 = success
```

### Step-by-Step with Live Monitoring

```python
from pyswmm import Simulation, Nodes, Links, Subcatchments

with Simulation("project.inp") as sim:
    nodes = Nodes(sim)
    links = Links(sim)
    subs = Subcatchments(sim)

    for step in sim:
        t = sim.current_time
        for node in nodes:
            depth = node.depth           # m
            head = node.head             # m (elevation + depth)
            inflow = node.total_inflow   # m³/s
            flooding = node.flooding     # m³/s above crown

        for link in links:
            flow = link.flow             # m³/s
            depth = link.depth           # m
            velocity = link.velocity     # m/s

        for sub in subs:
            runoff = sub.runoff          # m³/s
            rainfall = sub.rainfall      # mm/hr
```

### Rain Gage Access

```python
from pyswmm import RainGages

with Simulation("project.inp") as sim:
    gages = RainGages(sim)
    for step in sim:
        for gage in gages:
            intensity = gage.rainfall    # mm/hr
```

---

## CLI Command Groups

### `project` — Project lifecycle
Manages the .inp project file: create, open, save, validate, inspect element counts.

### `network` — Network topology
Add and remove hydraulic elements: junctions, conduits, subcatchments, outfalls, raingages,
storage units, pumps, weirs, orifices, and external inflows.
Writes directly to the .inp file sections.

### `options` — Simulation parameters
Set and query simulation options: dates, routing method, flow units, timesteps.

### `timeseries` — Rainfall data
Add raw timeseries data or generate synthetic rainfall events (SCS Type II, uniform, triangular).

### `simulate` — Run engine
Execute simulations via `pyswmm.Simulation`. Validates .inp before running.

### `results` — Post-processing
Parse the .rpt report file: continuity errors, node depth summary, link flow summary,
subcatchment runoff summary (via `results subcatchments`).

---

## Workflow Examples

### Simple Drainage Network

```bash
# Create project
cli-anything-swmm project new -o urban.inp --title "Urban Catchment" --flow-units CMS

# Add two junctions and an outfall
cli-anything-swmm --project urban.inp network add-junction --name J1 --elevation 10.0 --max-depth 3.0
cli-anything-swmm --project urban.inp network add-junction --name J2 --elevation 9.5 --max-depth 3.0
cli-anything-swmm --project urban.inp network add-outfall --name OUT1 --elevation 8.0 --type FREE

# Connect with pipes (100m and 50m circular)
cli-anything-swmm --project urban.inp network add-conduit --name C1 --from J1 --to J2 --length 100 --diameter 0.9
cli-anything-swmm --project urban.inp network add-conduit --name C2 --from J2 --to OUT1 --length 50 --diameter 0.75

# Add rain gage and subcatchment
cli-anything-swmm --project urban.inp network add-raingage --name RG1 --timeseries STORM1
cli-anything-swmm --project urban.inp network add-subcatchment \
  --name SUB1 --raingage RG1 --outlet J1 --area 8.5 --pct-imperv 65 --width 150 --slope 1.2

# Generate 2-hour SCS storm with 30 mm/hr peak
cli-anything-swmm --project urban.inp timeseries rainfall \
  --name STORM1 --raingage RG1 \
  --start "2023-06-15 08:00" --duration 2 --peak 30 --pattern SCS

# Set simulation period
cli-anything-swmm --project urban.inp options set \
  --start-date 06/15/2023 --end-date 06/15/2023 \
  --start-time 08:00:00 --end-time 14:00:00 \
  --routing DYNWAVE

# Run simulation
cli-anything-swmm --project urban.inp simulate run

# Check results
cli-anything-swmm --project urban.inp results summary
cli-anything-swmm --project urban.inp results nodes
cli-anything-swmm --project urban.inp results links --name C1
```

### Rainfall-Runoff Pipeline (Scriptable)

```bash
#!/bin/bash
INP="catchment.inp"

cli-anything-swmm project new -o "$INP" --title "Rainfall-Runoff Study"
cli-anything-swmm --project "$INP" network add-junction --name J1 --elevation 5.0
cli-anything-swmm --project "$INP" network add-outfall --name OUT1 --elevation 4.0
cli-anything-swmm --project "$INP" network add-raingage --name RG1 --timeseries TS_DESIGN
cli-anything-swmm --project "$INP" network add-subcatchment \
  --name S1 --raingage RG1 --outlet J1 --area 20.0 --pct-imperv 40
cli-anything-swmm --project "$INP" timeseries rainfall \
  --name TS_DESIGN --raingage RG1 \
  --start "2023-01-01 00:00" --duration 6 --peak 50 --pattern SCS
cli-anything-swmm --project "$INP" options set \
  --start-date 01/01/2023 --end-date 01/01/2023 --end-time 12:00:00
cli-anything-swmm --json --project "$INP" simulate run | python3 -c "
import json, sys
r = json.load(sys.stdin)
print('Status:', r['status'])
print('Elapsed:', r['elapsed_time'], 's')
print('Report:', r['rpt_path'])
"
```

---

## Interactive REPL

Launch with no subcommand (or with `repl`):

```bash
cli-anything-swmm              # starts the REPL
cli-anything-swmm -p urban.inp # starts the REPL with a project pre-loaded
```

### Prompt format

```
◆ swmm [urban.inp*] ❯
```

- `◆` — cli-anything brand icon
- `swmm` — software name in accent color (water blue, ANSI 256 #45)
- `[urban.inp]` — basename of the active `.inp` file; absent when no project is loaded
- `*` — appears when the undo stack is non-empty (there are uncommitted edits)

### REPL built-in commands

| Command | Description |
|---------|-------------|
| `help` | Print all available commands and their descriptions |
| `status` | Show project path, section count, undo depth, redo depth |
| `undo` | Revert the last network/options/timeseries/rules mutation |
| `redo` | Re-apply the last undone mutation |
| `quit` / `exit` / `q` | Exit the REPL |

All other input is forwarded verbatim to the Click CLI (e.g. `network add-junction --name J1 --elevation 10.0`).

### Keyboard shortcuts (prompt_toolkit)

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate command history |
| `Ctrl+R` | Reverse incremental history search |
| `→` | Accept inline auto-suggestion from prior command |
| `Ctrl+C` | Cancel current input line |
| `Ctrl+D` | Exit REPL |

History is persisted across sessions at `~/.cli-anything-swmm/history`.

---

## Session State and Undo/Redo

The CLI maintains an in-process session with full undo/redo:

- `session.push()` — Snapshot current sections before any mutation
- `session.undo()` — Restore previous snapshot
- `session.redo()` — Re-apply the undone snapshot
- `session.save()` — Write current sections to the `.inp` file on disk

All `network`, `options`, `timeseries`, and `rules` commands auto-push before modifying and auto-save after. In the REPL, use `undo` / `redo` built-in commands or call them as subcommands in a script.

The session state is stored in `~/.cli-anything-swmm/<project>.session.json` and is locked with `fcntl` to prevent concurrent corruption.

---

## Known Limitations

1. **GUI features not supported**: Map layouts, visual editing require the SWMM GUI
2. **Binary .out parsing**: The `.out` binary output requires `swmm-toolkit` for detailed
   time-series extraction beyond what the `.rpt` file provides
3. **LID controls**: Low Impact Development controls are defined but not fully automated
   in the network builder — use direct .inp editing for complex LID configurations
4. **Pump curves**: `add-pump` links to a named pump curve (CURVES section) but no
   `curves add` command exists yet — define pump curves via direct .inp editing
5. **Dividers/Outtakes**: Flow splitter nodes (DIVIDERS section) are not yet exposed
