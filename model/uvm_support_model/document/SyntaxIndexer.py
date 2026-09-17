"""Mirrors src/document/SyntaxIndexer.cpp -- walking a parsed tree for facts.

Pulls `define directives out of token trivia and top-level declarations out of
the compilation unit. In slang a `define is trivia, not a tree node, so these
have to be recovered by walking every token's trivia list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pyslang as ps

from ..SlangOptions import _build_opts, _source_manager

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
