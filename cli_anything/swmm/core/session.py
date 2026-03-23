"""Stateful SWMM session with undo/redo support."""

from __future__ import annotations

import copy
import fcntl
import json
import os
from typing import Any

from cli_anything.swmm.core.project import parse_inp, write_inp


def _locked_save_json(path: str, data: Any, **dump_kwargs) -> None:
    """Atomically write JSON with exclusive file locking.

    Never uses open("w") which would truncate before lock acquisition.
    """
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "w")

    with f:
        _locked = False
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass  # Windows or unsupported FS — proceed unlocked
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class Session:
    """Stateful SWMM session with undo/redo history.

    The session stores the current .inp file path and a history stack
    of section snapshots for undo/redo operations.

    Usage:
        session = Session(inp_path="/path/to/project.inp")
        session.load()               # Load current INP into sections
        session.push()               # Snapshot current state
        # ... modify session.sections ...
        session.save()               # Write back to INP file
        session.undo()               # Restore previous state
        session.redo()               # Re-apply undone state
    """

    MAX_HISTORY = 50

    def __init__(
        self,
        inp_path: str | None = None,
        session_file: str | None = None,
    ):
        """Initialize session.

        Args:
            inp_path: Path to the current .inp file.
            session_file: Path to JSON session state file.
                          Defaults to <inp_dir>/.swmm_session.json
        """
        self.inp_path: str | None = inp_path
        self.sections: dict[str, list[str]] = {}
        self._history: list[dict[str, list[str]]] = []  # undo stack
        self._redo_stack: list[dict[str, list[str]]] = []

        if session_file is None and inp_path:
            base_dir = os.path.dirname(os.path.abspath(inp_path))
            self.session_file = os.path.join(base_dir, ".swmm_session.json")
        else:
            self.session_file = session_file

    # -------------------------------------------------------------------------
    # Load / Save
    # -------------------------------------------------------------------------

    def load(self) -> "Session":
        """Load sections from the current inp_path.

        Returns:
            self (for chaining)

        Raises:
            ValueError: If inp_path is not set.
            FileNotFoundError: If the file doesn't exist.
        """
        if not self.inp_path:
            raise ValueError("No inp_path set. Use session.inp_path = '...'")
        self.sections = parse_inp(self.inp_path)
        return self

    def save(self, path: str | None = None) -> str:
        """Write current sections back to the INP file.

        Args:
            path: Optional alternative output path.

        Returns:
            Path written to.
        """
        target = path or self.inp_path
        if not target:
            raise ValueError("No path specified for save.")
        write_inp(self.sections, target)
        return os.path.abspath(target)

    # -------------------------------------------------------------------------
    # History management
    # -------------------------------------------------------------------------

    def push(self) -> None:
        """Snapshot current sections onto the undo history stack.

        Clears the redo stack (new action invalidates redo history).
        Trims history to MAX_HISTORY entries.
        """
        snapshot = copy.deepcopy(self.sections)
        self._history.append(snapshot)
        self._redo_stack.clear()

        # Trim history
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]

    def undo(self) -> bool:
        """Restore the previous state from history.

        Returns:
            True if undo was successful, False if no history available.
        """
        if not self._history:
            return False

        # Save current state to redo stack
        self._redo_stack.append(copy.deepcopy(self.sections))
        # Restore previous state
        self.sections = self._history.pop()
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone state.

        Returns:
            True if redo was successful, False if no redo history available.
        """
        if not self._redo_stack:
            return False

        # Save current state to history
        self._history.append(copy.deepcopy(self.sections))
        # Restore redo state
        self.sections = self._redo_stack.pop()
        return True

    @property
    def history_depth(self) -> int:
        """Number of states available for undo."""
        return len(self._history)

    @property
    def redo_depth(self) -> int:
        """Number of states available for redo."""
        return len(self._redo_stack)

    # -------------------------------------------------------------------------
    # Session file persistence
    # -------------------------------------------------------------------------

    def save_session(self) -> str | None:
        """Persist session state to a JSON file.

        Saves: inp_path, section names, history count.
        Does NOT save full section contents (too large).

        Returns:
            Path to session file, or None if no session_file set.
        """
        if not self.session_file:
            return None

        data = {
            "inp_path": self.inp_path,
            "section_names": list(self.sections.keys()),
            "history_depth": self.history_depth,
            "redo_depth": self.redo_depth,
        }
        _locked_save_json(self.session_file, data, indent=2)
        return self.session_file

    def load_session(self) -> dict[str, Any] | None:
        """Load session metadata from JSON file.

        Returns:
            Session metadata dict, or None if file doesn't exist.
        """
        if not self.session_file or not os.path.exists(self.session_file):
            return None

        with open(self.session_file, "r") as f:
            data = json.load(f)

        if data.get("inp_path"):
            self.inp_path = data["inp_path"]
            if os.path.exists(self.inp_path):
                self.load()

        return data

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return current session status.

        Returns:
            Dict with session metadata.
        """
        return {
            "inp_path": self.inp_path,
            "sections": list(self.sections.keys()),
            "history_depth": self.history_depth,
            "redo_depth": self.redo_depth,
            "session_file": self.session_file,
        }
