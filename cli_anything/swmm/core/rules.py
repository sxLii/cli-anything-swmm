"""SWMM control rules management: [CONTROLS] section.

SWMM control rules conditionally set pump/orifice/weir status and settings
based on system state (node depth, link flow, simulation time, etc.).

Rule format in .inp file::

    RULE  RuleName
    IF    Node J1 Depth > 4.5
    AND   Node J2 Depth > 3.0
    THEN  Pump P1 Status = ON
    AND   Orifice O1 Setting = 0.5
    ELSE  Pump P1 Status = OFF
    PRIORITY 1
"""

from __future__ import annotations

from typing import Any

# Keywords that begin a clause line
_CLAUSE_KEYWORDS = {"RULE", "IF", "AND", "OR", "THEN", "ELSE", "PRIORITY"}

_SECTION_HEADER = [
    ";;Name",
    ";;-------------- ",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith(";;")


def _rule_lines_to_dict(lines: list[str]) -> dict[str, Any] | None:
    """Parse a block of lines belonging to a single rule into a dict."""
    rule: dict[str, Any] = {
        "id": None,
        "if_clauses": [],
        "then_actions": [],
        "else_actions": [],
        "priority": None,
    }
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(";;"):
            continue
        parts = stripped.split(None, 1)
        keyword = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if keyword == "RULE":
            rule["id"] = rest
        elif keyword == "IF":
            rule["if_clauses"].append({"type": "IF", "premise": rest})
        elif keyword == "AND":
            # AND can attach to IF chain or THEN chain or ELSE chain
            # Infer by what was seen last
            if rule["else_actions"]:
                rule["else_actions"].append({"type": "AND", "action": rest})
            elif rule["then_actions"]:
                rule["then_actions"].append({"type": "AND", "action": rest})
            else:
                rule["if_clauses"].append({"type": "AND", "premise": rest})
        elif keyword == "OR":
            rule["if_clauses"].append({"type": "OR", "premise": rest})
        elif keyword == "THEN":
            rule["then_actions"].append({"type": "THEN", "action": rest})
        elif keyword == "ELSE":
            rule["else_actions"].append({"type": "ELSE", "action": rest})
        elif keyword == "PRIORITY":
            try:
                rule["priority"] = float(rest)
            except ValueError:
                rule["priority"] = rest

    if rule["id"] is None:
        return None
    return rule


def _dict_to_lines(rule: dict[str, Any]) -> list[str]:
    """Serialise a rule dict back to .inp text lines (without trailing blank)."""
    lines: list[str] = []
    lines.append(f"RULE  {rule['id']}")
    for clause in rule["if_clauses"]:
        lines.append(f"{clause['type']:<5} {clause['premise']}")
    for action in rule["then_actions"]:
        lines.append(f"{action['type']:<5} {action['action']}")
    for action in rule["else_actions"]:
        lines.append(f"{action['type']:<5} {action['action']}")
    if rule["priority"] is not None:
        lines.append(f"PRIORITY {rule['priority']!s}")
    return lines


def _split_into_blocks(section_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Split section lines into (header_comments, list_of_rule_line_blocks)."""
    header: list[str] = []
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in section_lines:
        stripped = line.strip()
        if _is_comment(line) and current is None:
            header.append(line)
            continue

        upper = stripped.upper()
        if upper.startswith("RULE ") or upper == "RULE":
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
        # Orphan comment/blank lines between rules go to header

    if current is not None:
        blocks.append(current)

    return header, blocks


def _reassemble_section(header: list[str], blocks: list[list[str]]) -> list[str]:
    lines: list[str] = list(header)
    for block in blocks:
        lines.extend(block)
        lines.append("")  # blank line between rules
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_rules(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Return all control rules as a list of dicts.

    Args:
        sections: INP sections dict.

    Returns:
        List of rule dicts, each with keys:
        ``id``, ``if_clauses``, ``then_actions``, ``else_actions``, ``priority``.
    """
    _, blocks = _split_into_blocks(sections.get("CONTROLS", []))
    rules = []
    for block in blocks:
        r = _rule_lines_to_dict(block)
        if r:
            rules.append(r)
    return rules


def get_rule(sections: dict[str, list[str]], rule_id: str) -> dict[str, Any] | None:
    """Return the rule with the given ID, or None if not found."""
    for rule in parse_rules(sections):
        if rule["id"] == rule_id:
            return rule
    return None


def list_rules(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Return a lightweight summary list for all rules.

    Each entry has ``id``, ``conditions`` (count), ``actions`` (count),
    ``has_else``, and ``priority``.
    """
    return [
        {
            "id": r["id"],
            "conditions": len(r["if_clauses"]),
            "actions": len(r["then_actions"]),
            "has_else": bool(r["else_actions"]),
            "priority": r["priority"],
        }
        for r in parse_rules(sections)
    ]


def add_rule(
    sections: dict[str, list[str]],
    rule_id: str,
    if_clauses: list[str],
    then_actions: list[str],
    else_actions: list[str] | None = None,
    priority: float | None = None,
) -> dict[str, Any]:
    """Add a new control rule to the [CONTROLS] section.

    If a rule with the same *rule_id* already exists it is replaced.

    Args:
        sections: INP sections dict (modified in-place).
        rule_id: Unique rule name.
        if_clauses: Condition strings in SWMM syntax, e.g.
            ``["Node J1 Depth > 4.5", "Node J2 Depth > 3.0"]``.
            The first item maps to ``IF``, remaining items map to ``AND``.
        then_actions: Action strings, e.g. ``["Pump P1 Status = ON"]``.
            First item maps to ``THEN``, remaining to ``AND``.
        else_actions: Optional alternate actions (first maps to ``ELSE``).
        priority: Optional numeric priority (higher runs first).

    Returns:
        The rule dict that was added.

    Raises:
        ValueError: If rule_id is empty or clause lists are empty.
    """
    if not rule_id or not rule_id.strip():
        raise ValueError("rule_id must not be empty")
    if not if_clauses:
        raise ValueError("at least one IF clause is required")
    if not then_actions:
        raise ValueError("at least one THEN action is required")

    # Build clause dicts
    if_dicts: list[dict[str, str]] = []
    for i, c in enumerate(if_clauses):
        if_dicts.append({"type": "IF" if i == 0 else "AND", "premise": c})

    then_dicts: list[dict[str, str]] = []
    for i, a in enumerate(then_actions):
        then_dicts.append({"type": "THEN" if i == 0 else "AND", "action": a})

    else_dicts: list[dict[str, str]] = []
    if else_actions:
        for i, a in enumerate(else_actions):
            else_dicts.append({"type": "ELSE" if i == 0 else "AND", "action": a})

    rule = {
        "id": rule_id,
        "if_clauses": if_dicts,
        "then_actions": then_dicts,
        "else_actions": else_dicts,
        "priority": priority,
    }

    # Ensure section exists
    if "CONTROLS" not in sections:
        sections["CONTROLS"] = list(_SECTION_HEADER)

    # Remove existing rule with same id (replace semantics)
    header, blocks = _split_into_blocks(sections["CONTROLS"])
    blocks = [b for b in blocks if _rule_lines_to_dict(b) and _rule_lines_to_dict(b)["id"] != rule_id]

    # Append new rule
    blocks.append(_dict_to_lines(rule))
    sections["CONTROLS"] = _reassemble_section(header, blocks)

    return rule


def remove_rule(sections: dict[str, list[str]], rule_id: str) -> bool:
    """Remove the rule with the given ID from [CONTROLS].

    Args:
        sections: INP sections dict (modified in-place).
        rule_id: Rule name to remove.

    Returns:
        True if removed, False if not found.
    """
    if "CONTROLS" not in sections:
        return False
    header, blocks = _split_into_blocks(sections["CONTROLS"])
    new_blocks = [b for b in blocks if not (_rule_lines_to_dict(b) and _rule_lines_to_dict(b)["id"] == rule_id)]
    if len(new_blocks) == len(blocks):
        return False
    sections["CONTROLS"] = _reassemble_section(header, new_blocks)
    return True


def revise_rule(
    sections: dict[str, list[str]],
    rule_id: str,
    if_clauses: list[str] | None = None,
    then_actions: list[str] | None = None,
    else_actions: list[str] | None = None,
    priority: float | None = None,
    clear_else: bool = False,
    clear_priority: bool = False,
) -> dict[str, Any]:
    """Revise (update) fields of an existing rule in-place.

    Only the fields that are explicitly passed (non-None) are updated.
    Pass ``clear_else=True`` to remove the ELSE branch entirely.
    Pass ``clear_priority=True`` to remove the PRIORITY clause.

    Args:
        sections: INP sections dict (modified in-place).
        rule_id: Rule to modify.
        if_clauses: New IF/AND conditions (replaces all existing conditions).
        then_actions: New THEN/AND actions (replaces all existing actions).
        else_actions: New ELSE/AND actions (replaces existing ELSE branch).
        priority: New priority value.
        clear_else: If True, remove the ELSE branch regardless of else_actions.
        clear_priority: If True, remove the PRIORITY clause.

    Returns:
        Updated rule dict.

    Raises:
        KeyError: If rule_id does not exist.
    """
    existing = get_rule(sections, rule_id)
    if existing is None:
        raise KeyError(f"Rule '{rule_id}' not found")

    # Apply updates
    if if_clauses is not None:
        new_if: list[dict[str, str]] = []
        for i, c in enumerate(if_clauses):
            new_if.append({"type": "IF" if i == 0 else "AND", "premise": c})
        existing["if_clauses"] = new_if

    if then_actions is not None:
        new_then: list[dict[str, str]] = []
        for i, a in enumerate(then_actions):
            new_then.append({"type": "THEN" if i == 0 else "AND", "action": a})
        existing["then_actions"] = new_then

    if clear_else:
        existing["else_actions"] = []
    elif else_actions is not None:
        new_else: list[dict[str, str]] = []
        for i, a in enumerate(else_actions):
            new_else.append({"type": "ELSE" if i == 0 else "AND", "action": a})
        existing["else_actions"] = new_else

    if clear_priority:
        existing["priority"] = None
    elif priority is not None:
        existing["priority"] = priority

    # Re-serialise: remove old block, insert updated block
    header, blocks = _split_into_blocks(sections.get("CONTROLS", []))
    new_blocks: list[list[str]] = []
    for block in blocks:
        r = _rule_lines_to_dict(block)
        if r and r["id"] == rule_id:
            new_blocks.append(_dict_to_lines(existing))
        else:
            new_blocks.append(block)
    sections["CONTROLS"] = _reassemble_section(header, new_blocks)

    return existing
