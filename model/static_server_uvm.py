#!/usr/bin/env python3
"""Static pyslang model of slang-server's indexing/preprocessing behaviour.

Point it at a repo root and a .slang/server.json and it reproduces, without
running the server, the two-layer split described in
tests/data/uvm_support/context.md:

  Layer 1 (index)     -- Indexer.cpp:74 indexPaths()
                         crawls every .sv/.svh/.v/.vh, preprocesses each with
                         maxIncludeDepth=0, and records macros ONLY for files
                         that declare no modules and no classes.
                         Feeds hover / completion / go-to-definition.

  Layer 2 (document)  -- SlangDoc.cpp:96 getSyntaxTree()
                         parses one open file with the real include path from
                         `flags`, following includes for real.
                         Feeds diagnostics (the red squiggles).

The implementation is split across uvm_support_model/, mirroring the C++ source
layout; see uvm_support_model/__init__.py for the file-by-file mapping.

Usage:
    python model/static_server_uvm.py <repo-root> [--open FILE]... [--log FILE]
                                      [--resolve-macros] [--no-cache] [--no-waivers]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from uvm_support_model.ServerDiagClient import WAIVED_PATH_PARTS
from uvm_support_model.StaticServer import run

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    
    ap.add_argument("root", type=Path, help="repo root to model")

    ap.add_argument("--config", type=Path, default=None,
                    help="server.json (default: <root>/.slang/server.json)")
    
    ap.add_argument("--open", action="append", default=[], metavar="FILE",
                    help="repo-relative file to model as open; repeatable")
    
    ap.add_argument("--log", type=Path, default=None, metavar="FILE",
                    help="write a full elaboration trace here (trees added, "
                         "definitions, top instances, waived and dropped diags)")
    
    ap.add_argument("--no-waivers", action="store_true",
                    help="do not waive library (UVM) diagnostics")
    
    ap.add_argument("--resolve-macros", action="store_true",
                    help="when a document uses a macro it cannot see, look up "
                         "the defining header in the index (preferring the "
                         "library umbrella header) and inject it, then "
                         "elaborate fully")
    
    ap.add_argument("--show-cross-file", action="store_true",
                    help="also report diagnostics located in files this "
                         "document `include-s. The real server cannot: LSP "
                         "keys diagnostics by URI, so an error inside an "
                         "included file is invisible from both the includer "
                         "and the include (where it may be legal standalone)")

    ap.add_argument("--no-cache", action="store_true",
                    help="disable the pre-parsed library cache (reparse every "
                         "dependency per document), for A/B timing")

    a = ap.parse_args()
    root = a.root.resolve()
    if not root.is_dir():
        return print(f"not a directory: {root}") or 1
    if a.no_waivers:
        WAIVED_PATH_PARTS.clear()
    return run(root, a.config, a.open, a.log, use_cache=not a.no_cache,
               resolve_macros=a.resolve_macros,
               cross_file=a.show_cross_file)


if __name__ == "__main__":
    raise SystemExit(main())