"""cli-anything-swmm: EPA SWMM 5 CLI harness."""

from __future__ import annotations

import json as _json_mod
import os
import sys
from typing import Any

import click

from cli_anything.swmm.core.project import (
    create_project, open_project, save_project, project_info, parse_inp, write_inp,
)
from cli_anything.swmm.core.network import (
    add_junction, remove_junction, add_conduit, remove_conduit,
    add_subcatchment, add_outfall, add_storage, add_raingage, list_network,
    add_pump, remove_pump, add_weir, remove_weir,
    add_orifice, remove_orifice, add_inflow, remove_inflow,
)
from cli_anything.swmm.core.options import get_options, set_options, set_simulation_dates
from cli_anything.swmm.core.timeseries import add_timeseries, add_rainfall_event, list_timeseries
from cli_anything.swmm.core.simulate import run_simulation, validate_inp
from cli_anything.swmm.core.results import (
    parse_report, get_node_results, get_link_results,
    get_runoff_summary, get_flow_routing_summary,
)
from cli_anything.swmm.core.session import Session
from cli_anything.swmm.core.rules import (
    parse_rules, get_rule, list_rules, add_rule, remove_rule, revise_rule,
)
from cli_anything.swmm.core.calibrate import (
    load_session as calib_load_session,
    save_session as calib_save_session,
    load_observed_csv,
    add_observed,
    add_param as calib_add_param,
    compute_metrics,
    run_sensitivity,
    run_calibration,
    apply_best_params,
)
from cli_anything.swmm.utils.repl_skin import ReplSkin

_VERSION = "1.1.0"
_skin = ReplSkin("swmm", version=_VERSION)
_session: Session = Session()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _is_json(ctx_obj):
    return bool((ctx_obj or {}).get("json"))


def _out(data, ctx_obj=None):
    if _is_json(ctx_obj):
        click.echo(_json_mod.dumps(data, indent=2, default=str))
    else:
        _pretty(data)


def _status_symbol(primary: str, fallback: str, stream=None) -> str:
    """Return a symbol that can be encoded on the given stream."""
    target = stream or sys.stderr
    encoding = getattr(target, "encoding", None) or "utf-8"
    try:
        primary.encode(encoding)
        return primary
    except UnicodeEncodeError:
        return fallback


def _pretty(data, indent=0):
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                click.echo(f"{prefix}{k}:")
                _pretty(v, indent + 1)
            else:
                click.echo(f"{prefix}{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _pretty(item, indent)
                click.echo("")
            else:
                click.echo(f"{prefix}- {item}")
    else:
        click.echo(f"{prefix}{data}")


def _ok(msg, ctx_obj=None):
    """Success message: stderr in JSON mode, stdout otherwise."""
    if _is_json(ctx_obj):
        icon = _status_symbol("\u2713", "OK", stream=sys.stderr)
        click.echo(f"  {icon} {msg}", file=sys.stderr)
    else:
        _skin.success(msg)


def _err(msg, ctx_obj=None):
    """Error message: always stderr."""
    _skin.error(msg)


def _info(msg, ctx_obj=None):
    """Info message: stderr in JSON mode, stdout otherwise."""
    if _is_json(ctx_obj):
        icon = _status_symbol("\u25cf", "-", stream=sys.stderr)
        click.echo(f"  {icon} {msg}", file=sys.stderr)
    else:
        _skin.info(msg)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, default=False, help="Output as JSON.")
@click.option("--project", "-p", default=None, metavar="PATH", help="Active .inp file.")
@click.version_option(_VERSION, prog_name="cli-anything-swmm")
@click.pass_context
def main(ctx, use_json, project):
    """cli-anything-swmm: EPA SWMM 5 Storm Water Management CLI.

    Run without a subcommand to enter the interactive REPL.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["project"] = project

    if project and os.path.exists(project):
        _session.inp_path = project
        try:
            _session.load()
        except Exception:
            pass

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

@main.command()
@click.pass_context
def repl(ctx):
    """Enter the interactive REPL mode."""
    ctx.ensure_object(dict)
    _skin.print_banner()
    pt_session = _skin.create_prompt_session()

    help_map = {
        "project new":              "Create a new SWMM project",
        "project open PATH":        "Open an existing .inp file",
        "project info":             "Show element counts",
        "project save":             "Save current project",
        "project validate":         "Validate with pyswmm",
        "network add-junction":     "Add a junction node",
        "network add-conduit":      "Add a conduit link",
        "network add-subcatchment": "Add a subcatchment",
        "network add-outfall":      "Add an outfall node",
        "network add-raingage":     "Add a rain gage",
        "network add-pump":         "Add a pump link",
        "network add-weir":         "Add a weir link",
        "network add-orifice":      "Add an orifice link",
        "network add-inflow":       "Add external inflow to a node",
        "network list":             "List network elements",
        "network remove":           "Remove a network element",
        "options set":              "Set simulation options",
        "options show":             "Show current options",
        "timeseries add":           "Add a timeseries",
        "timeseries rainfall":      "Generate synthetic rainfall",
        "timeseries list":          "List all timeseries",
        "simulate run":             "Run simulation",
        "simulate validate":        "Validate .inp file",
        "results summary":          "Show simulation summary",
        "results nodes":            "Show node results",
        "results links":            "Show link results",
        "results subcatchments":    "Show subcatchment runoff summary",
        "calibrate observed-add":   "Add observed CSV data",
        "calibrate observed-list":  "List observed datasets",
        "calibrate params-add":     "Add a calibration parameter",
        "calibrate params-list":    "List calibration parameters",
        "calibrate sensitivity":    "Run OAT sensitivity analysis",
        "calibrate run":            "Run multi-parameter calibration",
        "calibrate apply":          "Apply best parameters to .inp",
        "calibrate metrics":        "Compute NSE/RMSE/MAE/PBias",
        "calibrate status":         "Show calibration session status",
        "rules add":                "Add a control rule",
        "rules list":               "List all control rules",
        "rules show RULE_ID":       "Show a rule's full definition",
        "rules remove":             "Remove a control rule",
        "rules revise":             "Revise an existing control rule",
        "undo":                     "Undo last change",
        "redo":                     "Redo last undone change",
        "status":                   "Show session status",
        "help":                     "Show this help",
        "quit / exit":              "Exit the REPL",
    }

    while True:
        proj_name = os.path.basename(_session.inp_path) if _session.inp_path else ""
        modified = _session.history_depth > 0
        try:
            line = _skin.get_input(pt_session, project_name=proj_name, modified=modified)
        except (EOFError, KeyboardInterrupt):
            _skin.print_goodbye()
            break

        if not line:
            continue
        cmd = line.strip().lower()

        if cmd in ("quit", "exit", "q"):
            _skin.print_goodbye()
            break
        elif cmd == "help":
            _skin.help(help_map)
        elif cmd == "status":
            _skin.status_block({
                "Project": _session.inp_path or "(none)",
                "Sections": str(len(_session.sections)),
                "History": str(_session.history_depth),
                "Redo": str(_session.redo_depth),
            }, title="Session Status")
        elif cmd == "undo":
            if _session.undo():
                _skin.success("Undo successful")
            else:
                _skin.warning("Nothing to undo")
        elif cmd == "redo":
            if _session.redo():
                _skin.success("Redo successful")
            else:
                _skin.warning("Nothing to redo")
        else:
            try:
                import shlex
                args = shlex.split(line)
                from click.testing import CliRunner
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(main, args, catch_exceptions=False)
                if result.output:
                    click.echo(result.output, nl=False)
                if result.exception and not isinstance(result.exception, SystemExit):
                    _skin.error(str(result.exception))
            except SystemExit:
                pass
            except Exception as e:
                _skin.error(f"Error: {e}")


# ---------------------------------------------------------------------------
# project group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def project(ctx):
    """Project management: create, open, save, validate."""


@project.command("new")
@click.option("--output", "-o", required=True, metavar="PATH")
@click.option("--title", default="New SWMM Project")
@click.option("--flow-units", default="CMS",
              type=click.Choice(["CMS","LPS","CFS","GPM","MGD","IMGD","AFD"], case_sensitive=False))
@click.pass_context
def project_new(ctx, output, title, flow_units):
    """Create a new SWMM project .inp file."""
    try:
        result = create_project(output, title, flow_units)
        _session.inp_path = result["path"]
        _session.load()
        _ok(f"Created: {result['path']}", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@project.command("open")
@click.argument("path")
@click.pass_context
def project_open(ctx, path):
    """Open an existing .inp file."""
    try:
        result = open_project(path)
        _session.inp_path = result["path"]
        _session.sections = result["sections"]
        _ok(f"Opened: {result['path']}", ctx.obj)
        _out(result["info"], ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@project.command("info")
@click.argument("path", required=False)
@click.pass_context
def project_info_cmd(ctx, path):
    """Show project information (element counts, options)."""
    target = path or ctx.obj.get("project") or _session.inp_path
    if not target:
        _err("No project specified. Use --project or open a project first.", ctx.obj)
        sys.exit(1)
    try:
        result = project_info(target)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@project.command("save")
@click.argument("path", required=False)
@click.pass_context
def project_save(ctx, path):
    """Save the current project."""
    if not _session.sections:
        _err("No project loaded.", ctx.obj)
        sys.exit(1)
    target = path or _session.inp_path
    if not target:
        _err("No save path specified.", ctx.obj)
        sys.exit(1)
    try:
        result = save_project(_session.sections, target)
        _ok(f"Saved: {result['path']} ({result['size']:,} bytes)", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@project.command("validate")
@click.argument("path", required=False)
@click.pass_context
def project_validate(ctx, path):
    """Validate a .inp file using pyswmm."""
    target = path or ctx.obj.get("project") or _session.inp_path
    if not target:
        _err("No project specified.", ctx.obj)
        sys.exit(1)
    try:
        result = validate_inp(target)
        if result["valid"]:
            _ok("Validation passed", ctx.obj)
        else:
            _err("Validation failed", ctx.obj)
            for e in result["errors"]:
                _err(f"  {e}", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# network group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def network(ctx):
    """Network element management: nodes, links, subcatchments."""


def _require_project(ctx):
    """Ensure a project is loaded; return sections dict."""
    proj_path = ctx.obj.get("project") if ctx.obj else None
    if proj_path and os.path.exists(proj_path) and not _session.sections:
        _session.inp_path = proj_path
        _session.load()
    if not _session.sections:
        _err("No project loaded. Use 'project open PATH' or --project PATH first.")
        sys.exit(1)
    return _session.sections


@network.command("add-junction")
@click.option("--name", required=True)
@click.option("--elevation", required=True, type=float)
@click.option("--max-depth", default=5.0, type=float)
@click.option("--init-depth", default=0.0, type=float)
@click.option("--sur-depth", default=0.0, type=float)
@click.option("--aponded", default=0.0, type=float)
@click.pass_context
def network_add_junction(ctx, name, elevation, max_depth, init_depth, sur_depth, aponded):
    """Add a junction node to the network."""
    sections = _require_project(ctx)
    _session.push()
    result = add_junction(sections, name, elevation, max_depth, init_depth, sur_depth, aponded)
    _session.save()
    _ok(f"Added junction: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-conduit")
@click.option("--name", required=True)
@click.option("--from", "from_node", required=True)
@click.option("--to", "to_node", required=True)
@click.option("--length", required=True, type=float)
@click.option("--roughness", default=0.01, type=float)
@click.option("--diameter", default=1.0, type=float)
@click.option("--shape", default="CIRCULAR",
              type=click.Choice(["CIRCULAR","RECT_CLOSED","TRAPEZOIDAL","TRIANGULAR",
                                 "HORIZ_ELLIPSE","VERT_ELLIPSE","ARCH","FORCE_MAIN"],
                                case_sensitive=False))
@click.option("--in-offset", default=0.0, type=float)
@click.option("--out-offset", default=0.0, type=float)
@click.pass_context
def network_add_conduit(ctx, name, from_node, to_node, length, roughness,
                        diameter, shape, in_offset, out_offset):
    """Add a conduit (pipe) link to the network."""
    sections = _require_project(ctx)
    _session.push()
    result = add_conduit(sections, name, from_node, to_node, length, roughness,
                         in_offset, out_offset, shape=shape, diameter=diameter)
    _session.save()
    _ok(f"Added conduit: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-subcatchment")
@click.option("--name", required=True)
@click.option("--raingage", required=True)
@click.option("--outlet", required=True)
@click.option("--area", required=True, type=float)
@click.option("--pct-imperv", default=50.0, type=float)
@click.option("--width", default=100.0, type=float)
@click.option("--slope", default=0.5, type=float)
@click.pass_context
def network_add_subcatchment(ctx, name, raingage, outlet, area, pct_imperv, width, slope):
    """Add a subcatchment to the network."""
    sections = _require_project(ctx)
    _session.push()
    result = add_subcatchment(sections, name, raingage, outlet, area, pct_imperv, width, slope)
    _session.save()
    _ok(f"Added subcatchment: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-outfall")
@click.option("--name", required=True)
@click.option("--elevation", required=True, type=float)
@click.option("--type", "outfall_type", default="FREE",
              type=click.Choice(["FREE","NORMAL","FIXED","TIDAL","TIMESERIES"],
                                case_sensitive=False))
@click.pass_context
def network_add_outfall(ctx, name, elevation, outfall_type):
    """Add an outfall node."""
    sections = _require_project(ctx)
    _session.push()
    result = add_outfall(sections, name, elevation, outfall_type)
    _session.save()
    _ok(f"Added outfall: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-raingage")
@click.option("--name", required=True)
@click.option("--timeseries", default="")
@click.option("--interval", default="0:05")
@click.option("--scf", default=1.0, type=float)
@click.pass_context
def network_add_raingage(ctx, name, timeseries, interval, scf):
    """Add a rain gage."""
    sections = _require_project(ctx)
    _session.push()
    result = add_raingage(sections, name, timeseries, interval=interval, scf=scf)
    _session.save()
    _ok(f"Added rain gage: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-pump")
@click.option("--name", required=True)
@click.option("--from", "from_node", required=True)
@click.option("--to", "to_node", required=True)
@click.option("--pump-curve", default="*", help="Pump curve name (or '*' for ideal pump).")
@click.option("--status", default="ON",
              type=click.Choice(["ON", "OFF"], case_sensitive=False))
@click.option("--startup-depth", default=0.0, type=float,
              help="Node depth (m) that turns pump ON.")
@click.option("--shutoff-depth", default=0.0, type=float,
              help="Node depth (m) that turns pump OFF.")
@click.pass_context
def network_add_pump(ctx, name, from_node, to_node, pump_curve, status,
                     startup_depth, shutoff_depth):
    """Add a pump link between two nodes."""
    sections = _require_project(ctx)
    _session.push()
    result = add_pump(sections, name, from_node, to_node,
                      pump_curve, status, startup_depth, shutoff_depth)
    _session.save()
    _ok(f"Added pump: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-weir")
@click.option("--name", required=True)
@click.option("--from", "from_node", required=True)
@click.option("--to", "to_node", required=True)
@click.option("--type", "weir_type", default="TRANSVERSE",
              type=click.Choice(["TRANSVERSE", "SIDEFLOW", "V-NOTCH", "TRAPEZOIDAL"],
                                case_sensitive=False))
@click.option("--crest-height", default=0.0, type=float,
              help="Height of weir crest above node invert (m).")
@click.option("--cd", "discharge_coeff", default=3.33, type=float,
              help="Discharge coefficient.")
@click.option("--gated", default="NO",
              type=click.Choice(["YES", "NO"], case_sensitive=False))
@click.option("--surcharge", default="YES",
              type=click.Choice(["YES", "NO"], case_sensitive=False))
@click.pass_context
def network_add_weir(ctx, name, from_node, to_node, weir_type, crest_height,
                     discharge_coeff, gated, surcharge):
    """Add a weir link for overflow/flow control."""
    sections = _require_project(ctx)
    _session.push()
    result = add_weir(sections, name, from_node, to_node,
                      weir_type, crest_height, discharge_coeff,
                      gated, can_surcharge=surcharge)
    _session.save()
    _ok(f"Added weir: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-orifice")
@click.option("--name", required=True)
@click.option("--from", "from_node", required=True)
@click.option("--to", "to_node", required=True)
@click.option("--type", "orifice_type", default="BOTTOM",
              type=click.Choice(["BOTTOM", "SIDE"], case_sensitive=False))
@click.option("--offset", default=0.0, type=float,
              help="Height of orifice centerline above node invert (m).")
@click.option("--cd", "discharge_coeff", default=0.65, type=float,
              help="Discharge coefficient (typically 0.6-0.7).")
@click.option("--gated", default="NO",
              type=click.Choice(["YES", "NO"], case_sensitive=False))
@click.option("--close-time", default=0.0, type=float,
              help="Time to close a gated orifice (hours).")
@click.pass_context
def network_add_orifice(ctx, name, from_node, to_node, orifice_type, offset,
                        discharge_coeff, gated, close_time):
    """Add an orifice link (e.g. storage unit outlet)."""
    sections = _require_project(ctx)
    _session.push()
    result = add_orifice(sections, name, from_node, to_node,
                         orifice_type, offset, discharge_coeff, gated, close_time)
    _session.save()
    _ok(f"Added orifice: {name}", ctx.obj)
    _out(result, ctx.obj)


@network.command("add-inflow")
@click.option("--node", required=True, help="Node receiving the inflow.")
@click.option("--timeseries", required=True, help="Timeseries name providing flow data.")
@click.option("--constituent", default="FLOW",
              help="Constituent name (default: FLOW).")
@click.option("--type", "inflow_type", default="FLOW",
              type=click.Choice(["FLOW", "CONCEN", "MASS"], case_sensitive=False))
@click.option("--mfactor", default=1.0, type=float,
              help="Multiplier applied to timeseries values.")
@click.option("--baseline", default=0.0, type=float,
              help="Constant baseline flow added to timeseries.")
@click.pass_context
def network_add_inflow(ctx, node, timeseries, constituent, inflow_type, mfactor, baseline):
    """Add an external inflow (direct hydrograph) to a node."""
    sections = _require_project(ctx)
    _session.push()
    result = add_inflow(sections, node, timeseries, constituent, inflow_type, mfactor, 1.0, baseline)
    _session.save()
    _ok(f"Added inflow to node: {node}", ctx.obj)
    _out(result, ctx.obj)


@network.command("list")
@click.option("--type", "element_type",
              type=click.Choice(["nodes","links","subcatchments","raingages","all"],
                                case_sensitive=False),
              default="all")
@click.pass_context
def network_list(ctx, element_type):
    """List network elements."""
    sections = _require_project(ctx)
    net = list_network(sections)

    if element_type == "all":
        _out(net, ctx.obj)
        if not _is_json(ctx.obj):
            for category, items in net.items():
                _skin.section(category.title())
                if items:
                    headers = list(items[0].keys())
                    rows = [[str(item.get(h, "")) for h in headers] for item in items]
                    _skin.table(headers, rows)
                else:
                    _skin.hint("  (none)")
    else:
        items = net.get(element_type, [])
        _out(items, ctx.obj)
        if not _is_json(ctx.obj):
            if items:
                headers = list(items[0].keys())
                rows = [[str(item.get(h, "")) for h in headers] for item in items]
                _skin.table(headers, rows)
            else:
                _skin.hint(f"No {element_type} found.")


@network.command("remove")
@click.option("--type", "element_type", required=True,
              type=click.Choice(["junction","conduit","subcatchment","pump","weir","orifice"],
                                case_sensitive=False))
@click.option("--name", required=True)
@click.pass_context
def network_remove(ctx, element_type, name):
    """Remove a network element by type and name."""
    sections = _require_project(ctx)
    _session.push()
    removed = False
    if element_type == "junction":
        removed = remove_junction(sections, name)
    elif element_type == "conduit":
        removed = remove_conduit(sections, name)
    elif element_type == "subcatchment":
        from cli_anything.swmm.core.network import _remove_from_section
        removed = _remove_from_section(sections.get("SUBCATCHMENTS", []), name)
        _remove_from_section(sections.get("SUBAREAS", []), name)
        _remove_from_section(sections.get("INFILTRATION", []), name)
    elif element_type == "pump":
        removed = remove_pump(sections, name)
    elif element_type == "weir":
        removed = remove_weir(sections, name)
    elif element_type == "orifice":
        removed = remove_orifice(sections, name)

    if removed:
        _session.save()
        _ok(f"Removed {element_type}: {name}", ctx.obj)
        _out({"removed": True, "type": element_type, "name": name}, ctx.obj)
    else:
        _session.undo()
        _err(f"{element_type} '{name}' not found.", ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# options group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def options(ctx):
    """Simulation options: dates, routing method, flow units."""


@options.command("show")
@click.pass_context
def options_show(ctx):
    """Show current simulation options."""
    sections = _require_project(ctx)
    opts = get_options(sections)
    _out(opts, ctx.obj)
    if not _is_json(ctx.obj):
        _skin.status_block(opts, title="Simulation Options")


@options.command("set")
@click.option("--start-date", default=None)
@click.option("--end-date", default=None)
@click.option("--start-time", default=None)
@click.option("--end-time", default=None)
@click.option("--routing", type=click.Choice(["DYNWAVE","KINWAVE","STEADYSTATE"],
                                              case_sensitive=False), default=None)
@click.option("--flow-units", type=click.Choice(["CMS","LPS","CFS","GPM","MGD","IMGD","AFD"],
                                                case_sensitive=False), default=None)
@click.option("--report-step", default=None)
@click.option("--routing-step", default=None)
@click.pass_context
def options_set(ctx, start_date, end_date, start_time, end_time,
                routing, flow_units, report_step, routing_step):
    """Set simulation options."""
    sections = _require_project(ctx)
    _session.push()
    kwargs = {}
    if start_date:   kwargs["START_DATE"] = start_date
    if end_date:     kwargs["END_DATE"] = end_date
    if start_time:   kwargs["START_TIME"] = start_time
    if end_time:     kwargs["END_TIME"] = end_time
    if start_date:   kwargs["REPORT_START_DATE"] = start_date
    if start_time:   kwargs["REPORT_START_TIME"] = start_time
    if routing:      kwargs["FLOW_ROUTING"] = routing
    if flow_units:   kwargs["FLOW_UNITS"] = flow_units
    if report_step:  kwargs["REPORT_STEP"] = report_step
    if routing_step: kwargs["ROUTING_STEP"] = routing_step
    try:
        updated = set_options(sections, **kwargs)
        _session.save()
        _ok("Options updated", ctx.obj)
        _out(updated, ctx.obj)
    except ValueError as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# timeseries group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def timeseries(ctx):
    """Timeseries management: rainfall data, synthetic events."""


@timeseries.command("add")
@click.option("--name", required=True)
@click.option("--data", required=True,
              help='Data as "date,time,value;..." e.g. "01/01/2023,0:00,0.0;..."')
@click.pass_context
def timeseries_add(ctx, name, data):
    """Add a timeseries from inline data."""
    sections = _require_project(ctx)
    _session.push()
    try:
        entries = []
        for point in data.split(";"):
            point = point.strip()
            if not point:
                continue
            parts = point.split(",", 2)
            if len(parts) != 3:
                raise ValueError(f"Invalid data point: {point!r}. Expected 'date,time,value'")
            entries.append((parts[0].strip(), parts[1].strip(), float(parts[2].strip())))
        result = add_timeseries(sections, name, entries)
        _session.save()
        _ok(f"Added timeseries '{name}' with {result['points']} points", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)


@timeseries.command("rainfall")
@click.option("--name", required=True)
@click.option("--raingage", required=True)
@click.option("--start", required=True, metavar="DATETIME")
@click.option("--duration", required=True, type=float)
@click.option("--peak", required=True, type=float)
@click.option("--pattern", type=click.Choice(["SCS", "UNIFORM", "TRIANGULAR", "CHICAGO"],
                                             case_sensitive=False), default="SCS")
@click.option("--timestep-minutes", type=int, default=5, show_default=True)
@click.option("--chicago-a", type=float, default=None)
@click.option("--chicago-c", type=float, default=None)
@click.option("--chicago-n", type=float, default=None)
@click.option("--chicago-b", type=float, default=None)
@click.option("--chicago-r", type=float, default=None)
@click.pass_context
def timeseries_rainfall(
    ctx,
    name,
    raingage,
    start,
    duration,
    peak,
    pattern,
    timestep_minutes,
    chicago_a,
    chicago_c,
    chicago_n,
    chicago_b,
    chicago_r,
):
    """Generate synthetic rainfall timeseries."""
    sections = _require_project(ctx)
    _session.push()
    try:
        if pattern.upper() == "CHICAGO" and chicago_r is not None and not (0 < chicago_r < 1):
            raise ValueError("--chicago-r must satisfy 0 < r < 1")
        result = add_rainfall_event(sections, raingage, start, duration, peak,
                                    pattern=pattern, ts_name=name,
                                    timestep_minutes=timestep_minutes,
                                    chicago_a=chicago_a,
                                    chicago_c=chicago_c,
                                    chicago_n=chicago_n,
                                    chicago_b=chicago_b,
                                    chicago_r=chicago_r)
        _session.save()
        _ok(f"Generated rainfall '{name}': {result['points']} points, "
            f"{result['total_depth_mm']} mm total", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)


@timeseries.command("list")
@click.pass_context
def timeseries_list(ctx):
    """List all timeseries."""
    sections = _require_project(ctx)
    ts_list = list_timeseries(sections)
    _out(ts_list, ctx.obj)
    if not _is_json(ctx.obj):
        if ts_list:
            _skin.table(["Name", "Points"], [[t["name"], str(t["points"])] for t in ts_list])
        else:
            _skin.hint("No timeseries defined.")


# ---------------------------------------------------------------------------
# simulate group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def simulate(ctx):
    """Simulation control: run, validate."""


@simulate.command("run")
@click.option("--inp", default=None, metavar="PATH")
@click.option("--report", default=None, metavar="PATH")
@click.option("--output", default=None, metavar="PATH")
@click.pass_context
def simulate_run(ctx, inp, report, output):
    """Run a SWMM simulation using pyswmm."""
    target = inp or ctx.obj.get("project") or _session.inp_path
    if not target:
        _err("No .inp file specified.", ctx.obj)
        sys.exit(1)
    _info(f"Running simulation: {target}", ctx.obj)
    try:
        result = run_simulation(target, rpt_path=report, output_path=output)
        if result["status"] == "success":
            _ok(f"Simulation complete ({result['elapsed_time']:.1f}s)", ctx.obj)
        else:
            _err(f"Simulation failed (code {result['error_code']})", ctx.obj)
            for e in result["errors"]:
                _err(f"  {e}", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@simulate.command("validate")
@click.argument("path", required=False)
@click.pass_context
def simulate_validate(ctx, path):
    """Validate a .inp file."""
    target = path or ctx.obj.get("project") or _session.inp_path
    if not target:
        _err("No .inp file specified.", ctx.obj)
        sys.exit(1)
    try:
        result = validate_inp(target)
        if result["valid"]:
            _ok("Validation passed", ctx.obj)
        else:
            _err("Validation failed", ctx.obj)
            for e in result["errors"]:
                _err(f"  {e}", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# results group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def results(ctx):
    """Simulation results: summary, node/link time-series."""


def _get_rpt(ctx, rpt):
    if rpt:
        return rpt
    proj = ctx.obj.get("project") or _session.inp_path
    if proj:
        candidate = os.path.splitext(proj)[0] + ".rpt"
        if os.path.exists(candidate):
            return candidate
    _err("No .rpt file found. Run simulation first or specify --report PATH.", ctx.obj)
    sys.exit(1)


@results.command("summary")
@click.option("--report", default=None, metavar="PATH")
@click.pass_context
def results_summary(ctx, report):
    """Show simulation summary from the .rpt file."""
    rpt = _get_rpt(ctx, report)
    try:
        parsed = parse_report(rpt)
        summary = {
            "errors": parsed["errors"],
            "warnings": parsed["warnings"],
            "runoff_continuity": parsed["runoff_summary"],
            "flow_routing_continuity": parsed["flow_routing_continuity"],
            "subcatchment_count": len(parsed["subcatch_runoff_summary"]),
            "node_count": len(parsed["node_depth_summary"]),
            "link_count": len(parsed["link_flow_summary"]),
        }
        _out(summary, ctx.obj)
        if not _is_json(ctx.obj):
            _skin.status_block({
                "Errors":        str(len(parsed["errors"])),
                "Warnings":      str(len(parsed["warnings"])),
                "Nodes":         str(len(parsed["node_depth_summary"])),
                "Links":         str(len(parsed["link_flow_summary"])),
                "Subcatchments": str(len(parsed["subcatch_runoff_summary"])),
            }, title="Simulation Summary")
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@results.command("nodes")
@click.option("--report", default=None, metavar="PATH")
@click.option("--name", default=None)
@click.pass_context
def results_nodes(ctx, report, name):
    """Show node depth results."""
    rpt = _get_rpt(ctx, report)
    try:
        if name:
            result = get_node_results(rpt, name)
        else:
            parsed = parse_report(rpt)
            result = parsed["node_depth_summary"]
        _out(result, ctx.obj)
        if not _is_json(ctx.obj):
            if isinstance(result, dict) and "node" not in result:
                nodes = [{"name": k, **v} for k, v in result.items()]
                if nodes:
                    headers = list(nodes[0].keys())
                    rows = [[str(n.get(h, "")) for h in headers] for n in nodes]
                    _skin.table(headers, rows)
            else:
                _skin.status_block({k: str(v) for k, v in result.items()})
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@results.command("links")
@click.option("--report", default=None, metavar="PATH")
@click.option("--name", default=None)
@click.pass_context
def results_links(ctx, report, name):
    """Show link flow results."""
    rpt = _get_rpt(ctx, report)
    try:
        if name:
            result = get_link_results(rpt, name)
        else:
            parsed = parse_report(rpt)
            result = parsed["link_flow_summary"]
        _out(result, ctx.obj)
        if not _is_json(ctx.obj):
            if isinstance(result, dict) and "link" not in result:
                links = [{"name": k, **v} for k, v in result.items()]
                if links:
                    headers = list(links[0].keys())
                    rows = [[str(lk.get(h, "")) for h in headers] for lk in links]
                    _skin.table(headers, rows)
            else:
                _skin.status_block({k: str(v) for k, v in result.items()})
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@results.command("subcatchments")
@click.option("--report", default=None, metavar="PATH")
@click.option("--name", default=None, help="Filter to a single subcatchment by name.")
@click.pass_context
def results_subcatchments(ctx, report, name):
    """Show subcatchment runoff summary from the .rpt file."""
    rpt = _get_rpt(ctx, report)
    try:
        parsed = parse_report(rpt)
        subcatches = parsed["subcatch_runoff_summary"]
        if name:
            subcatches = [s for s in subcatches if s.get("subcatchment") == name]
            if not subcatches:
                _err(f"Subcatchment '{name}' not found in report.", ctx.obj)
                sys.exit(1)
        _out(subcatches, ctx.obj)
        if not _is_json(ctx.obj):
            if subcatches:
                headers = list(subcatches[0].keys())
                rows = [[str(s.get(h, "")) for h in headers] for s in subcatches]
                _skin.table(headers, rows)
            else:
                _skin.hint("No subcatchment runoff data in report.")
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# calibrate group
# ---------------------------------------------------------------------------

@main.group()
@click.pass_context
def calibrate(ctx):
    """Model calibration: sensitivity analysis, multi-run optimization, metrics."""


def _calib_session(ctx) -> tuple[str, dict]:
    """Return (inp_path, session) for the active project."""
    target = ctx.obj.get("project") if ctx.obj else None
    if not target:
        target = _session.inp_path
    if not target:
        _err("No project loaded. Use --project PATH or open a project first.")
        import sys as _sys; _sys.exit(1)
    session = calib_load_session(target)
    return target, session


@calibrate.command("observed-add")
@click.option("--file", "csv_file", required=True, metavar="CSV",
              help="CSV file with 'datetime' and 'value' columns.")
@click.option("--element", required=True, metavar="SPEC",
              help="Element variable spec, e.g. 'node:J1:depth' or 'link:C1:flow'.")
@click.option("--id", "obs_id", default=None, metavar="ID",
              help="Unique ID for this observation set (default: element spec).")
@click.pass_context
def calibrate_observed_add(ctx, csv_file, element, obs_id):
    """Add observed time-series data from a CSV file.

    The CSV must have 'datetime' and 'value' columns. Observed data is linked
    to a specific simulated variable via ELEMENT spec.

    \b
    Examples:
      --element node:J1:depth      Compare node J1 water depth
      --element link:C1:flow       Compare conduit C1 flow rate
      --element subcatch:S1:runoff Compare subcatchment S1 runoff
    """
    inp_path, calib = _calib_session(ctx)
    try:
        data = load_observed_csv(csv_file)
        result = add_observed(calib, element, data, obs_id=obs_id)
        calib_save_session(calib)
        _ok(f"Added observed '{result['id']}': {result['n_points']} points "
            f"for element '{result['element']}'", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("observed-list")
@click.pass_context
def calibrate_observed_list(ctx):
    """List all observed datasets in the calibration session."""
    inp_path, calib = _calib_session(ctx)
    obs_list = calib.get("observed", [])
    summary = [
        {"id": o["id"], "element": o["element"], "n_points": len(o.get("data", []))}
        for o in obs_list
    ]
    _out(summary, ctx.obj)
    if not _is_json(ctx.obj):
        if summary:
            _skin.table(["ID", "Element", "Points"],
                        [[s["id"], s["element"], str(s["n_points"])] for s in summary])
        else:
            _skin.hint("No observed data defined. Use 'calibrate observed-add'.")


@calibrate.command("params-add")
@click.option("--type", "param_type", required=True,
              type=click.Choice(["subcatchment", "subarea", "conduit",
                                 "infiltration", "junction"], case_sensitive=False),
              help="Element type to calibrate.")
@click.option("--name", required=True, metavar="NAME",
              help="Element name (e.g. 'C1', 'S1') or 'ALL'.")
@click.option("--field", required=True, metavar="FIELD",
              help="Parameter field (e.g. ROUGHNESS, %%IMPERV, N-IMPERV, MAXRATE).")
@click.option("--min", "min_val", required=True, type=float, metavar="MIN")
@click.option("--max", "max_val", required=True, type=float, metavar="MAX")
@click.option("--nominal", default=None, type=float,
              help="Nominal value (default: midpoint of min..max).")
@click.pass_context
def calibrate_params_add(ctx, param_type, name, field, min_val, max_val, nominal):
    """Add a calibration parameter with min/max bounds.

    \b
    Supported param types and fields:
      subcatchment : %IMPERV, AREA, WIDTH, %SLOPE
      subarea      : N-IMPERV, N-PERV, S-IMPERV, S-PERV
      conduit      : ROUGHNESS, LENGTH
      infiltration : MAXRATE, MINRATE, DECAY, DRYTIME
      junction     : MAXDEPTH
    """
    inp_path, calib = _calib_session(ctx)
    try:
        result = calib_add_param(calib, param_type, name, field, min_val, max_val, nominal)
        calib_save_session(calib)
        _ok(f"Added param '{result['id']}': [{result['min']}, {result['max']}] "
            f"nominal={result['nominal']}", ctx.obj)
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("params-list")
@click.pass_context
def calibrate_params_list(ctx):
    """List all calibration parameters defined in the session."""
    inp_path, calib = _calib_session(ctx)
    params = calib.get("params", [])
    _out(params, ctx.obj)
    if not _is_json(ctx.obj):
        if params:
            _skin.table(
                ["ID", "Type", "Name", "Field", "Min", "Max", "Nominal"],
                [[p["id"], p["type"], p["name"], p["field"],
                  str(p["min"]), str(p["max"]), str(p["nominal"])]
                 for p in params]
            )
        else:
            _skin.hint("No parameters defined. Use 'calibrate params-add'.")


@calibrate.command("sensitivity")
@click.option("--inp", default=None, metavar="PATH", help="Override .inp file.")
@click.option("--n-steps", default=5, type=int, show_default=True,
              help="Number of steps per parameter (default 5).")
@click.pass_context
def calibrate_sensitivity(ctx, inp, n_steps):
    """Run one-at-a-time (OAT) sensitivity analysis.

    Varies each calibration parameter across its range while holding all others
    at their nominal values. Runs a SWMM simulation for each step and reports
    how metrics change with each parameter value.
    """
    inp_path, calib = _calib_session(ctx)
    target = inp or inp_path
    try:
        _info(f"Running sensitivity analysis ({n_steps} steps/param)...", ctx.obj)
        records = run_sensitivity(target, calib, n_steps=n_steps)
        calib_save_session(calib)
        _ok(f"Sensitivity complete: {len(records)} records", ctx.obj)
        _out(records, ctx.obj)
        if not _is_json(ctx.obj):
            _skin.section("Sensitivity Results")
            _skin.table(
                ["Parameter", "Value", "Element", "NSE", "RMSE"],
                [
                    [
                        r["param_id"],
                        f"{r['value']:.4g}",
                        r["element"],
                        f"{r['metrics'].get('nse', 'N/A'):.4f}" if isinstance(r['metrics'], dict) else "error",
                        f"{r['metrics'].get('rmse', 'N/A'):.4f}" if isinstance(r['metrics'], dict) else "error",
                    ]
                    for r in records
                ]
            )
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("run")
@click.option("--inp", default=None, metavar="PATH", help="Override .inp file.")
@click.option("--method", type=click.Choice(["grid", "lhs"], case_sensitive=False),
              default="lhs", show_default=True,
              help="Sampling method: 'grid' (full factorial) or 'lhs' (Latin Hypercube).")
@click.option("--n-samples", default=20, type=int, show_default=True,
              help="Number of parameter sets to evaluate.")
@click.option("--metric", type=click.Choice(["nse", "rmse", "mae"], case_sensitive=False),
              default="nse", show_default=True,
              help="Objective metric: nse (maximise), rmse/mae (minimise).")
@click.option("--seed", default=42, type=int, show_default=True,
              help="Random seed for LHS reproducibility.")
@click.pass_context
def calibrate_run(ctx, inp, method, n_samples, metric, seed):
    """Run automatic parameter calibration.

    Generates parameter sets via the chosen method, simulates each with pyswmm,
    computes metrics against all observed datasets, and identifies the best
    parameter set.

    \b
    Methods:
      lhs   Latin Hypercube Sampling — space-filling, recommended (default)
      grid  Full factorial grid — combinatorial, best for 1-2 parameters
    """
    inp_path, calib = _calib_session(ctx)
    target = inp or inp_path
    try:
        _info(
            f"Running calibration: method={method}, n_samples={n_samples}, metric={metric}",
            ctx.obj,
        )
        result = run_calibration(target, calib, method=method, n_samples=n_samples,
                                 metric=metric, seed=seed)
        calib_save_session(calib)
        _ok(f"Calibration complete: {result['n_runs']} runs evaluated", ctx.obj)

        if result["best_params"]:
            best_score = result["best_metrics"].get(metric, "N/A")
            _ok(f"Best {metric.upper()}: {best_score}", ctx.obj)

        _out(result, ctx.obj)
        if not _is_json(ctx.obj) and result["best_params"]:
            _skin.section("Best Parameters")
            _skin.status_block(
                {pid: str(round(val, 6)) for pid, val in result["best_params"].items()}
            )
            if isinstance(result["best_metrics"], dict):
                _skin.section("Best Metrics")
                _skin.status_block(
                    {k: str(v) for k, v in result["best_metrics"].items()
                     if k not in ("run", "observed_metrics")}
                )
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("apply")
@click.option("--inp", default=None, metavar="PATH", help="Source .inp file.")
@click.option("--output", default=None, metavar="PATH",
              help="Output .inp path (default: overwrite source).")
@click.pass_context
def calibrate_apply(ctx, inp, output):
    """Apply the best calibration parameters to the .inp file.

    Reads the best parameter set from the calibration session and writes it
    back into the .inp file. Use --output to write a new calibrated copy
    instead of overwriting the original.
    """
    inp_path, calib = _calib_session(ctx)
    target = inp or inp_path
    best = calib.get("best", {})
    best_params = best.get("params") if best else None

    if not best_params:
        _err("No best parameters found in calibration session. Run 'calibrate run' first.",
             ctx.obj)
        sys.exit(1)

    try:
        result = apply_best_params(target, best_params, output_path=output)
        _ok(f"Applied {result['n_applied']} parameters to {result['output']}", ctx.obj)
        if result["errors"]:
            for e in result["errors"]:
                _skin.warning(f"  {e}")
        _out(result, ctx.obj)
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("metrics")
@click.option("--observed", required=True, metavar="CSV",
              help="Observed data CSV with 'datetime' and 'value' columns.")
@click.option("--simulated", required=True, metavar="CSV",
              help="Simulated data CSV with 'datetime' and 'value' columns.")
@click.pass_context
def calibrate_metrics(ctx, observed, simulated):
    """Compute goodness-of-fit metrics between two CSV time series.

    Outputs NSE, RMSE, MAE, and PBias. Both CSV files must have 'datetime'
    and 'value' columns with matching (or overlapping) time ranges.
    """
    try:
        obs_data = load_observed_csv(observed)
        sim_data = load_observed_csv(simulated)
        metrics = compute_metrics(obs_data, sim_data)
        _out(metrics, ctx.obj)
        if not _is_json(ctx.obj):
            _skin.section("Goodness-of-Fit Metrics")
            _skin.status_block({
                "NSE (Nash-Sutcliffe)": f"{metrics['nse']:.4f}",
                "RMSE":                 f"{metrics['rmse']:.4f}",
                "MAE":                  f"{metrics['mae']:.4f}",
                "PBias (%)":            f"{metrics['pbias']:.2f}",
                "Comparison points":    str(metrics["n"]),
            })
    except Exception as e:
        _err(str(e), ctx.obj)
        sys.exit(1)


@calibrate.command("status")
@click.pass_context
def calibrate_status(ctx):
    """Show calibration session status: params, observed data, and best result."""
    inp_path, calib = _calib_session(ctx)
    params = calib.get("params", [])
    observed = calib.get("observed", [])
    runs = calib.get("runs", [])
    best = calib.get("best", {})

    summary = {
        "inp_path": inp_path,
        "n_params": len(params),
        "n_observed_sets": len(observed),
        "n_runs_completed": len(runs),
        "best_params": best.get("params") if best else None,
        "best_metrics": best.get("metrics") if best else None,
    }
    _out(summary, ctx.obj)
    if not _is_json(ctx.obj):
        _skin.status_block({
            "Project":          inp_path or "(none)",
            "Parameters":       str(len(params)),
            "Observed sets":    str(len(observed)),
            "Completed runs":   str(len(runs)),
            "Best params":      str(best.get("params")) if best and best.get("params") else "(none)",
        }, title="Calibration Session Status")


# ---------------------------------------------------------------------------
# rules group
# ---------------------------------------------------------------------------


@main.group()
@click.pass_context
def rules(ctx):
    """Control rules: add, revise, list, show, remove [CONTROLS] rules."""


@rules.command("add")
@click.option("--name", required=True, help="Unique rule ID.")
@click.option("--if", "if_clauses", required=True, multiple=True,
              metavar="CLAUSE",
              help='IF/AND condition(s), e.g. "Node J1 Depth > 4.5". '
                   'First occurrence is IF; subsequent are AND. Repeat for multiple.')
@click.option("--then", "then_actions", required=True, multiple=True,
              metavar="ACTION",
              help='THEN/AND action(s), e.g. "Pump P1 Status = ON". '
                   'First is THEN; subsequent are AND. Repeat for multiple.')
@click.option("--else", "else_actions", default=(), multiple=True,
              metavar="ACTION",
              help='ELSE/AND action(s). First is ELSE; subsequent are AND.')
@click.option("--priority", default=None, type=float,
              help="Rule priority (higher = evaluated first).")
@click.pass_context
def rules_add(ctx, name, if_clauses, then_actions, else_actions, priority):
    """Add a new control rule to [CONTROLS]."""
    sections = _require_project(ctx)
    _session.push()
    try:
        rule = add_rule(
            sections, name,
            list(if_clauses),
            list(then_actions),
            list(else_actions) or None,
            priority,
        )
        _session.save()
        _ok(f"Added rule: {name}", ctx.obj)
        _out(rule, ctx.obj)
    except (ValueError, Exception) as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)


@rules.command("list")
@click.pass_context
def rules_list(ctx):
    """List all control rules (summary)."""
    sections = _require_project(ctx)
    items = list_rules(sections)
    _out(items, ctx.obj)
    if not _is_json(ctx.obj):
        if not items:
            _skin.hint("No control rules defined.")
        else:
            _skin.section("Control Rules")
            headers = ["id", "conditions", "actions", "has_else", "priority"]
            rows = [
                [str(r.get(h, "")) for h in headers]
                for r in items
            ]
            _skin.table(headers, rows)


@rules.command("show")
@click.argument("rule_id")
@click.pass_context
def rules_show(ctx, rule_id):
    """Show the full definition of a single rule."""
    sections = _require_project(ctx)
    rule = get_rule(sections, rule_id)
    if rule is None:
        _err(f"Rule '{rule_id}' not found.", ctx.obj)
        sys.exit(1)
    _out(rule, ctx.obj)
    if not _is_json(ctx.obj):
        _skin.section(f"Rule: {rule_id}")
        for c in rule["if_clauses"]:
            _skin.info(f"  {c['type']:<5} {c['premise']}")
        for a in rule["then_actions"]:
            _skin.info(f"  {a['type']:<5} {a['action']}")
        for a in rule["else_actions"]:
            _skin.info(f"  {a['type']:<5} {a['action']}")
        if rule["priority"] is not None:
            _skin.info(f"  PRIORITY {rule['priority']}")


@rules.command("remove")
@click.option("--name", required=True, help="Rule ID to remove.")
@click.pass_context
def rules_remove(ctx, name):
    """Remove a control rule by ID."""
    sections = _require_project(ctx)
    _session.push()
    removed = remove_rule(sections, name)
    if removed:
        _session.save()
        _ok(f"Removed rule: {name}", ctx.obj)
        _out({"removed": True, "id": name}, ctx.obj)
    else:
        _session.undo()
        _err(f"Rule '{name}' not found.", ctx.obj)
        sys.exit(1)


@rules.command("revise")
@click.option("--name", required=True, help="Rule ID to revise.")
@click.option("--if", "if_clauses", default=(), multiple=True,
              metavar="CLAUSE",
              help="Replace ALL IF/AND conditions with these (repeat for multiple).")
@click.option("--then", "then_actions", default=(), multiple=True,
              metavar="ACTION",
              help="Replace ALL THEN/AND actions with these (repeat for multiple).")
@click.option("--else", "else_actions", default=(), multiple=True,
              metavar="ACTION",
              help="Replace ALL ELSE/AND actions with these (repeat for multiple).")
@click.option("--clear-else", is_flag=True, default=False,
              help="Remove the ELSE branch entirely.")
@click.option("--priority", default=None, type=float,
              help="Set/update priority.")
@click.option("--clear-priority", is_flag=True, default=False,
              help="Remove the PRIORITY clause.")
@click.pass_context
def rules_revise(ctx, name, if_clauses, then_actions, else_actions,
                 clear_else, priority, clear_priority):
    """Revise (update) an existing control rule in-place.

    Only the options you pass are updated; omitted fields are left unchanged.
    """
    sections = _require_project(ctx)
    _session.push()
    try:
        updated = revise_rule(
            sections,
            name,
            if_clauses=list(if_clauses) if if_clauses else None,
            then_actions=list(then_actions) if then_actions else None,
            else_actions=list(else_actions) if else_actions else None,
            priority=priority,
            clear_else=clear_else,
            clear_priority=clear_priority,
        )
        _session.save()
        _ok(f"Revised rule: {name}", ctx.obj)
        _out(updated, ctx.obj)
    except KeyError as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)
    except Exception as e:
        _session.undo()
        _err(str(e), ctx.obj)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main(windows_expand_args=False)
