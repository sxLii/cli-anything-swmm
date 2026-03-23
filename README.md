# cli-anything-swmm

A complete Command-Line Interface (CLI) harness for EPA SWMM 5 (Storm Water Management Model), built with the [CLI-Anything](https://github.com/HKUDS/CLI-Anything) methodology.

SWMM 5 is the industry-standard hydrological and hydraulic simulator for urban drainage networks, modeling rainfall-runoff processes, pipe network flow routing, and water quality. This CLI wraps the full SWMM 5 engine via `pyswmm` and exposes every modelling workflow - project creation, network editing, simulation, results parsing, control rules, and parameter calibration - as composable shell commands.

---

## Features

- **Full SWMM 5 workflow** — create, edit, simulate, and post-process from a single CLI
- **Interactive REPL** — styled prompt with persistent history, undo/redo, and live project status
- **JSON output** — every command supports `--json` for machine-readable output (AI-agent friendly)
- **Synthetic rainfall generation** — SCS Type II, uniform, and triangular patterns
- **Control rules** — add, edit, and remove IF/THEN/ELSE pump/weir/orifice control rules
- **Parameter calibration** — sensitivity analysis, Latin Hypercube Sampling, NSE/RMSE/MAE/PBias metrics
- **Session management** — undo/redo with file-locked persistent state (up to 50 history snapshots)

---

## Requirements

- Python ≥ 3.10
- `pyswmm >= 2.0.0` (wraps the compiled SWMM 5 engine `libswmm5.so`)
- `swmm-toolkit >= 0.15.0` (binary `.out` file parsing)

---

## Installation

```bash
cd /path/to/cli-anything-swmm
pip install -e .
```

Verify:

```bash
cli-anything-swmm --help
```

---

## Quick Start

### Interactive REPL

```bash
cli-anything-swmm              # launch REPL
```

![REPL](REPL.png)

The REPL wraps the full CLI in an interactive loop with a styled prompt, persistent command history, and built-in control commands:

| Command | Description |
|---------|-------------|
| `help` | Print all available commands |
| `status` | Show project path, section count, undo/redo depth |
| `undo` | Revert the last network/options/timeseries change |
| `redo` | Re-apply the last undone change |
| `quit` / `exit` / `q` | Exit the REPL |

**Prompt format:** `◆ swmm [<filename>*] ❯` — the `*` suffix appears when there are unsaved changes.

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate command history |
| `Ctrl+R` | Reverse incremental history search |
| `→` | Accept auto-suggestion from history |
| `Ctrl+C` | Cancel current input line |
| `Ctrl+D` | Exit REPL |

Command history is persisted at `~/.cli-anything-swmm/history`.

### End-to-End Example

```bash
# 1. Create a new project
cli-anything-swmm project new --output urban.inp --title "Urban Drainage" --flow-units CMS

# 2. Build the network
cli-anything-swmm -p urban.inp network add-junction --name J1 --elevation 10.0
cli-anything-swmm -p urban.inp network add-junction --name J2 --elevation 9.5
cli-anything-swmm -p urban.inp network add-outfall  --name O1 --elevation 8.0
cli-anything-swmm -p urban.inp network add-conduit  --name C1 --from J1 --to J2 --length 100
cli-anything-swmm -p urban.inp network add-conduit  --name C2 --from J2 --to O1 --length 50

# 3. Add subcatchment with rain gage
cli-anything-swmm -p urban.inp network add-raingage     --name RG1 --timeseries TS1
cli-anything-swmm -p urban.inp network add-subcatchment --name S1  --raingage RG1 --outlet J1 --area 10.0

# 4. Generate synthetic rainfall (SCS Type II, 3-hour, 20 mm peak)
cli-anything-swmm -p urban.inp timeseries rainfall \
  --name TS1 --raingage RG1 \
  --start "2026-03-24 00:00" --duration 3 --peak 20

# 5. Set simulation period
cli-anything-swmm -p urban.inp options set \
  --start-date 03/24/2026 --end-date 04/01/2026 \
  --start-time 00:00:00   --end-time 01:00:00

# 6. Run simulation
cli-anything-swmm -p urban.inp simulate run

# 7. View results
cli-anything-swmm -p urban.inp results summary
cli-anything-swmm -p urban.inp results nodes
cli-anything-swmm -p urban.inp results links
cli-anything-swmm -p urban.inp results subcatchments
```

### JSON Output (for AI agents)

Every command supports `--json` for machine-readable output (status messages go to stderr):

```bash
cli-anything-swmm --json project info urban.inp
cli-anything-swmm --json -p urban.inp results summary
cli-anything-swmm --json -p urban.inp network list
```

---

## Command Reference

### Global Options

| Option | Description |
|--------|-------------|
| `-p / --project PATH` | Active `.inp` file |
| `--json` | Output as JSON (status messages to stderr) |

---

### `project` — Project lifecycle

| Command | Description |
|---------|-------------|
| `project new -o PATH [--title TEXT] [--flow-units UNITS]` | Create a new `.inp` file |
| `project open PATH` | Open and validate an existing `.inp` file |
| `project info [PATH]` | Show element counts and simulation options |
| `project save [PATH]` | Save the current project |
| `project validate [PATH]` | Validate with pyswmm |

Flow unit choices: `CMS`, `LPS`, `CFS`, `GPM`, `MGD`, `IMGD`, `AFD`

---

### `network` — Network element management

| Command | Key Options | Description |
|---------|-------------|-------------|
| `network add-junction` | `--name --elevation [--max-depth --init-depth --sur-depth --aponded]` | Add junction node |
| `network add-conduit` | `--name --from --to --length [--roughness --diameter --shape --in-offset --out-offset]` | Add conduit link |
| `network add-subcatchment` | `--name --raingage --outlet --area [--pct-imperv --width --slope]` | Add subcatchment |
| `network add-outfall` | `--name --elevation [--type FREE\|NORMAL\|FIXED]` | Add outfall node |
| `network add-storage` | `--name --elevation [--max-depth --area]` | Add storage unit (detention pond) |
| `network add-raingage` | `--name [--timeseries --interval --scf]` | Add rain gage |
| `network add-pump` | `--name --from --to [--pump-curve --status --startup-depth --shutoff-depth]` | Add pump link |
| `network add-weir` | `--name --from --to [--type --crest-height --cd --gated --surcharge]` | Add weir link |
| `network add-orifice` | `--name --from --to [--type --offset --cd --gated --close-time]` | Add orifice link |
| `network add-inflow` | `--node --timeseries [--constituent --type --mfactor --baseline]` | Add external inflow to a node |
| `network list [--type all\|nodes\|links\|...]` | — | List network elements |
| `network remove --type TYPE --name NAME` | — | Remove element (`junction\|conduit\|subcatchment\|pump\|weir\|orifice`) |

---

### `options` — Simulation parameters

| Command | Description |
|---------|-------------|
| `options show` | Display the current `[OPTIONS]` section |
| `options set [flags...]` | Update one or more options |

Key `options set` flags:

| Flag | Description |
|------|-------------|
| `--start-date / --end-date DATE` | Simulation date range (`MM/DD/YYYY` or `YYYY-MM-DD`) |
| `--start-time / --end-time TIME` | Simulation time range (`HH:MM:SS`) |
| `--routing DYNWAVE\|KINWAVE\|STEADYSTATE` | Flow routing algorithm |
| `--flow-units UNITS` | Flow measurement units |
| `--report-step TIME` | Report output interval (`HH:MM:SS`) |
| `--routing-step TIME` | Routing timestep |

---

### `timeseries` — Rainfall and flow data

| Command | Key Options | Description |
|---------|-------------|-------------|
| `timeseries add` | `--name --data "DATE TIME VALUE ..."` | Add raw timeseries data |
| `timeseries rainfall` | `--name --raingage --start --duration --peak [--pattern SCS\|UNIFORM\|TRIANGULAR]` | Generate synthetic rainfall |
| `timeseries list` | — | List all timeseries in the project |

Rainfall patterns:
- **SCS** — SCS Type II 24-hour dimensionless distribution (default)
- **UNIFORM** — Constant intensity throughout duration
- **TRIANGULAR** — Linearly rises to peak then falls

---

### `simulate` — Simulation execution

| Command | Description |
|---------|-------------|
| `simulate run [--inp PATH] [--report PATH] [--output PATH]` | Run simulation via pyswmm |
| `simulate validate [PATH]` | Validate `.inp` file (parse + check continuity) |

---

### `results` — Post-processing

| Command | Description |
|---------|-------------|
| `results summary [--report PATH]` | Runoff/routing continuity, errors, warnings |
| `results nodes [--name NAME] [--report PATH]` | Node depth summary table |
| `results links [--name NAME] [--report PATH]` | Link flow summary table |
| `results subcatchments [--name NAME] [--report PATH]` | Subcatchment runoff summary |

---

### `rules` — Control rules (IF/THEN/ELSE)

| Command | Key Options | Description |
|---------|-------------|-------------|
| `rules add` | `--name --if CLAUSE [--if...] --then ACTION [--then...] [--else...] [--priority N]` | Add a control rule |
| `rules list` | — | List all rules |
| `rules show RULE_ID` | — | Show a single rule definition |
| `rules remove` | `--name RULE_ID` | Delete a rule |
| `rules revise` | `--name RULE_ID [--if...] [--then...] [--else...] [--priority N]` | Modify an existing rule |

---

### `calibrate` — Parameter calibration

```bash
# 1. Register calibration parameters
cli-anything-swmm -p urban.inp calibrate params add \
  --id p1 --type subcatchment --field %IMPERV --min 10 --max 90

# 2. Provide observed data
cli-anything-swmm -p urban.inp calibrate observed add \
  --id obs1 --type node --element J2 --data "0 0.0  3600 0.5  7200 0.3"

# 3. Run calibration (Latin Hypercube Sampling, 100 samples, NSE metric)
cli-anything-swmm -p urban.inp calibrate run \
  --method lhs --n-samples 100 --metric nse

# 4. Apply best parameters
cli-anything-swmm -p urban.inp calibrate apply

# 5. View metrics
cli-anything-swmm -p urban.inp calibrate metrics
```

| Command | Description |
|---------|-------------|
| `calibrate params add` | Register a calibration parameter with bounds |
| `calibrate params list` | List registered parameters |
| `calibrate observed add` | Add observed time series for comparison |
| `calibrate observed list` | List observed data series |
| `calibrate sensitivity` | One-at-a-time sensitivity analysis |
| `calibrate run` | Run sampling-based calibration (`lhs` or `grid`) |
| `calibrate apply` | Write best parameters back to `.inp` |
| `calibrate metrics` | Show goodness-of-fit metrics (NSE, RMSE, MAE, PBias) |

Supported calibration parameter types and fields:

| Type | Fields |
|------|--------|
| `subcatchment` | `%IMPERV`, `AREA`, `WIDTH`, `%SLOPE` |
| `subarea` | `N-IMPERV`, `N-PERV`, `S-IMPERV`, `S-PERV` |
| `conduit` | `ROUGHNESS`, `LENGTH` |
| `infiltration` | `MAXRATE`, `MINRATE`, `DECAY`, `DRYTIME` |
| `junction` | `MAXDEPTH` |

---

## File Format

SWMM uses text-based `.inp` files with named section headers:

```
[TITLE]        [OPTIONS]       [RAINGAGES]     [SUBCATCHMENTS]
[SUBAREAS]     [INFILTRATION]  [JUNCTIONS]     [OUTFALLS]
[CONDUITS]     [XSECTIONS]     [TIMESERIES]    [REPORT]
[STORAGE]      [PUMPS]         [ORIFICES]      [WEIRS]
[CONTROLS]     [INFLOWS]       [CURVES]        [PATTERNS]
...
```

Output files generated by simulation:
- `.rpt` — Human-readable report with summary tables (parsed by `results` commands)
- `.out` — Binary time-series results (queryable via `swmm-toolkit`)

---

## Architecture

```
cli_anything/swmm/
├── swmm_cli.py          # Click CLI entry point + REPL dispatcher
├── __init__.py          # Package init (version = 1.1.0)
├── __main__.py          # python -m cli_anything.swmm runner
├── core/
│   ├── project.py       # INP file create / parse / write / info
│   ├── network.py       # Add / remove nodes, links, subcatchments
│   ├── options.py       # Simulation options management
│   ├── timeseries.py    # Rainfall timeseries generation
│   ├── simulate.py      # pyswmm simulation runner
│   ├── results.py       # .rpt file parser
│   ├── session.py       # Stateful session + undo/redo (fcntl-locked JSON)
│   ├── rules.py         # IF/THEN/ELSE control rules
│   └── calibrate.py     # Parameter calibration (LHS, grid, NSE/RMSE)
└── utils/
    ├── swmm_backend.py  # pyswmm import wrapper
    └── repl_skin.py     # Styled terminal output (cli-anything standard)
```


---

## Running Tests

```bash
# Unit tests (no simulation required)
pytest cli_anything/swmm/tests/test_core.py -v --tb=short

# End-to-end tests (requires pyswmm and a working SWMM 5 engine)
pytest cli_anything/swmm/tests/test_full_e2e.py -v --tb=short

# All tests
pytest cli_anything/swmm/tests/ -v --tb=short

# Force installed CLI binary (instead of module fallback)
CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/swmm/tests/ -v -s
```

---

## License

The SWMM 5 engine is public domain software developed by the U.S. EPA. The Python CLI harness in this repository is released under the same public domain terms.
