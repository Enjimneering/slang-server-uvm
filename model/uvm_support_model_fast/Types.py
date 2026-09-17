"""Small shared dataclasses.

AstDiag is this model's stand-in for a published lsp::Diagnostic; FileSummary
has no C++ twin -- it backs the end-of-log report that the model adds on top.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    elapsed_ms: float = 0.0


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