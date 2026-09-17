"""Mirrors src/Config.cpp -- flag parsing and layered server.json loading.

Models the hierarchical config described in docs/start/config.md: workspace,
then user, then local, with `flags` merged and `-f` command files followed.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Flags:
    """The subset of slang flags that changes indexing/preprocessing."""

    include_dirs: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


def parse_flag_string(text: str, root: Path, _seen: set[Path] | None = None) -> Flags:
    """Parse a slang flag string, following -f command files recursively."""
    _seen = _seen if _seen is not None else set()
    out = Flags()
    # slang command files allow // comments
    text = re.sub(r"//[^\n]*", "", text)
    toks = shlex.split(text)
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("-f", "-F"):
            i += 1
            if i < len(toks):
                sub = (root / toks[i]).resolve()
                if sub.is_file() and sub not in _seen:
                    _seen.add(sub)
                    nested = parse_flag_string(sub.read_text(), root, _seen)
                    out.include_dirs += nested.include_dirs
                    out.defines += nested.defines
                    out.files += nested.files
        elif t in ("-I", "--include-directory", "+incdir+"):
            i += 1
            if i < len(toks):
                out.include_dirs.append(toks[i])
        elif t.startswith("-I"):
            out.include_dirs.append(t[2:])
        elif t in ("-D", "--define-macro"):
            i += 1
            if i < len(toks):
                out.defines.append(toks[i])
        elif t.startswith("-D"):
            out.defines.append(t[2:])
        elif not t.startswith("-"):
            out.files.append(t)
        i += 1
    return out

def load_config(root: Path, config_path: Path | None) -> tuple[Flags, dict]:
    """Layer configs the way SlangServer does: workspace, then user, then local.

    Only `flags` merging is modelled (workspace overrides user, local appends).
    """
    candidates = [
        config_path or (root / ".slang" / "server.json"),
        Path.home() / ".slang" / "server.json",
        root / ".slang" / "local" / "server.json",
    ]
    raw: dict = {}
    flag_text: list[str] = []
    for c in candidates:
        if not c.is_file():
            continue
        try:
            data = json.loads(c.read_text())
        except json.JSONDecodeError as e:
            print(f"  ! {c}: bad JSON ({e})", file=sys.stderr)
            continue
        raw.update(data)
        if data.get("flags"):
            flag_text.append(data["flags"])
    return parse_flag_string(" ".join(flag_text), root), raw