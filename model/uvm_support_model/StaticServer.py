"""Mirrors src/SlangServer.cpp -- the top-level orchestration.

The real server is reactive: it analyses whatever the editor has open
(m_openDocs, SlangServer.cpp:895/931) and nothing else. A batch tool has no
editor, so --open models that set explicitly and the build-file closure stands
in when none is given.
"""

from __future__ import annotations

import time
from pathlib import Path

import pyslang as ps

from .Config import Flags, load_config
from .ElabLog import ElabLog
from .Indexer import crawl
from .LibraryCache import LibraryCache
from .MacroResolver import resolve_macro_headers
from .ServerDiagClient import WAIVED_PATH_PARTS, is_waived
from .ServerDriver import (
    build_source_closure,
    count_direct_includes,
    resolve_deps,
    resolve_deps_deep,
    macro_uses,
)
from .SlangOptions import DOC_MAX_INCLUDE_DEPTH, INDEX_MAX_INCLUDE_DEPTH, SV_EXTS, _source_manager
from .Types import FileSummary
from .document.ShallowAnalysis import elaborate
from .document.SyntaxIndexer import parse_file




def run(root: Path, config_path: Path | None, open_files: list[str],
        log_path: Path | None = None, use_cache: bool = True,
        resolve_macros: bool = False, cross_file: bool = False) -> int:
    t_start = time.perf_counter()
    flags, cfg = load_config(root, config_path)
    incs = [str((root / i).resolve()) for i in flags.include_dirs]

    print(f"repo root   : {root}")
    print(f"include dirs: {incs or '(none)'}")
    print(f"defines     : {flags.defines or '(none)'}")
    print()

    t_crawl = time.perf_counter()
    files = crawl(root, cfg)
    print(f"crawled {len(files)} files matching {sorted(SV_EXTS)}")

    # ---- Layer 1: the index (maxIncludeDepth = 0, no include path) ----
    macro_to_files: dict[str, list[Path]] = {}
    symbol_to_file: dict[str, Path] = {}
    skipped_by_heuristic: list[Path] = []

    for f in files:
        r = parse_file(f, INDEX_MAX_INCLUDE_DEPTH, [], flags.defines)
        if r.error:
            continue
        has_symbols = bool(r.modules or r.packages)
        if has_symbols:
            # extractFromRoot(): record symbols, macros NOT recorded
            for nm in r.modules + r.packages:
                symbol_to_file.setdefault(nm, f)
        elif not r.classes:
            # Indexer.cpp:117 -- macros only when no modules AND no classes
            for m in r.defines:
                macro_to_files.setdefault(m, []).append(f)
        else:
            # class-bearing header: contributes NOTHING to the index
            skipped_by_heuristic.append(f)

    print(f"  indexed macros : {len(macro_to_files)}")
    print(f"  indexed symbols: {len(symbol_to_file)}")
    index_ms = (time.perf_counter() - t_crawl) * 1000.0
    print(f"  files dropped by the class heuristic (Indexer.cpp:117): "
          f"{len(skipped_by_heuristic)}")
    for f in skipped_by_heuristic[:10]:
        print(f"      {f.relative_to(root)}")
    if len(skipped_by_heuristic) > 10:
        print(f"      ... and {len(skipped_by_heuristic)-10} more")
    print()

    # ---- Layer 2: the document (real include path, includes followed) ----
    # --open models the server's m_openDocs: the tabs the editor has open, which
    # is the only thing the server ever analyses. With none given, fall back to
    # the build file's include closure (see build_source_closure).
    if open_files:
        targets = [Path(o) if Path(o).is_absolute() else root / o
                   for o in open_files]
        target_source = f"--open ({len(targets)} file(s))"
    else:
        targets = build_source_closure(root, flags)
        target_source = f"build-file closure of {len(flags.files)} root(s) in flags"
        if not targets:
            targets = skipped_by_heuristic or files[:10]
            target_source = "fallback: heuristic-dropped files (no build roots found)"
    print(f"targets: {target_source}")
    for t in targets:
        try:
            print(f"    {t.relative_to(root)}")
        except ValueError:
            print(f"    {t}")
    print()

    # One SourceManager shared by every document, so cached trees stay valid
    # (a tree's BufferIDs belong to the manager that parsed it).
    shared_sm = _source_manager(incs) if use_cache else None
    cache = LibraryCache() if use_cache else None

    elog = ElabLog()
    elog.enabled = log_path is not None
    elog.log("slang-server static model -- elaboration log")
    elog.log(f"repo root   : {root}")
    elog.log(f"include dirs: {incs}")
    elog.log(f"defines     : {flags.defines}")
    elog.log(f"waived paths: {WAIVED_PATH_PARTS}")
    elog.log(f"crawled     : {len(files)} files")
    elog.log(f"indexed     : {len(macro_to_files)} macros, {len(symbol_to_file)} symbols")
    elog.log(f"targets     : {target_source}")

    t_elab_phase = time.perf_counter()
    print("per-document elaboration (SlangDoc.cpp:96) + AST (ShallowAnalysis.cpp):")
    print()
    divergent_total = 0
    ast_error_total = 0
    summary: list[FileSummary] = []
    for f in targets:
        if not f.is_file():
            print(f"  {f}: missing")
            continue
        doc = parse_file(f, DOC_MAX_INCLUDE_DEPTH, incs, flags.defines)
        visible = set(doc.defines)
        used = macro_uses(f)

        # Macros this file uses that its own compilation unit cannot see.
        missing = sorted(used - visible)
        # Of those, the ones the INDEX can happily hover.
        hoverable = [m for m in missing if m in macro_to_files]

        rel = f.relative_to(root)
        print(f"  {rel}")
        print(f"      includes      : {doc.includes or '(none)'}")
        print(f"      macros visible: {len(visible)}")
        print(f"      macros used   : {len(used)}")
        if hoverable:
            if resolve_macros:
                # --resolve-macros injects the defining header below, so these
                # are about to become elaborable. Report them as RESOLVED, not
                # DIVERGENT: divergence is the state this mode exists to fix,
                # and counting it here would describe the input, not the result.
                print(f"      resolvable    : {len(hoverable)} macro(s) "
                      f"missing from this unit, will inject defining header")
            else:
                divergent_total += len(hoverable)
                print(f"      DIVERGENT     : {len(hoverable)} macro(s) hover but do not elaborate")
                for m in hoverable[:6]:
                    src = macro_to_files[m][0].relative_to(root)
                    print(f"          `{m}  (indexed from {src})")
                if len(hoverable) > 6:
                    print(f"          ... and {len(hoverable)-6} more")
        elif missing:
            print(f"      missing+unindexed: {missing[:6]}")
        else:
            print("      consistent: every used macro is elaborable")

        # ---- Layer 3: AST elaboration (ShallowAnalysis.cpp) ----
        deps = resolve_deps(f, root, symbol_to_file, flags)
        elog.section(f"ELABORATE {f.relative_to(root)}")
        elog.log(f"  include dirs: {incs or '(none)'}")
        elog.log(f"  defines     : {flags.defines or '(none)'}")
        elog.log(f"  deps resolved via index: {len(deps)}")
        mac_headers: list[str] = []
        mac_pkgs: list[str] = []
        if resolve_macros and hoverable:
            mac_headers, mac_pkgs = resolve_macro_headers(f, macro_to_files, incs)
            # An injected `import uvm_pkg::*` only binds if the package's tree is
            # actually in the compilation. getDependentTrees never reaches it for
            # a class-bearing fragment (no module-scope references), so add the
            # library roots explicitly -- they come from the cache, so this is
            # a tree lookup, not a reparse.
            for pkg in mac_pkgs:
                src = symbol_to_file.get(pkg)
                if src is None:
                    for cand in flags.files:
                        cp = (root / cand).resolve()
                        if cp.is_file() and cp.stem == pkg:
                            src = cp
                            break
                if src is not None and src not in deps:
                    deps.append(src)
            # Second pass: with macros expandable, names that were previously
            # hidden inside unexpanded macro bodies (and types used only in
            # class bodies) become resolvable. Ask the index for any remaining
            # undeclared name -- this is the "crawl down" step, run only after
            # the library lookup above, never before it.
            extra = resolve_deps_deep(f, root, symbol_to_file, deps)
            for e in extra:
                if e not in deps:
                    deps.append(e)
            if mac_headers:
                print(f"      macro resolution: +{mac_headers} "
                      f"{'+import ' + ','.join(mac_pkgs) if mac_pkgs else ''}"
                      f"{' +' + str(len(extra)) + ' crawled' if extra else ''}")

        t_elab = time.perf_counter()
        diags, err = elaborate(f, incs, flags.defines, deps, log=elog,
                               cache=cache, sm=shared_sm,
                               macro_headers=mac_headers,
                               macro_packages=mac_pkgs,
                               macro_mode=resolve_macros,
                               cross_file=cross_file)
        elapsed_ms = (time.perf_counter() - t_elab) * 1000.0
        elog.log(f"  elapsed: {elapsed_ms:.1f} ms")

        row = FileSummary(
            path=str(rel),
            macros_used=len(used),
            macros_visible=len(visible),
            # In --resolve-macros mode the defining header is injected, so the
            # macros are no longer divergent by the time we elaborate.
            macros_divergent=0 if (resolve_macros and mac_headers) else len(hoverable),
            includes_direct=count_direct_includes(f),
            includes_total=len(doc.includes),
            deps=len(deps),
            top_instances=elog.last_top_instances,
            elaborated=err is None,
            elapsed_ms=elapsed_ms,
        )
        if err is None:
            row.errors = sum(1 for d in diags if d.is_error)
            row.warnings = sum(1 for d in diags if not d.is_error)
        summary.append(row)

        if err:
            print(f"      AST: failed to elaborate ({err[:60]})")
        else:
            errs = [d for d in diags if d.is_error]
            warns = [d for d in diags if not d.is_error]
            dep_note = f", +{len(deps)} dep tree(s)" if deps else ""
            print(f"      AST diagnostics: {len(errs)} error(s), "
                  f"{len(warns)} warning(s){dep_note}")
            for d in diags[:10]:
                tag = "ERR " if d.is_error else "warn"
                print(f"          {tag} L{d.line}: {d.message[:95]}")
            if len(diags) > 10:
                print(f"          ... and {len(diags)-10} more")
            ast_error_total += len(errs)
        print()

    print("-" * 60)
    print(f"total divergent macro references: {divergent_total}")
    print(f"total AST errors in opened files : {ast_error_total}")
    print()
    if resolve_macros:
        print("--resolve-macros: for each fragment that used a macro its own")
        print("compilation unit could not see, the defining header was looked")
        print("up in the index (library first) and injected, then the library")
        print("package imported. Divergence is therefore 0 by construction.")
        print()
        print("Any errors left are real: they are what a full build would also")
        print("report, not artefacts of elaborating a fragment out of context.")
    else:
        print("Divergent = hover works (index, depth 0) but diagnostics fail")
        print("(document, real includes). No include path fixes these: the file")
        print("is a fragment whose macros come from the including package.")
        print()
        print("AST errors that are NOT 'unknown macro' (undeclared identifiers,")
        print("unknown interfaces, bad assignments) are the second half of the")
        print("problem: the fragment has no enclosing package scope. A macro")
        print("library alone would not fix those.")
    elab_phase_ms = (time.perf_counter() - t_elab_phase) * 1000.0
    total_ms = (time.perf_counter() - t_start) * 1000.0
    per_doc_ms = sum(r.elapsed_ms for r in summary)

    elog.section("TIMING")
    elog.log(f"  crawl + index (Layer 1) : {index_ms:9.1f} ms  "
             f"({len(files)} files, {len(macro_to_files)} macros)")
    elog.log(f"  elaboration phase       : {elab_phase_ms:9.1f} ms  "
             f"({len(summary)} document(s))")
    elog.log(f"      of which in elaborate(): {per_doc_ms:9.1f} ms")
    elog.log(f"      harness overhead       : {elab_phase_ms - per_doc_ms:9.1f} ms")
    if cache is not None:
        elog.log(f"  library cache           : {cache.parse_seconds*1000:9.1f} ms parsing "
                 f"({cache.hits} hit, {cache.misses} miss)")
    elog.log(f"  TOTAL WALL TIME         : {total_ms:9.1f} ms")

    print()
    print(f"total: {total_ms:.0f} ms "
          f"(index {index_ms:.0f} ms, elaborate {elab_phase_ms:.0f} ms)")

    if log_path is not None:
        if cache is not None:
            elog.section("LIBRARY CACHE (pre-parsed trees)")
            elog.log(f"  {cache.stats()}")
            elog.log("  cached: parsed SyntaxTrees for dependency files")
            elog.log("  NOT cached: ast::Compilation -- slang finalizes it on first")
            elog.log("  elaboration, so each document still needs its own.")
        write_summary(elog, summary, macro_to_files, symbol_to_file, files)
        elog.write(log_path)
        print()
        print(f"elaboration log written to {log_path}")
    return 0


def write_summary(
    elog: "ElabLog",
    summary: list[FileSummary],
    macro_to_files: dict[str, list[Path]],
    symbol_to_file: dict[str, Path],
    files: list[Path],
) -> None:
    """Append the end-of-log summary covering only non-library (non-UVM) files."""
    elog.section("SUMMARY -- project files (library/UVM files excluded)")

    if not summary:
        elog.log("  (no files elaborated)")
        return

    # Size the name column to the longest path so nothing overflows.
    w = max(len("file"), max(len(r.path) for r in summary))
    hdr = (f"  {'file':<{w}} {'err':>4} {'warn':>5} {'used':>5} {'vis':>6} "
           f"{'div':>4} {'inc':>4} {'inc*':>5} {'deps':>5} {'tops':>5} {'ms':>7}")
    elog.log(hdr)
    elog.log("  " + "-" * (len(hdr) - 2))
    for r in summary:
        flag = "" if r.elaborated else "  <ELABORATION FAILED>"
        elog.log(
            f"  {r.path:<{w}} {r.errors:>4} {r.warnings:>5} {r.macros_used:>5} "
            f"{r.macros_visible:>6} {r.macros_divergent:>4} {r.includes_direct:>4} "
            f"{r.includes_total:>5} {r.deps:>5} {r.top_instances:>5} "
            f"{r.elapsed_ms:>7.1f}{flag}"
        )

    tot_err = sum(r.errors for r in summary)
    tot_warn = sum(r.warnings for r in summary)
    tot_div = sum(r.macros_divergent for r in summary)
    elog.log("  " + "-" * (len(hdr) - 2))
    elog.log(f"  {'TOTAL':<{w}} {tot_err:>4} {tot_warn:>5} "
             f"{sum(r.macros_used for r in summary):>5} {'':>6} {tot_div:>4}")

    elog.log("")
    elog.log("  columns")
    elog.log("    err/warn : diagnostics the server would publish for this file")
    elog.log("    used     : `macro references written in the file")
    elog.log("    vis      : macros its own compilation unit can see")
    elog.log("    div      : divergent -- hoverable via the index, not elaborable")
    elog.log("    inc      : `include directives written in the file")
    elog.log("    inc*     : files actually pulled in, transitively")
    elog.log("    deps     : dependency trees added via the index (getDependentTrees)")
    elog.log("    tops     : top instances; 0 means analysis diags are discarded")
    elog.log("    ms       : wall time to elaborate this document")

    # Project-wide index totals, excluding anything under a waived path.
    proj_files = [f for f in files if not is_waived(str(f))]
    proj_macros = {m for m, srcs in macro_to_files.items()
                   if any(not is_waived(str(s)) for s in srcs)}
    proj_syms = {n for n, src in symbol_to_file.items() if not is_waived(str(src))}
    elog.log("")
    elog.log("  project totals (excluding waived library paths)")
    elog.log(f"    files crawled  : {len(proj_files)} of {len(files)}")
    elog.log(f"    macros indexed : {len(proj_macros)} of {len(macro_to_files)}")
    elog.log(f"    symbols indexed: {len(proj_syms)} of {len(symbol_to_file)}")

    if tot_div:
        elog.log("")
        elog.log(f"  {tot_div} divergent macro reference(s): hover resolves them from the")
        elog.log("  index, elaboration does not. These are the `unknown macro' errors")
        elog.log("  in .svh fragments -- no include path fixes them (context.md).")
