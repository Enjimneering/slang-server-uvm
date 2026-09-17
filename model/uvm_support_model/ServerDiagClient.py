"""Mirrors src/ServerDiagClient.cpp -- turning slang diagnostics into published ones.

Covers the filtering the server applies before a diagnostic reaches the editor:
the unused-* drops from ShallowAnalysis.cpp:1154, the library (UVM) waivers,
and message formatting. normalize_message() reconciles pyslang's formatter with
the pinned slang fork the server links against.
"""

from __future__ import annotations

from pathlib import Path

_FILTERED_DIAGS = {
    "UnusedDefinition", "UnusedPackageParameter", "UnusedPackageSubroutine",
    "UnusedPackageTypedef", "UnusedPackageVar",
}

# Additional unused-* diags suppressed only in --resolve-macros mode. Once a
# macro like `uvm_component_utils expands, it generates methods (get_type,
# type_name, create) that nothing in the fragment calls. Reporting those as
# "unused" blames the user for code UVM wrote, so they are dropped alongside
# the server's own unused-* filter above.
_MACRO_EXPANSION_FILTERED = {
    "UnusedClassMethod", "UnusedConstructor", "UnusedArgument",
    "UnusedVariable", "UnusedButSetVariable", "UnusedTypedef",
}



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


def is_waived(filename: str) -> bool:
    """True if `filename` is third-party library code whose diags we ignore."""
    if not filename:
        return False
    norm = str(Path(filename).as_posix())
    return any(part in norm for part in WAIVED_PATH_PARTS)
