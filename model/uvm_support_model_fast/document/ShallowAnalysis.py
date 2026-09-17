"""Mirrors src/document/ShallowAnalysis.cpp -- one document's shallow compilation.

Layer 2: builds an ast::Compilation for a single open document plus whatever
dependency trees the driver resolved, then collects the diagnostics the server
would publish for that URI. The compilation flags here track
ShallowAnalysis.cpp:97-106 exactly, and the top-instance gate that discards
analysis diagnostics is ShallowAnalysis.cpp:1142.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pyslang as ps

from ..ElabLog import ElabLog
from ..LibraryCache import LibraryCache
from ..ServerDiagClient import (
    _FILTERED_DIAGS,
    _MACRO_EXPANSION_FILTERED,
    is_waived,
    normalize_message,
)
from ..SlangOptions import DOC_MAX_INCLUDE_DEPTH, _build_opts, _compilation_opts, _source_manager
from ..Types import AstDiag

# Unique suffix source for synthesized (macro-prelude) buffers.
_BUFFER_SEQ = itertools.count(1)

def _include_closure(path: Path) -> set[Path]:
    """Every file reachable from `path` by following `include, transitively.

    Textual, like ServerDriver's build_source_closure: it does not evaluate
    `ifdef, so a conditionally-excluded include is still counted. For deciding
    "is this diagnostic in a file I pulled in?" that errs on the useful side.
    """
    seen: set[Path] = set()
    stack = [path.resolve()]
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
    seen.discard(path.resolve())
    return seen


def elaborate(
    path: Path,
    incs: list[str],
    defines: list[str],
    deps: list[Path] | None = None,
    log: "ElabLog | None" = None,
    cache: "LibraryCache | None" = None,
    sm: "ps.SourceManager | None" = None,
    macro_headers: list[str] | None = None,
    macro_packages: list[str] | None = None,
    macro_mode: bool = False,
    cross_file: bool = False,
) -> tuple[list[AstDiag], str | None]:
    """Build a shallow Compilation for one document and collect its diagnostics.

    `deps` stands in for ServerDriver::getDependentTrees -- extra trees added to
    the same compilation so the file can resolve names it does not declare.
    Only diagnostics landing in `path`'s own buffer are returned, matching the
    server, which publishes per-URI.

    `cross_file` relaxes exactly that rule: diagnostics landing in a file this
    document `include-s are kept too, tagged with the file they came from. The
    real server cannot do this -- LSP publishDiagnostics is keyed by URI, so an
    error located in dut.svh cannot be attached to my_testbench_pkg.sv's
    squiggles -- which is why errors like "interface inside a package" are
    invisible in the editor from either file. See the --show-cross-file flag.

    When `cache` is given, dependency trees come from it instead of being
    reparsed. The SourceManager must then be shared across documents too: a
    parsed tree holds BufferIDs owned by the SourceManager that parsed it, so
    reusing a tree under a fresh SourceManager would leave those buffers
    dangling. `sm` carries that shared manager.
    """
    log = log or ElabLog()
    sm = sm if sm is not None else _source_manager(incs)
    opts = _compilation_opts(_build_opts(DOC_MAX_INCLUDE_DEPTH, defines))
    try:
        comp = ps.ast.Compilation(opts)
        # The edited document is never cached: it is the thing that changes.
        #
        # When macro resolution found headers this fragment needs, they are
        # injected as a prelude ahead of the document text. Every injected line
        # shifts the document's own lines, so `line_offset` is subtracted back
        # out below -- reported line numbers must match the file on disk.
        prelude = ""
        for h in macro_headers or []:
            prelude += f'`include "{h}"\n'
        for pkg in macro_packages or []:
            prelude += f"import {pkg}::*;\n"
        line_offset = prelude.count("\n")

        if prelude:
            text = prelude + path.read_text(errors="replace")
            # The shared SourceManager rejects a second buffer with a path it
            # already holds ("Buffer with the given path has already been
            # assigned"), which happens when this file is also reachable as a
            # dependency. Give the synthesized buffer a unique name; the real
            # path is kept for reporting via the third argument.
            # Both `name` and `path` must be unique: the SourceManager keys on
            # `path`, so reusing the real path collides when this file is also
            # reachable as a dependency. Diagnostics are matched back to the
            # document by basename, so keep the real stem at the front.
            # Both `name` and `path` must be unique: the SourceManager keys on
            # `path`, so reusing the real path collides when this file is also
            # reachable as a dependency. Keep the real PARENT DIRECTORY in the
            # synthesized path -- relative `include directives in the document
            # are resolved against it, and a bare basename breaks them.
            uniq = str(path.parent / f"{path.stem}#macro{next(_BUFFER_SEQ)}{path.suffix}")
            main_tree = ps.syntax.SyntaxTree.fromText(
                text, sm, path.name, uniq, opts)
            if isinstance(main_tree, tuple):
                main_tree = main_tree[0]
            log.log(f"  tree[0] (document + {line_offset}-line macro prelude) {path}")
            for h in macro_headers or []:
                log.log(f"      injected: `include \"{h}\"")
            for pkg in macro_packages or []:
                log.log(f"      injected: import {pkg}::*;")
        else:
            main_tree = ps.syntax.SyntaxTree.fromFile(str(path), sm, opts)
            if isinstance(main_tree, tuple):
                main_tree = main_tree[0]
            log.log(f"  tree[0] (document, always reparsed) {path}")
        comp.addSyntaxTree(main_tree)
        for i, d in enumerate(deps or [], start=1):
            if not d.is_file():
                log.log(f"  tree[{i}] SKIPPED (missing) {d}")
                continue
            if cache is not None:
                before = cache.hits
                t = cache.get_tree(d, sm, opts, defines)
                tag = "cache HIT " if cache.hits > before else "cache miss"
            else:
                t = ps.syntax.SyntaxTree.fromFile(str(d), sm, opts)
                if isinstance(t, tuple):
                    t = t[0]
                tag = "no cache  "
            comp.addSyntaxTree(t)
            log.log(f"  tree[{i}] ({tag}) {d}")

        diags = list(comp.getAllDiagnostics())
        log.log(f"  compilation diagnostics (all files): {len(diags)}")
        log.log(f"  definitions: {sorted(s.name for s in comp.getDefinitions())}")

        tops = [i.name for i in comp.getRoot().topInstances]
        log.log(f"  top instances: {tops or '(none)'}")
        # Surface for the caller's summary row without changing the return type.
        log.last_top_instances = len(tops)

        # Lint-style diags (unused import, unused variable) come from a second
        # AnalysisManager pass, not from the Compilation -- ShallowAnalysis.cpp:1147.
        # ShallowAnalysis.cpp:1142 -- if the shallow compilation produced no top
        # instances, the server discards analysis diagnostics entirely. That is
        # what keeps "unused class method / formal argument" noise out of .svh
        # fragments while still reporting "unused wildcard import" in a module.
        if tops:
            ao = ps.analysis.AnalysisOptions()
            ao.flags |= ps.analysis.AnalysisFlags.CheckUnused
            mgr = ps.analysis.AnalysisManager(ao)
            comp.freeze()
            mgr.analyze(comp)
            adiags = list(mgr.getDiagnostics())
            comp.unfreeze()
            diags.extend(adiags)
            log.log(f"  analysis pass ran (CheckUnused): +{len(adiags)} diagnostic(s)")
        else:
            log.log("  analysis pass SKIPPED: no top instances "
                    "(ShallowAnalysis.cpp:1142 discards analysis diags)")
    except Exception as e:
        log.log(f"  FAILED: {e}")
        return [], str(e)

    engine = ps.DiagnosticEngine(sm)
    target = str(path.resolve())
    out: list[AstDiag] = []
    n_filtered = 0
    n_waived = 0
    waived_by_file: dict[str, int] = {}
    n_other_file = 0
    n_cross = 0
    included_files = _include_closure(path) if cross_file else set()
    for d in diags:
        code = str(d.code).replace("DiagCode(", "").rstrip(")")
        if code in _FILTERED_DIAGS:
            n_filtered += 1
            continue
        if macro_mode and code in _MACRO_EXPANSION_FILTERED:
            # In --resolve-macros mode UVM macros actually expand, generating
            # methods/properties (get_type, type_name, the factory proxy) that
            # nothing in the file calls. This applies whenever macros expand --
            # not only when WE injected the prelude, since a file may already
            # `include "uvm_macros.svh" itself.
            n_filtered += 1
            continue
        try:
            fname = sm.getFileName(d.location)
            line = sm.getLineNumber(d.location)
        except Exception:
            fname, line = "", 0
        # Library code (UVM) is waived: it is a dependency, not the user's code.
        if is_waived(fname):
            n_waived += 1
            waived_by_file[Path(fname).name] = waived_by_file.get(Path(fname).name, 0) + 1
            continue
        # Only report diagnostics in the open document's own file -- unless
        # cross_file is on and the location is in a file this document includes.
        own_file = Path(fname).name == Path(target).name
        included = cross_file and Path(fname).resolve() in included_files
        if not own_file and not included:
            n_other_file += 1
            continue
        try:
            msg = normalize_message(engine.formatMessage(d))
        except Exception:
            msg = code
        if included:
            # Attribute it to the including document, but say where it really is.
            msg = f"[in {Path(fname).name}] {msg}"
            n_cross += 1
            out.append(AstDiag(d.isError, code, msg, line, fname))
        else:
            out.append(AstDiag(d.isError, code, msg, max(1, line - line_offset), fname))

    log.log(f"  dropped: {n_filtered} by _FILTERED_DIAGS, "
            f"{n_waived} waived (library), {n_other_file} in other files")
    if cross_file and n_cross:
        log.log(f"  cross-file: {n_cross} diagnostic(s) kept from `include-d files")
    if waived_by_file:
        log.log("  waived by library file (top 10):")
        for fn, n in sorted(waived_by_file.items(), key=lambda x: -x[1])[:10]:
            log.log(f"      {n:5}  {fn}")

    # slang can report the same diagnostic once per elaborated instance.
    seen: set[tuple] = set()
    uniq: list[AstDiag] = []
    n_dupe = 0
    for d in out:
        key = (d.line, d.code, d.message)
        if key in seen:
            n_dupe += 1
            continue
        seen.add(key)
        uniq.append(d)
    uniq.sort(key=lambda x: (not x.is_error, x.line))
    log.log(f"  deduped: {n_dupe} duplicate(s) removed")
    log.log(f"  PUBLISHED: {len(uniq)} diagnostic(s) for this document")
    for d in uniq:
        tag = "ERR " if d.is_error else "warn"
        log.log(f"      {tag} L{d.line:<4} {d.code:<24} {d.message}")
    return uniq, None
