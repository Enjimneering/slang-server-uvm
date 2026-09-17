`ifndef UART_PKG_SV
`define UART_PKG_SV

// uvm_macros.svh must be preprocessed BEFORE any file that uses `uvm_*_utils.
// Including it inside (or after) the class files leaves those macros undefined
// at the point of use, which silently skips factory registration.
`include "uvm_macros.svh"

package uart_pkg;
  import uvm_pkg::*;
  // Order matters: each file may only reference types already declared above it.
  `include "uart_config.svh"
  `include "uart_tx_seq_item.svh"
  `include "uart_sequencer.svh"   // uses tx_seq_item, uart_config
  `include "uart_seq.svh"         // uses tx_seq_item, uart_config
  `include "uart_tx_driver.svh"
  `include "uart_tx_monitor.svh"
  `include "uart_tx_agent.svh"    // uses uart_sequencer, driver, monitor
  `include "uart_rx_monitor.svh"
  `include "uart_rx_agent.svh"
  `include "uart_env.svh"         // uses both agents
endpackage
`endif
