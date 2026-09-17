In UVM, this is a common pattern:

package my_pkg;
  `include "src/some_class.svh"
  `include "src/some_types.svh"
  ...
endpackage

To properly show diags and other info for the svh files in this compilation unit, we need to make note of this pattern. One heuristic we can use is the local includes found during indexing, and then map src/some_class.svh back to the pkg's syntax tree. This will require some changes with document management in the server driver, since right now there's a 1-1 assumption for documents, syntax trees, and shallow analysis.

Another big issue is the sheer size of the uvm includes, which cause excessive delays in lsp requests. More info in the follow up comment.


I have a draft for having the relevant documents share a shallow compilation for the package, but the file expansion work for uvm_macros.svh really bogs down the server. There's a couple solutions that should both eventually be implemented to make this usable:

Pre-compiled headers. A more accurate name for what would be implemented with slang is pre-parsed headers- macros dumped, and cst nodes copied and grafted on. These would be keyed by file + either used defines, or the entire define map.
Request cancellation, threaded analysis. New onChange requests would cancel older ones in progress/queued. This would also be really nice for server compilations, which can already lag the server.
evanwporter commented on Feb 14
@evanwporter
evanwporter
on Feb 14
Contributor
Regarding the PCHs, would this be something new that is developed? Or does it already exist in slang? If it's the former, how would it be serialized (ie: as binary or JSON)? Either way it would probably require a lot of wrapper code arounds slang to enable reflection (if going that route).

AndrewNolte commented on Jun 15
@AndrewNolte
AndrewNolte
on Jun 15
Collaborator
Author
PCH doesn't need a serialization format - it can just live in memory, and would be integrated in slang's source manager / parser stack. Not sure what you mean with the reflection comment.

evanwporter commented on Jun 16
@evanwporter
evanwporter
on Jun 16 via email
Contributor
Yeah this is outdated lol. I wasn’t as familiar with slang as I am now.
…
dpetrisko commented on Jul 24
@dpetrisko
dpetrisko
on Jul 24
Hi, is there any known workaround? Maybe specifying the class files in a build file or something else? I'm seeing an error in the vs-code extension, but I'm fairly sure it's coming from slang-server, not the plugin (please correct me and I can open an issue on the plugin repo instead!)

my_uvm_pkg.sv

package my_uvm_pkg;
`include "my_monitor.svh"
endpackage
my_bfm_if.sv

interface my_bfm_if (input clk, input reset);
endinterface
my_monitor.svh

`include "uvm_macros.svh"

class my_monitor extends uvm_monitor;
  `uvm_component_utils(my_monitor)
  virtual my_bfm_if bfm; // <- slang-server error: unknown interface 'my_bfm_if'
endclass
Interestingly, when I hover over the error, it actually seems to be finding the interface in the tree, since it lists the ports correctly

Image
mumblingdrunkard commented on Aug 10
@mumblingdrunkard
mumblingdrunkard
on Aug 10
@dpetrisko What I've ended up doing is to follow a certain convention:

// src/my_if.sv
`ifndef _MY_IF_SV_
`define _MY_IF_SV_

interface my_if (input clk, input reset);
endinterface

`endif

// src/my_uvm_pkg.sv
`ifndef _MY_UVM_PKG_SV_
`define _MY_UVM_PKG_SV_

package my_uvm_pkg;
  `include "uvm_macros.svh"
  import uvm_pkg::*;

  `define IN_PKG_SV

  `include "my_monitor.svh"

  `undef IN_PKG_SV
endpackage

`endif

// src/my_monitor.svh
`ifndef _MY_MONITOR_SVH_
`define _MY_MONITOR_SVH_

`ifndef IN_PKG_SV
  `include "uvm_macros.svh"
  import uvm_pkg::*;

  // special includes
  `include "my_if.sv"
`endif

class my_monitor extends uvm_monitor;
  `uvm_component_utils(my_monitor)

  virtual my_if vif_my_if;
  
  function new(string name, uvm_component parent);
    super.new(name, component);
  endfunction
endclass

`endif
With this setup, I find slang-server generally provides good support and does not give me red squiggly lines everywhere.

It works okay-ish, but has definite room for improvement.

