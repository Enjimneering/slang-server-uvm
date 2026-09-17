"""Static pyslang model of slang-server, split to mirror the C++ sources.

  Config.py                    <- src/Config.cpp
  Indexer.py                   <- src/Indexer.cpp
  ServerDriver.py              <- src/ServerDriver.cpp
  ServerDiagClient.py          <- src/ServerDiagClient.cpp
  SlangServer.py               <- src/SlangServer.cpp
  document/SlangDoc.py         <- src/document/SlangDoc.cpp
  document/ShallowAnalysis.py  <- src/document/ShallowAnalysis.cpp
  document/SyntaxIndexer.py    <- src/document/SyntaxIndexer.cpp

No C++ twin (model-only, or proposed behaviour):
  SlangOptions.py   shared pyslang Bag/SourceManager plumbing
  Types.py          AstDiag / FileSummary
  ElabLog.py        the --log trace
  LibraryCache.py   pre-parsed library trees (the PCH proposal)
  MacroResolver.py  --resolve-macros (the proposed server change)
"""
