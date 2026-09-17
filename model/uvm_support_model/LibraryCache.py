"""Pre-parsed library trees -- the "pre-compiled headers" idea from context.md.

No C++ twin yet: this is the piece slang-server does not have. It would live
alongside ServerDriver's tree management. The class docstring records the hard
constraint found while building it -- slang finalizes an ast::Compilation on
first elaboration, so only SyntaxTrees can be shared, not compilations.
"""

from __future__ import annotations

import time
from pathlib import Path

import pyslang as ps

class LibraryCache:
    """Pre-parsed library trees, reused across documents.

    This is the modellable half of the "pre-compiled headers" idea in
    tests/data/uvm_support/context.md. What it does NOT do is as important as
    what it does, so both are spelled out here -- this class is meant to be
    ported to C++, and the constraints are what shape that port.

    WHAT IS CACHED
        The parsed SyntaxTree of a library file (uvm_pkg.sv and friends).
        Parsing uvm_pkg.sv costs ~345 ms cold; handing back the cached tree
        costs nothing. Measured on this fixture, per-document elaboration
        drops from ~614 ms to ~100-190 ms.

    WHAT IS NOT CACHED, AND WHY
        The ast::Compilation. slang finalizes a Compilation the first time it
        is elaborated -- addSyntaxTree() afterwards raises "The compilation has
        already been finalized". So each document still needs its own fresh
        Compilation; only the *trees* are shared. That is the single most
        important constraint for the C++ port: a cached Compilation is not
        possible without changes inside slang itself.

        This means ~1110 UVM diagnostics are still re-derived per document.
        Eliminating that is the second, much larger piece of work -- it needs
        slang to support either a frozen//shareable elaborated scope or an
        incremental Compilation. Caching trees is the part available today.

    CACHE KEY
        (resolved path, mtime_ns, sorted defines).

        Defines belong in the key even though they happen not to change the
        macro count on this fixture (UVM_NO_DPI / UVM_NO_DEPRECATED all yield
        510 macros in uvm_macros.svh): `ifdef can gate real content, and a key
        that ignores defines would silently return a tree built under the
        wrong configuration. context.md proposes exactly this -- "keyed by
        file + either used defines, or the entire define map". Using the whole
        define list is the conservative choice; narrowing it to *used* defines
        is a later optimisation that needs the preprocessor to report which
        defines a file actually consulted.

    THREAD SAFETY (for the C++ port)
        Reads dominate. A shared_mutex guarding the map, with trees held by
        shared_ptr, matches how Indexer.h already guards its index.
    """

    def __init__(self) -> None:
        self._trees: dict[tuple, object] = {}
        self.hits = 0
        self.misses = 0
        self.parse_seconds = 0.0

    @staticmethod
    def _key(path: Path, defines: list[str]) -> tuple:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return (str(path.resolve()), mtime, tuple(sorted(defines)))

    def get_tree(self, path: Path, sm: "ps.SourceManager", opts: "ps.Bag",
                 defines: list[str]):
        """Return a parsed tree for `path`, reusing a cached one when possible."""
        key = self._key(path, defines)
        cached = self._trees.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        t0 = time.perf_counter()
        tree = ps.syntax.SyntaxTree.fromFile(str(path), sm, opts)
        if isinstance(tree, tuple):
            tree = tree[0]
        self.parse_seconds += time.perf_counter() - t0
        self._trees[key] = tree
        return tree

    def stats(self) -> str:
        total = self.hits + self.misses
        rate = (100.0 * self.hits / total) if total else 0.0
        return (f"{self.hits} hit(s), {self.misses} miss(es), "
                f"{rate:.0f}% hit rate, {self.parse_seconds*1000:.1f} ms parsing")
