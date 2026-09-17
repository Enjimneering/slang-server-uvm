"""Mirrors src/document/SlangDoc.cpp -- one file/SyntaxTree pair.

SlangDoc.cpp:96 getSyntaxTree() parses an open document with the real include
path from `flags`, following includes for real -- the crucial contrast with the
Indexer's maxIncludeDepth=0. In the C++ this is a class holding the buffer, the
tree and a cached ShallowAnalysis; the model has no long-lived document state,
so the parsing lives in document/SyntaxIndexer.py (parse_file) and the analysis
in document/ShallowAnalysis.py (elaborate).

This module records that mapping rather than duplicating either.
"""

from __future__ import annotations

from .ShallowAnalysis import elaborate
from .SyntaxIndexer import ParseResult, parse_file

__all__ = ["parse_file", "ParseResult", "elaborate"]
