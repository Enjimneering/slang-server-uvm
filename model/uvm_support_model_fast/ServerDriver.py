"""Mirrors src/ServerDriver.cpp -- dependency resolution and build-file handling.

getDependentTrees (ServerDriver.cpp:426) walks a worklist of referenced-but-
undeclared names, asking the Indexer which file declares each. resolve_deps()
models that; resolve_deps_deep() is the proposed extension that also looks
inside class bodies once macros are expandable.

build_source_closure() models m_buildSourceUris (ServerDriver.cpp:289) -- the
files the build file pulls into the compilation.
"""

from __future__ import annotations

import re
from pathlib import Path

from .Config import Flags
from .ServerDiagClient import is_waived

def build_source_closure(root: Path, flags: Flags) -> list[Path]:
    """Files reachable from the build file's roots, following `include.

    Models ServerDriver's `m_buildSourceUris` (ServerDriver.cpp:289): the set of
    files the build file actually pulls into the compilation. The server itself
    never chooses files to analyse -- it analyses whatever the editor has open
    (m_openDocs, SlangServer.cpp:895/931) -- so there is no exact analogue for a
    batch tool. This is the closest principled stand-in: it is what the project
    declares it builds, it tracks edits to uvm.f automatically, and it excludes
    both library internals and unrelated fixtures.

    Library files are dropped: they are dependencies, not documents a user
    would have open, and their own diagnostics are waived everywhere else.
    """
    seen: set[Path] = set()
    stack = [(root / f).resolve() for f in flags.files]
    while stack:
        p = stack.pop()
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        try:
            src = p.read_text(errors="replace")
        except OSError:
            continue
        src = re.sub(r"//[^\n]*", "", src)
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        for inc in re.findall(r'`include\s+"([^"]+)"', src):
            cand = p.parent / inc
            if cand.is_file():
                stack.append(cand.resolve())
    return sorted(p for p in seen if not is_waived(str(p)))


def count_direct_includes(path: Path) -> int:
    """`include directives written in this file (not transitively pulled in)."""
    try:
        src = path.read_text(errors="replace")
    except OSError:
        return 0
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return len(re.findall(r'`include\s+"[^"]+"', src))



def _includes(candidate: Path, target: Path) -> bool:
    """True if `candidate` textually `include`s `target` (one level)."""
    try:
        src = candidate.read_text(errors="replace")
    except OSError:
        return False
    for inc in re.findall(r'`include\s+"([^"]+)"', src):
        if (candidate.parent / inc).resolve() == target:
            return True
    return False


def resolve_deps(
    path: Path,
    root: Path,
    symbol_to_file: dict[str, Path],
    flags: Flags,
) -> list[Path]:
    """Model ServerDriver::getDependentTrees (ServerDriver.cpp:426).

    The C++ walks a worklist: for each name referenced but not declared in the
    tree, ask the INDEX which file declares it, load that file, repeat.

    Two consequences worth stating, because both are load-bearing:

    * Dependencies come from the index, NOT from the files listed in `flags`.
      A file can be a compilation root in uvm.f and still be invisible here if
      the indexer never recorded its symbols. `design.sv` is exactly that case
      for `.svh` fragments, which is why the server still reports
      "unknown interface 'dut_if'" in my_driver.svh even after design.sv was
      added to the build file.
    * A file that `include`s the open document is never added. The server
      compiles an open document as its own unit; pulling in its includer would
      double-define everything and hand the fragment a package scope it does
      not have.
    """
    deps: list[Path] = []
    me = path.resolve()

    try:
        src = path.read_text(errors="replace")
    except OSError:
        return deps
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)

    declared = {
        m for m in re.findall(
            r"\b(?:module|interface|package|program|class)\s+(\w+)", src
        )
    }

    # The C++ drives this from slang's ParserMetadata::visitReferencedSymbols,
    # which records symbols referenced at *module* scope. pyslang does not
    # expose ParserMetadata, so approximate it by ignoring class bodies: a
    # `virtual dut_if` inside a class is not a top-level referenced symbol, and
    # the server correspondingly does NOT pull design.sv in for my_driver.svh
    # (it still reports "unknown interface 'dut_if'" there).
    src = re.sub(r"\bclass\b.*?\bendclass\b", " ", src, flags=re.S)
    for name in sorted(set(re.findall(r"\b([A-Za-z_]\w*)\b", src))):
        if name in declared:
            continue
        target = symbol_to_file.get(name)
        if not target:
            continue  # index cannot resolve it -> server cannot either
        target = target.resolve()
        if target == me or target in deps:
            continue
        # Skip in BOTH directions:
        #  - target includes me   -> adding it would double-define this document
        #  - me includes target   -> it is already in my tree via `include, and
        #    adding it again compiles its contents twice (once at file scope,
        #    where an interface/module is legal, and once inside whatever
        #    construct included it, where it may not be)
        if _includes(target, me) or _includes(me, target):
            continue
        deps.append(target)
    return deps


def resolve_deps_deep(
    path: Path,
    root: Path,
    symbol_to_file: dict[str, Path],
    already: list[Path],
) -> list[Path]:
    """Resolve names referenced anywhere in the file, class bodies included.

    resolve_deps() deliberately ignores class bodies because that is what the
    current server does (ParserMetadata records module-scope references only).
    Once macros are expandable, that restriction is the thing standing between
    a fragment and a full elaboration: `virtual dut_if` inside a class is a
    real dependency even though it is not a module-scope reference.

    Only called in --resolve-macros mode, and only AFTER the library lookup,
    so the library is always preferred over crawling the project tree.
    """
    out: list[Path] = []
    me = path.resolve()
    try:
        src = path.read_text(errors="replace")
    except OSError:
        return out
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    declared = set(re.findall(
        r"\b(?:module|interface|package|program|class)\s+(\w+)", src))
    for name in sorted(set(re.findall(r"\b([A-Za-z_]\w*)\b", src))):
        if name in declared:
            continue
        target = symbol_to_file.get(name)
        if not target:
            continue
        target = target.resolve()
        if target == me or target in already or target in out:
            continue
        # Skip in BOTH directions:
        #  - target includes me   -> adding it would double-define this document
        #  - me includes target   -> it is already in my tree via `include, and
        #    adding it again compiles its contents twice (once at file scope,
        #    where an interface/module is legal, and once inside whatever
        #    construct included it, where it may not be)
        if _includes(target, me) or _includes(me, target):
            continue
        out.append(target)
    return out


def macro_uses(path: Path) -> set[str]:
    """Textual scan for `macro_name uses -- cheap and layer-independent."""
    try:
        src = path.read_text(errors="replace")
    except OSError:
        return set()
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    directives = {
        "define", "include", "ifdef", "ifndef", "else", "elsif", "endif",
        "timescale", "undef", "line", "begin_keywords", "end_keywords",
        "default_nettype", "resetall", "celldefine", "endcelldefine",
        "unconnected_drive", "nounconnected_drive", "pragma", "__FILE__",
        "__LINE__",
    }
    return {m for m in re.findall(r"`([A-Za-z_]\w*)", src) if m not in directives}
