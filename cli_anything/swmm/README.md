# cli-anything-swmm

A complete CLI harness for EPA SWMM 5 (Storm Water Management Model), built with the cli-anything methodology.

## Software Dependency

**Backend:** `pyswmm` (Python bindings for the EPA SWMM 5 engine)

```bash
pip install pyswmm>=2.0.0
pip install swmm-toolkit>=0.15.0
```

pyswmm wraps the compiled SWMM 5 shared library (`libswmm5.so`) and provides the full simulation engine.
The CLI is useless without it.

## Installation

```bash
cd /path/to/agent-harness
pip install -e .
```

## Verify Installation

```bash
cli-anything-swmm --help
which cli-anything-swmm
```

## Quick Start

### Interactive REPL (default)

```bash
cli-anything-swmm              # launch REPL
cli-anything-swmm -p urban.inp # launch REPL with a project pre-loaded
```

The REPL wraps the full Click CLI in an interactive loop with a styled prompt, persistent command history, and a short set of built-in control commands:

| Command | Description |
|---------|-------------|
| `help` | Print all available commands |
| `status` | Show project path, section count, undo/redo depth |
| `undo` | Revert the last network/options/timeseries change |
| `redo` | Re-apply the last undone change |
| `quit` / `exit` / `q` | Exit the REPL |

Every other input is forwarded to the Click CLI exactly as typed:

```
◆ swmm [urban.inp*] ❯ network add-junction --name J3 --elevation 8.5
◆ swmm [urban.inp*] ❯ undo
  ✓ Undo successful
◆ swmm [urban.inp*] ❯ simulate run
◆ swmm [urban.inp ] ❯ results summary
```

**Prompt format:** `◆ swmm [<filename>*] ❯`  — the `*` suffix appears whenever there are unsaved changes in the undo stack.

**Keyboard shortcuts** (via `prompt_toolkit`):

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate command history |
| `Ctrl+R` | Reverse incremental history search |
| `→` | Accept auto-suggestion from history |
| `Tab` | (if completions registered) complete command |
| `Ctrl+C` | Cancel current input line |
| `Ctrl+D` | Exit REPL (same as `quit`) |

Command history is persisted between sessions at `~/.cli-anything-swmm/history`.

### Create and Run a Project

```bash
# Create project
cli-anything-swmm project new --output my_project.inp --title "Urban Drainage" --flow-units CMS

# Add network elements
cli-anything-swmm --project my_project.inp network add-junction --name J1 --elevation 10.0
cli-anything-swmm --project my_project.inp network add-junction --name J2 --elevation 9.5
cli-anything-swmm --project my_project.inp network add-outfall --name O1 --elevation 8.0
cli-anything-swmm --project my_project.inp network add-conduit --name C1 --from J1 --to J2 --length 100
cli-anything-swmm --project my_project.inp network add-conduit --name C2 --from J2 --to O1 --length 50

# Add subcatchment and rainfall
cli-anything-swmm --project my_project.inp network add-raingage --name RG1 --timeseries TS1
cli-anything-swmm --project my_project.inp network add-subcatchment --name S1 --raingage RG1 --outlet J1 --area 10.0

# Generate synthetic rainfall
cli-anything-swmm --project my_project.inp timeseries rainfall \
  --name TS1 --raingage RG1 \
  --start "2023-01-01 00:00" --duration 3 --peak 20

# Set simulation dates
cli-anything-swmm --project my_project.inp options set \
  --start-date 01/01/2023 --end-date 01/01/2023 \
  --start-time 00:00:00 --end-time 06:00:00

# Run simulation
cli-anything-swmm --project my_project.inp simulate run

# View results
cli-anything-swmm --project my_project.inp results summary
cli-anything-swmm --project my_project.inp results nodes
cli-anything-swmm --project my_project.inp results links
```

### JSON Output (for AI agents)

Every command supports `--json` for machine-readable output:

```bash
cli-anything-swmm --json project info my_project.inp
cli-anything-swmm --json --project my_project.inp results summary
cli-anything-swmm --json --project my_project.inp network list
```

## Command Reference

### `project`
| Command | Description |
|---------|-------------|
| `project new -o PATH` | Create a new .inp file |
| `project open PATH` | Open an existing .inp file |
| `project info [PATH]` | Show element counts and options |
| `project save [PATH]` | Save current project |
| `project validate [PATH]` | Validate with pyswmm |

### `network`
| Command | Description |
|---------|-------------|
| `network add-junction` | Add junction node |
| `network add-conduit` | Add conduit link |
| `network add-subcatchment` | Add subcatchment |
| `network add-outfall` | Add outfall node |
| `network add-storage` | Add storage unit (detention pond) |
| `network add-raingage` | Add rain gage |
| `network add-pump` | Add pump link |
| `network add-weir` | Add weir link |
| `network add-orifice` | Add orifice link |
| `network add-inflow` | Add external inflow to a node |
| `network list [--type all\|nodes\|links\|...]` | List elements |
| `network remove --type TYPE --name NAME` | Remove element (junction\|conduit\|subcatchment\|pump\|weir\|orifice) |

### `options`
| Command | Description |
|---------|-------------|
| `options show` | Display current options |
| `options set [--start-date ...] [--end-date ...]` | Update options |

### `timeseries`
| Command | Description |
|---------|-------------|
| `timeseries add --name NAME --data "..."` | Add raw timeseries |
| `timeseries rainfall --name NAME --raingage ...` | Synthetic rainfall |
| `timeseries list` | List all timeseries |

### `simulate`
| Command | Description |
|---------|-------------|
| `simulate run [--inp PATH]` | Run simulation |
| `simulate validate [PATH]` | Validate .inp file |

### `results`
| Command | Description |
|---------|-------------|
| `results summary [--report PATH]` | Full simulation summary |
| `results nodes [--name NAME]` | Node depth results |
| `results links [--name NAME]` | Link flow results |
| `results subcatchments [--name NAME]` | Subcatchment runoff summary |

## Running Tests

```bash
cd /path/to/agent-harness
pytest cli_anything/swmm/tests/ -v --tb=short

# Force installed command (not module fallback):
CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/swmm/tests/ -v -s
```

## File Format

SWMM uses text-based `.inp` files with section headers like `[JUNCTIONS]`, `[CONDUITS]`, etc.
This CLI reads and writes `.inp` files directly with Python text processing, then invokes
`pyswmm.Simulation` for actual simulation execution.

Output files:
- `.rpt` — Human-readable report with summary tables
- `.out` — Binary time-series results (queryable via swmm-toolkit)

## Architecture

```
swmm_cli.py          # Click CLI entry point + REPL
core/
  project.py         # INP file create/parse/write/info
  network.py         # Add/remove nodes, links, subcatchments
  options.py         # Simulation options management
  timeseries.py      # Rainfall timeseries
  simulate.py        # pyswmm simulation runner
  results.py         # .rpt file parser
  session.py         # Stateful session + undo/redo
utils/
  swmm_backend.py    # pyswmm wrapper (the real software backend)
  repl_skin.py       # Unified REPL skin (cli-anything standard)
```
