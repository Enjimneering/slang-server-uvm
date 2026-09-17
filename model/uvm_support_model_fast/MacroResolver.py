"""Proposed server behaviour: resolve a fragment's missing macros via the index.

No C++ twin -- this is the change being prototyped. When a document references
a macro its own compilation unit cannot see, look up the defining header in the
Indexer's macro table, preferring the library's umbrella header over crawling
the project tree, and inject it ahead of the document text.
"""

from __future__ import annotations

import re
from pathlib import Path

from .ServerDriver import macro_uses


def _already_imports(path: Path, pkg: str) -> bool:
    """True if `path` already imports `pkg` anywhere (file, module or class scope)."""
    try:
        src = path.read_text(errors="replace")
    except OSError:
        return False
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.search(rf"\bimport\s+{re.escape(pkg)}\s*::", src) is not None


def resolve_macro_headers(
    path: Path,
    macro_to_files: dict[str, list[Path]],
    incs: list[str],
) -> tuple[list[str], list[str]]:
    """Find which headers define the macros a file uses but cannot see.

    This is the lookup half of the proposed server change: when a document
    references `some_macro that its own compilation unit does not define, ask
    the index which file defines it, and prefer a library header over crawling
    the file's own directory tree.

    Returns (headers_to_include, packages_to_import).

    Ordering matters and is the point of "searches in the uvm library before
    just digging down":

      1. If the defining file lives under an include directory (the UVM library),
         emit the include path RELATIVE to that directory -- `uvm_macros.svh`,
         not a deep absolute path. That is the include a human would write, and
         it lets slang resolve it through the normal -I mechanism.
      2. Prefer the library's umbrella header (uvm_macros.svh) over the specific
         defining file (macros/uvm_message_defines.svh). The umbrella pulls in
         the whole macro family in the order UVM expects; including one macro
         file directly can break because UVM macros reference each other.
      3. Only if no include directory covers the file do we fall back to a path
         relative to the document itself.
    """
    used = macro_uses(path)
    if not used:
        return [], []

    needed = sorted(m for m in used if m in macro_to_files)
    if not needed:
        return [], []

    headers: list[str] = []
    packages: list[str] = []
    inc_paths = [Path(i) for i in incs]

    covered_by_library = False
    for macro in needed:
        definer = macro_to_files[macro][0].resolve()
        for ip in inc_paths:
            try:
                definer.relative_to(ip)
            except ValueError:
                continue
            # Step 2: umbrella header if the library provides one.
            umbrella = ip / "uvm_macros.svh"
            if umbrella.is_file():
                if "uvm_macros.svh" not in headers:
                    headers.append("uvm_macros.svh")
                    # The macros expand into calls on the library package, so
                    # the package has to be in scope too -- but only add the
                    # import if the file does not already have one. A file that
                    # imports uvm_pkg inside a module (the normal place for a
                    # design unit) is already covered; injecting a second import
                    # at file scope would be redundant and get reported as an
                    # "unused wildcard import" against a line the user's file
                    # does not even contain.
                    if not _already_imports(path, "uvm_pkg"):
                        packages.append("uvm_pkg")
                covered_by_library = True
            else:
                rel = str(definer.relative_to(ip).as_posix())
                if rel not in headers:
                    headers.append(rel)
                covered_by_library = True
            break

    if not covered_by_library:
        # Step 3: fall back to a document-relative include.
        for macro in needed:
            definer = macro_to_files[macro][0].resolve()
            try:
                rel = str(definer.relative_to(path.parent).as_posix())
            except ValueError:
                rel = str(definer)
            if rel not in headers:
                headers.append(rel)

    return headers, packages
