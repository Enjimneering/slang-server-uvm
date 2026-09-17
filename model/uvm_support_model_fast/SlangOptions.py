"""Shared pyslang option plumbing.

No single C++ twin: in slang-server these Bag/SourceManager setups are spread
across ServerDriver.cpp (driver options) and ShallowAnalysis.cpp (compilation
options). They are gathered here because every layer of the model needs them.
"""

from __future__ import annotations

import pyslang as ps

# Mirrors Indexer.cpp:367-368
SV_EXTS = {".sv", ".svh", ".v", ".vh"}

# Mirrors Indexer.cpp:91 -- the single line that defines index behaviour.
INDEX_MAX_INCLUDE_DEPTH = 0
DOC_MAX_INCLUDE_DEPTH = 32

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
