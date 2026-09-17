"""Mirrors src/Indexer.cpp -- the workspace crawl and macro/symbol index.

Layer 1 of the two-layer model: every .sv/.svh/.v/.vh file is preprocessed with
maxIncludeDepth=0 (Indexer.cpp:91) and macros are recorded only for files that
declare no modules and no classes (Indexer.cpp:117). Feeds hover, completion
and go-to-definition -- never diagnostics.
"""

from __future__ import annotations

from pathlib import Path

from .SlangOptions import SV_EXTS



def crawl(root: Path, cfg: dict) -> list[Path]:
    """Mirrors Indexer.cpp crawl: walk for SV extensions, honour excludeDirs."""
    index_cfgs = cfg.get("index") or [{}]
    excluded: set[str] = set()
    dirs: list[Path] = []
    for ic in index_cfgs:
        for d in ic.get("excludeDirs") or []:
            excluded.add(d)
        for d in ic.get("dirs") or []:
            dirs.append(root / d)
    if not dirs:
        dirs = [root]

    found: list[Path] = []
    for base in dirs:
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix not in SV_EXTS or not p.is_file():
                continue
            if excluded & set(p.relative_to(root).parts):
                continue
            found.append(p)
    return sorted(set(found))
