# cli-anything-swmm

A CLI harness for EPA SWMM 5 (Storm Water Management Model) built on the cli-anything methodology. Provides project management, network editing, simulation execution via pyswmm, and results parsing — all accessible from a single entry point with an optional interactive REPL.

## Installation

```bash
pip install -e /path/to/agent-harness
# or after publishing:
pip install cli-anything-swmm
```

Requires `pyswmm>=2.1.0` (brings `libswmm5.so` / SWMM 5 engine).

## Entry point

```
cli-anything-swmm [OPTIONS] COMMAND [ARGS]...
```

Global options:
- `--json` — emit structured JSON to stdout (status messages go to stderr)
- `-p / --project PATH` — set the active `.inp` file for subsequent commands
- `--version` — show version
- (no subcommand) — launch the interactive REPL

---

## Command groups

### `project` — Project management

| Command | Description |
|---------|-------------|
| `project new PATH [--title TEXT] [--flow-units CMS]` | Create a new minimal-valid SWMM `.inp` file |
| `project open PATH` | Open (validate path) an existing `.inp` |
| `project save [PATH]` | Save current project (no-op when using `-p`; useful in REPL) |
| `project info` | Show element counts and simulation options |
| `project validate PATH` | Validate a `.inp` by running `pyswmm.Simulation` input parsing |

**Example**

```bash
cli-anything-swmm project new my_model.inp --title "Tutorial Network" --flow-units CMS
cli-anything-swmm -p my_model.inp project info
```

---

### `network` — Network element management

| Command | Key options | Description |
|---------|-------------|-------------|
| `network add-junction NAME` | `--elevation`, `--max-depth`, `--init-depth` | Add a junction node |
| `network add-outfall NAME` | `--elevation`, `--type` (FREE/NORMAL/FIXED) | Add an outfall |
| `network add-storage NAME` | `--elevation`, `--max-depth`, `--area` | Add a storage unit (detention pond) |
| `network add-conduit NAME` | `--from-node`, `--to-node`, `--length`, `--roughness`, `--in-offset`, `--out-offset` | Add a conduit (pipe) |
| `network add-subcatchment NAME` | `--rain-gage`, `--outlet`, `--area`, `--imperv`, `--width`, `--slope` | Add a subcatchment |
| `network add-raingage NAME` | `--timeseries`, `--format` (INTENSITY/VOLUME/CUMULATIVE), `--interval`, `--scf` | Add a rain gage |
| `network add-pump NAME` | `--from-node`, `--to-node`, `--pump-curve`, `--status` (ON/OFF), `--startup-depth`, `--shutoff-depth` | Add a pump link |
| `network add-weir NAME` | `--from-node`, `--to-node`, `--type` (TRANSVERSE/SIDEFLOW/V-NOTCH/TRAPEZOIDAL), `--crest-height`, `--discharge-coeff` | Add a weir link |
| `network add-orifice NAME` | `--from-node`, `--to-node`, `--type` (BOTTOM/SIDE), `--offset`, `--discharge-coeff`, `--shape`, `--height`, `--width` | Add an orifice link |
| `network add-inflow NODE` | `--timeseries`, `--constituent`, `--inflow-type`, `--mfactor`, `--sfactor`, `--baseline` | Add external inflow to a node |
| `network remove TYPE NAME` | — | Remove element by type and name (junction\|conduit\|subcatchment\|pump\|weir\|orifice\|inflow) |
| `network list [--type TYPE]` | — | List all or filtered network elements |

**Example — build a minimal network**

```bash
P=tutorial.inp
cli-anything-swmm project new $P --title "Demo"
cli-anything-swmm -p $P network add-raingage RG1 --timeseries TS_RAIN --format INTENSITY
cli-anything-swmm -p $P network add-junction J1 --elevation 10.0
cli-anything-swmm -p $P network add-outfall OUT1 --elevation 0.0 --type FREE
cli-anything-swmm -p $P network add-conduit C1 --from-node J1 --to-node OUT1 --length 100 --roughness 0.013
cli-anything-swmm -p $P network add-subcatchment S1 --rain-gage RG1 --outlet J1 --area 1.0 --imperv 50
cli-anything-swmm -p $P network add-pump P1 --from-node SMP --to-node J1 --pump-curve PUMP_CURVE --status ON
cli-anything-swmm -p $P network add-weir W1 --from-node J1 --to-node OUT1 --type TRANSVERSE --crest-height 0.5
cli-anything-swmm -p $P network add-orifice OR1 --from-node POND --to-node J1 --type BOTTOM --offset 0.0
cli-anything-swmm -p $P network add-inflow J1 --timeseries TS_INFLOW
cli-anything-swmm -p $P network list
```

---

### `timeseries` — Timeseries management

| Command | Key options | Description |
|---------|-------------|-------------|
| `timeseries add NAME` | `--data "TIME VALUE ..."` | Add a named timeseries from inline data |
| `timeseries list` | — | List all defined timeseries |
| `timeseries rainfall NAME` | `--type` (SCS/UNIFORM/TRIANGULAR), `--duration`, `--total`, `--peak-ratio`, `--interval`, `--rain-gage` | Generate synthetic rainfall, optionally wire to a rain gage |

**Rainfall types:**
- `SCS` — SCS Type II 24-hour dimensionless distribution
- `UNIFORM` — constant intensity throughout duration
- `TRIANGULAR` — linearly rises to peak then falls

**Example**

```bash
cli-anything-swmm -p model.inp timeseries rainfall RAIN_5YR \
    --type SCS --duration 24 --total 80.0 --rain-gage RG1
```

---

### `options` — Simulation options

| Command | Key options | Description |
|---------|-------------|-------------|
| `options show` | — | Print current `[OPTIONS]` section |
| `options set` | `--start-date`, `--end-date`, `--routing-step`, `--flow-units`, `--routing-model` (KINWAVE/DYNWAVE) | Set one or more simulation options |

**Example**

```bash
cli-anything-swmm -p model.inp options set \
    --start-date "01/01/2024 00:00:00" \
    --end-date "01/02/2024 00:00:00" \
    --flow-units CMS \
    --routing-model DYNWAVE
```

---

### `simulate` — Simulation control

| Command | Key options | Description |
|---------|-------------|-------------|
| `simulate run PATH` | `--rpt-path`, `--output-path` | Run full simulation via `pyswmm.Simulation.execute()` |
| `simulate validate PATH` | — | Validate `.inp` (parse + short run, report continuity errors) |

Output includes elapsed time, `flow_routing_error`, `runoff_error` (%).

**Example**

```bash
cli-anything-swmm simulate run model.inp --rpt-path model.rpt
cli-anything-swmm --json simulate run model.inp | jq .
```

---

### `results` — Simulation results

| Command | Key options | Description |
|---------|-------------|-------------|
| `results summary [--report PATH]` | — | Runoff/flow-routing continuity tables, errors, warnings |
| `results nodes [--name NAME] [--report PATH]` | — | Node depth summary (all or single node) |
| `results links [--name NAME] [--report PATH]` | — | Link flow summary (all or single link) |
| `results subcatchments [--name NAME] [--report PATH]` | — | Subcatchment runoff summary (all or filtered) |

**Example**

```bash
cli-anything-swmm -p model.inp results summary
cli-anything-swmm --json -p model.inp results nodes --name J1 | jq .
cli-anything-swmm --json -p model.inp results subcatchments | jq '.[].subcatchment'
```

---

### `rules` — Control rules management

| Command | Key options | Description |
|---------|-------------|-------------|
| `rules add --name RULE_ID` | `--if CLAUSE` (repeat), `--then ACTION` (repeat), `--else ACTION` (repeat), `--priority N` | Add a new IF/THEN/ELSE control rule to `[CONTROLS]` |
| `rules list` | — | List all rules (id, condition count, action count, has_else, priority) |
| `rules show RULE_ID` | — | Show full definition of a single rule |
| `rules remove --name RULE_ID` | — | Remove a rule by ID |
| `rules revise --name RULE_ID` | `--if CLAUSE` (repeat), `--then ACTION` (repeat), `--else ACTION` (repeat), `--priority N`, `--clear-else`, `--clear-priority` | Update specific fields of an existing rule in-place |

**Rule syntax** — SWMM condition syntax:
- Condition: `<ObjectType> <ObjectID> <Attribute> <op> <value>`
  e.g. `"Node J1 Depth > 4.5"`, `"Pump P1 Status = ON"`, `"Simulation Time > 2.0"`
- Object types: `Node`, `Link`, `Conduit`, `Pump`, `Orifice`, `Weir`, `Outlet`, `Gage`, `Simulation`
- Attributes: `Depth`, `Head`, `Volume`, `Inflow`, `Flow`, `Status`, `Setting`, `Time`, `Date`, etc.

**Example — pump control rule**

```bash
P=model.inp
# Add a rule: turn pump ON when node depth exceeds threshold
cli-anything-swmm -p $P rules add \
    --name PUMP_CTRL \
    --if "Node J1 Depth > 4.5" \
    --if "Simulation Time > 1.0" \
    --then "Pump P1 Status = ON" \
    --else "Pump P1 Status = OFF" \
    --priority 1

# Revise only the threshold
cli-anything-swmm -p $P rules revise --name PUMP_CTRL \
    --if "Node J1 Depth > 6.0" \
    --if "Simulation Time > 1.0"

# JSON mode for agent use
cli-anything-swmm --json -p $P rules list | jq '.[].id'
cli-anything-swmm --json -p $P rules show PUMP_CTRL | jq '.if_clauses'
```

---

### `calibrate` — Parameter calibration

| Command | Key options | Description |
|---------|-------------|-------------|
| `calibrate params add` | `--id`, `--type`, `--field`, `--min`, `--max`, `--nominal`, `--element` | Register a calibration parameter |
| `calibrate params list` | — | List all registered parameters |
| `calibrate observed add` | `--id`, `--type` (node_depth/link_flow), `--element`, `--data "T V ..."` | Add observed time-series for goodness-of-fit |
| `calibrate run` | `--method` (lhs/grid), `--n-samples`, `--seed`, `--metric` (nse/rmse/mae/pbias) | Run calibration and find best parameter set |
| `calibrate apply` | `--inp PATH` | Write the best parameter set back to a `.inp` file |
| `calibrate metrics` | — | Show goodness-of-fit metrics for the last calibration run |
| `calibrate status` | — | Show current session: parameters, observed series, last result |

**Example — calibrate Manning's n**

```bash
P=model.inp
cli-anything-swmm -p $P calibrate params add \
    --id n_c1 --type conduit --field roughness --element C1 --min 0.010 --max 0.020
cli-anything-swmm -p $P calibrate observed add \
    --id obs_j1 --type node_depth --element J1 \
    --data "0 0.0  300 0.5  600 1.2  900 0.8  1200 0.3"
cli-anything-swmm --json -p $P calibrate run --method lhs --n-samples 50 --metric nse | jq .
cli-anything-swmm -p $P calibrate apply --inp best.inp
```

---

### `repl` — Interactive REPL

```bash
cli-anything-swmm              # launch REPL (no subcommand)
cli-anything-swmm repl         # explicit subcommand
cli-anything-swmm -p urban.inp # launch with a project pre-loaded
```

The REPL wraps the full Click CLI in an interactive loop. All subcommands (`project`, `network`, `options`, `timeseries`, `simulate`, `results`, `rules`, `calibrate`) work exactly as in non-interactive mode.

**REPL-only built-in commands:**

| Command | Description |
|---------|-------------|
| `help` | Print all available commands with descriptions |
| `status` | Show project path, section count, undo depth, redo depth |
| `undo` | Revert the last network/options/timeseries/rules mutation |
| `redo` | Re-apply the last undone mutation |
| `quit` / `exit` / `q` | Exit the REPL |

**Prompt format:** `◆ swmm [<filename>*] ❯`
- `<filename>` shows the basename of the active `.inp` file (empty if none loaded)
- `*` suffix appears when the undo stack is non-empty (unsaved edits exist)

**Keyboard shortcuts** (via `prompt_toolkit`):

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate command history |
| `Ctrl+R` | Reverse incremental history search |
| `→` | Accept inline auto-suggestion from history |
| `Ctrl+C` | Cancel current input line |
| `Ctrl+D` | Exit REPL (same as `quit`) |

Command history is persisted between sessions at `~/.cli-anything-swmm/history`.

**Example session:**

```
◆ swmm  ❯ project new --output urban.inp --title "Urban Network" --flow-units CMS
  ✓ Created: urban.inp
◆ swmm [urban.inp ] ❯ network add-junction --name J1 --elevation 10.0
  ✓ Added junction: J1
◆ swmm [urban.inp*] ❯ status
  Project   urban.inp
  Sections  14
  History   1
  Redo      0
◆ swmm [urban.inp*] ❯ undo
  ✓ Undo successful
◆ swmm [urban.inp ] ❯ quit
```

---

## JSON mode

Pass `--json` as a global flag to receive machine-readable output:

```bash
cli-anything-swmm --json -p model.inp network list
```

Returns a JSON object on stdout; human-readable status messages are written to stderr so they do not interfere with piping.

---

## Architecture

```
cli_anything/swmm/
├── __init__.py
├── __main__.py
├── swmm_cli.py          # Click CLI + REPL entry point
├── core/
│   ├── project.py       # INP create/parse/write helpers
│   ├── network.py       # add/remove nodes, links, subcatchments, rain gages,
│   │                    # pumps, weirs, orifices, inflows
│   ├── timeseries.py    # timeseries CRUD + synthetic rainfall generators
│   ├── simulate.py      # run_simulation() / validate_inp() via pyswmm
│   ├── results.py       # parse_report() — .rpt section/table parser
│   ├── session.py       # undo/redo session with cross-platform file-locked JSON saves
│   ├── calibrate.py     # parameter calibration (LHS, grid, NSE/RMSE metrics)
│   └── rules.py         # IF/THEN/ELSE control rule management
├── utils/
│   └── swmm_backend.py  # thin pyswmm import wrapper
├── skills/
│   └── SKILL.md         # this file
└── tests/
    ├── test_core.py     # 190 unit tests (no simulation required)
    └── test_full_e2e.py # 50 E2E tests (requires pyswmm)
```

**Backend:** `pyswmm 2.1.0` wraps the EPA SWMM 5.2.4 engine (`libswmm5.so`).
**Namespace package:** `cli_anything/` has no `__init__.py` (PEP 420); `cli_anything/swmm/` has one.

---

## Supported SWMM element types

| Section | Elements |
|---------|----------|
| `[JUNCTIONS]` | Junction nodes |
| `[OUTFALLS]` | Outfall nodes |
| `[STORAGE]` | Storage units |
| `[CONDUITS]` | Pipe/conduit links |
| `[PUMPS]` | Pump links |
| `[WEIRS]` | Weir links |
| `[ORIFICES]` | Orifice links |
| `[SUBCATCHMENTS]` + `[SUBAREAS]` + `[INFILTRATION]` | Subcatchments |
| `[RAINGAGES]` | Rain gages (formats: INTENSITY, VOLUME, CUMULATIVE) |
| `[TIMESERIES]` | Time-value pairs |
| `[INFLOWS]` | External hydrograph/pollutograph inputs |
| `[OPTIONS]` | Simulation control settings |
| `[CONTROLS]` | Rule-based control logic (IF/THEN/ELSE rules for pumps, orifices, weirs) |

---

## Tests

```bash
cd agent-harness
python -m pytest cli_anything/swmm/tests/ -v --import-mode=importlib
# 240 tests, all passing
```
