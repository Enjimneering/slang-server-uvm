// UART testbench build file for slang-server.
//
// NOTE: paths are relative to the REPO ROOT (where slang-server is invoked),
// not to this file's directory.

// UVM library include path (uvm_macros.svh and the macros/ tree).
-I tests/data/uvm_support/uvm/src

// UVC and testbench include paths. The package `include-s its class files by
// bare name, so every directory holding a .svh must be on the include path.
-I tests/data/uvm_support/uart_tb/dut
-I tests/data/uvm_support/uart_tb/testbench
-I tests/data/uvm_support/uart_tb/uvc
-I tests/data/uvm_support/uart_tb/uvc/uart_tx
-I tests/data/uvm_support/uart_tb/uvc/uart_rx

// UVM's DPI layer needs a compiled C library; the server only elaborates.
-D UVM_NO_DPI

// The UVM base library.
tests/data/uvm_support/uvm/src/uvm_pkg.sv

// RTL
tests/data/uvm_support/uart_tb/dut/uart_if.sv
tests/data/uvm_support/uart_tb/dut/uart_tx.sv
tests/data/uvm_support/uart_tb/dut/uart_rx.sv

// Compilation roots. Everything else arrives through `include:
//   uart_pkg.sv   -> config, seq_item, sequencer, seq, driver, monitors,
//                    agents, env
//   testbench.sv  -> uart_test.svh
tests/data/uvm_support/uart_tb/uart_pkg.sv
tests/data/uvm_support/uart_tb/testbench.sv
