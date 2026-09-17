"""Elaboration trace collector.

No C++ twin -- slang-server logs through its own INFO/WARN macros. This gathers
the per-document trace that the console output throws away.
"""

from __future__ import annotations

from pathlib import Path

class ElabLog:
    """Collects a full trace of one elaboration for the --log file.

    The console output only shows what the server would publish; everything
    else (trees added, suppressed diagnostics, why analysis did or did not run)
    is discarded. That discarded material is usually what you need when the
    model and the server disagree, so it goes here instead.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.enabled = False
        # Written by elaborate() so run() can build its summary row.
        self.last_top_instances = 0

    def section(self, title: str) -> None:
        if not self.enabled:
            return
        self.lines.append("")
        self.lines.append(title)
        self.lines.append("-" * len(title))

    def log(self, msg: str = "") -> None:
        if not self.enabled:
            return
        self.lines.append(msg)

    def write(self, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("\n".join(self.lines) + "\n")
