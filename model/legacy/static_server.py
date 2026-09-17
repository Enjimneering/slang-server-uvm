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

The interesting output is the DIVERGENCE between them: macros a file can hover
but cannot elaborate. That set is exactly the `unknown macro` diagnostics.

Usage:
    python model/uvm.py <repo-root> [--config .slang/server.json] [--open FILE]...
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pyslang as ps
except ImportError:
    sys.exit("pyslang not installed:  pip install pyslang")

# Mirrors Indexer.cpp:367-368
SV_EXTS = {".sv", ".svh", ".v", ".vh"}

# Mirrors Indexer.cpp:91 -- the single line that defines index behaviour.
INDEX_MAX_INCLUDE_DEPTH = 0
DOC_MAX_INCLUDE_DEPTH = 32

# ---------------------------------------------------------------- config
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

# ---------------------------------------------------------------- crawl

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


# ---------------------------------------------------------------- parsing


def _build_opts(depth: int, defines: list[str]) -> ps.Bag:
    opts = ps.Bag()
    po = ps.parsing.PreprocessorOptions()
    po.maxIncludeDepth = depth
    for d in defines:
        po.predefines.append(d)
    opts.preprocessorOptions = po
    return opts


def _source_manager(incs: list[str]) -> ps.SourceManager:
    """Include dirs live on the SourceManager, NOT on PreprocessorOptions.

    pyslang exposes PreprocessorOptions.additionalIncludePaths as a plain list
    *copy*, so appending to it silently does nothing. addUserDirectories is the
    working path; getting this wrong makes every include fail to resolve.
    """
    sm = ps.SourceManager()
    for inc in incs:
        sm.addUserDirectories(inc)
    return sm


def _compilation_opts(opts: ps.Bag) -> ps.Bag:
    """Mirror ShallowAnalysis.cpp:97-106 compilation setup exactly.

    The C++ sets AllowTopLevelIfacePorts, CheckUninstantiated, AllowInvalidTop,
    maxInstanceDepth=3 and topModules.clear(). pyslang 11.0.0 does not expose
    CheckUninstantiated or AllowInvalidTop, but both only ADD checking of
    uninstantiated code / permit invalid tops -- they do not suppress
    diagnostics, so omitting them matches the server's output on this fixture.

    Do NOT add IgnoreUnknownModules or LintMode: the C++ sets neither, and
    each silences the unknown-module/undeclared-identifier errors that are
    the whole point of modelling a fragment with no package scope.
    """
    co = ps.ast.CompilationOptions()
    co.flags |= ps.ast.CompilationFlags.AllowTopLevelIfacePorts
    co.maxInstanceDepth = 3  # ShallowAnalysis.cpp:103
    co.topModules.clear()  # ShallowAnalysis.cpp:106
    co.errorLimit = 0  # do not truncate
    opts.compilationOptions = co
    return opts


# Analysis diags the server drops because a shallow compilation lacks the
# references that would justify them (ShallowAnalysis.cpp:1154).
_FILTERED_DIAGS = {
    "UnusedDefinition", "UnusedPackageParameter", "UnusedPackageSubroutine",
    "UnusedPackageTypedef", "UnusedPackageVar",
}


@dataclass
class FileSummary:
    """One row of the end-of-log summary for a non-library file."""

    path: str
    errors: int = 0
    warnings: int = 0
    macros_used: int = 0        # `macro references written in the file
    macros_visible: int = 0     # macros its own compilation unit can see
    macros_divergent: int = 0   # hoverable via the index, but not elaborable
    includes_direct: int = 0    # `include directives written in the file
    includes_total: int = 0     # files actually pulled in, transitively
    deps: int = 0               # dependency trees added via the index
    top_instances: int = 0
    elaborated: bool = True


@dataclass
class AstDiag:
    is_error: bool
    code: str
    message: str
    line: int
    file: str


# Path fragments treated as third-party library code. Diagnostics inside these
# are waived: UVM ships with ~1000 slang findings (sign conversions, implicit
# bool casts, incomplete returns) that are real but not the user's to fix, and
# they drown out the handful of findings in the testbench.
#
# The server gets this for free by publishing per-URI -- you never open a UVM
# file, so you never see them. The model compiles dependencies into the same
# Compilation, so it has to waive them explicitly.
WAIVED_PATH_PARTS: list[str] = ["/uvm/src/", "/uvm/compat/", "/uvm/deprecated/"]


def normalize_message(msg: str) -> str:
    """Match the C++ client's rendering of nested "(aka ...)" type aliases.

    slang-server publishes ReportedDiagnostic::formattedMessage built by the
    pinned slang fork (external/slang -> AndrewNolte/slang). pyslang ships
    upstream slang 11.0.0, whose formatter quotes a type alias even when it is
    already nested inside a quoted type:

        server:  (aka 'uvm_driver#(my_transaction,REQ (aka my_transaction))')
        pyslang: (aka 'uvm_driver#(my_transaction,REQ (aka 'my_transaction'))')

    Same diagnostic, same location, same code -- only the inner quoting differs.
    Strip quotes from any "(aka 'X')" at nesting depth > 1 so messages compare
    equal against the server. Outer (depth-1) aliases keep their quotes.
    """
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(msg):
        if msg.startswith("(aka ", i):
            depth += 1
            out.append("(aka ")
            i += 5
            if depth > 1 and i < len(msg) and msg[i] == "'":
                j = msg.find("'", i + 1)
                if j != -1:
                    out.append(msg[i + 1:j])
                    i = j + 1
                    continue
            continue
        if msg[i] == ")" and depth > 0:
            depth -= 1
        out.append(msg[i])
        i += 1
    return "".join(out)


def count_direct_includes(path: Path) -> int:
    """`include directives written in this file (not transitively pulled in)."""
    try:
        src = path.read_text(errors="replace")
    except OSError:
        return 0
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return len(re.findall(r'`include\s+"[^"]+"', src))


def is_waived(filename: str) -> bool:
    """True if `filename` is third-party library code whose diags we ignore."""
    if not filename:
        return False
    norm = str(Path(filename).as_posix())
    return any(part in norm for part in WAIVED_PATH_PARTS)


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


def elaborate(
    path: Path,
    incs: list[str],
    defines: list[str],
    deps: list[Path] | None = None,
    log: "ElabLog | None" = None,
) -> tuple[list[AstDiag], str | None]:
    """Build a shallow Compilation for one document and collect its diagnostics.

    `deps` stands in for ServerDriver::getDependentTrees -- extra trees added to
    the same compilation so the file can resolve names it does not declare.
    Only diagnostics landing in `path`'s own buffer are returned, matching the
    server, which publishes per-URI.
    """
    log = log or ElabLog()
    sm = _source_manager(incs)
    opts = _compilation_opts(_build_opts(DOC_MAX_INCLUDE_DEPTH, defines))
    try:
        comp = ps.ast.Compilation(opts)
        main_tree = ps.syntax.SyntaxTree.fromFile(str(path), sm, opts)
        if isinstance(main_tree, tuple):
            main_tree = main_tree[0]
        comp.addSyntaxTree(main_tree)
        log.log(f"  tree[0] (document) {path}")
        for i, d in enumerate(deps or [], start=1):
            if not d.is_file():
                log.log(f"  tree[{i}] SKIPPED (missing) {d}")
                continue
            t = ps.syntax.SyntaxTree.fromFile(str(d), sm, opts)
            if isinstance(t, tuple):
                t = t[0]
            comp.addSyntaxTree(t)
            log.log(f"  tree[{i}] (dependency) {d}")

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
    for d in diags:
        code = str(d.code).replace("DiagCode(", "").rstrip(")")
        if code in _FILTERED_DIAGS:
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
        # Only report diagnostics in the open document's own file.
        if Path(fname).name != Path(target).name:
            n_other_file += 1
            continue
        try:
            msg = normalize_message(engine.formatMessage(d))
        except Exception:
            msg = code
        out.append(AstDiag(d.isError, code, msg, line, fname))

    log.log(f"  dropped: {n_filtered} by _FILTERED_DIAGS, "
            f"{n_waived} waived (library), {n_other_file} in other files")
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


def _iter_tokens(node):
    """Yield every token under a syntax node (tokens carry the trivia)."""
    if hasattr(node, "trivia"):
        yield node
        return
    try:
        n = len(node)
    except TypeError:
        return
    for i in range(n):
        child = node[i]
        if child is not None:
            yield from _iter_tokens(child)


@dataclass
class ParseResult:
    defines: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    unknown_macros: list[str] = field(default_factory=list)
    error: str | None = None


def parse_file(path: Path, depth: int, incs: list[str], defines: list[str]) -> ParseResult:
    """Preprocess+parse one file, pulling out everything both layers care about."""
    res = ParseResult()
    try:
        tree = ps.syntax.SyntaxTree.fromFile(
            str(path), _source_manager(incs), _build_opts(depth, defines)
        )
    except Exception as e:  # unreadable / encoding
        res.error = str(e)
        return res
    if isinstance(tree, tuple):  # pyslang returns (tree, diags) in some builds
        tree = tree[0]

    # `define / `include live in token trivia, not as tree nodes.
    for tok in _iter_tokens(tree.root):
        for tv in tok.trivia:
            if tv.kind != ps.parsing.TriviaKind.Directive:
                continue
            syn = tv.syntax()
            if syn is None:
                continue
            if syn.kind == ps.syntax.SyntaxKind.DefineDirective:
                res.defines.append(syn.name.valueText)
            elif syn.kind == ps.syntax.SyntaxKind.IncludeDirective:
                res.includes.append(syn.fileName.valueText)

    # Top-level declarations, mirroring extractFromRoot()
    root = tree.root
    try:
        members = root.members
    except AttributeError:
        members = []
    for m in members:
        k = str(getattr(m, "kind", ""))
        # Modules/packages carry their name on .header; classes carry it directly.
        hdr = getattr(m, "header", None)
        if hdr is not None and hasattr(hdr, "name"):
            name = hdr.name.valueText
        elif hasattr(m, "name"):
            name = m.name.valueText
        else:
            name = None
        if not name:
            continue
        # slang gives interfaces/programs their own SyntaxKind, but they are all
        # "definitions" as far as the index is concerned -- extractFromRoot()
        # records any ModuleDeclarationSyntax, and interface/program/package
        # all derive from it in the C++ AST.
        if "PackageDeclaration" in k:
            res.packages.append(name)
        elif "ClassDeclaration" in k:
            res.classes.append(name)
        elif any(t in k for t in ("ModuleDeclaration", "InterfaceDeclaration",
                                  "ProgramDeclaration")):
            res.modules.append(name)

    # Unknown macros surface as diagnostics from the preprocessor.
    for d in tree.diagnostics:
        txt = str(d.code)
        if "UnknownDirective" in txt or "UnknownMacro" in txt:
            res.unknown_macros.append(txt)
    return res


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
        if _includes(target, me):
            continue
        deps.append(target)
    return deps


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


# ---------------------------------------------------------------- model


def run(root: Path, config_path: Path | None, open_files: list[str],
        log_path: Path | None = None) -> int:
    flags, cfg = load_config(root, config_path)
    incs = [str((root / i).resolve()) for i in flags.include_dirs]

    print(f"repo root   : {root}")
    print(f"include dirs: {incs or '(none)'}")
    print(f"defines     : {flags.defines or '(none)'}")
    print()

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
    print(f"  files dropped by the class heuristic (Indexer.cpp:117): "
          f"{len(skipped_by_heuristic)}")
    for f in skipped_by_heuristic[:10]:
        print(f"      {f.relative_to(root)}")
    if len(skipped_by_heuristic) > 10:
        print(f"      ... and {len(skipped_by_heuristic)-10} more")
    print()

    # ---- Layer 2: the document (real include path, includes followed) ----
    targets = (
        [Path(o) if Path(o).is_absolute() else root / o for o in open_files]
        if open_files
        else skipped_by_heuristic or files[:10]
    )

    elog = ElabLog()
    elog.enabled = log_path is not None
    elog.log("slang-server static model -- elaboration log")
    elog.log(f"repo root   : {root}")
    elog.log(f"include dirs: {incs}")
    elog.log(f"defines     : {flags.defines}")
    elog.log(f"waived paths: {WAIVED_PATH_PARTS}")
    elog.log(f"crawled     : {len(files)} files")
    elog.log(f"indexed     : {len(macro_to_files)} macros, {len(symbol_to_file)} symbols")

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
        diags, err = elaborate(f, incs, flags.defines, deps, log=elog)

        row = FileSummary(
            path=str(rel),
            macros_used=len(used),
            macros_visible=len(visible),
            macros_divergent=len(hoverable),
            includes_direct=count_direct_includes(f),
            includes_total=len(doc.includes),
            deps=len(deps),
            top_instances=elog.last_top_instances,
            elaborated=err is None,
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
    print("Divergent = hover works (index, depth 0) but diagnostics fail")
    print("(document, real includes). No include path fixes these: the file")
    print("is a fragment whose macros come from the including package.")
    print()
    print("AST errors that are NOT 'unknown macro' (undeclared identifiers,")
    print("unknown interfaces, bad assignments) are the second half of the")
    print("problem: the fragment has no enclosing package scope. A macro")
    print("library alone would not fix those.")
    if log_path is not None:
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
           f"{'div':>4} {'inc':>4} {'inc*':>5} {'deps':>5} {'tops':>5}")
    elog.log(hdr)
    elog.log("  " + "-" * (len(hdr) - 2))
    for r in summary:
        flag = "" if r.elaborated else "  <ELABORATION FAILED>"
        elog.log(
            f"  {r.path:<{w}} {r.errors:>4} {r.warnings:>5} {r.macros_used:>5} "
            f"{r.macros_visible:>6} {r.macros_divergent:>4} {r.includes_direct:>4} "
            f"{r.includes_total:>5} {r.deps:>5} {r.top_instances:>5}{flag}"
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

    a = ap.parse_args()
    root = a.root.resolve()
    if not root.is_dir():
        return print(f"not a directory: {root}") or 1
    if a.no_waivers:
        WAIVED_PATH_PARTS.clear()
    return run(root, a.config, a.open, a.log)


if __name__ == "__main__":
    raise SystemExit(main())
