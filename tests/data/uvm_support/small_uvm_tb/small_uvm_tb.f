// UVM include path and compilation roots for slang-server.
//
// NOTE: paths here are relative to the REPO ROOT (where slang-server is
// invoked), not to this file's directory. slang resolves command-file paths
// against the working directory, so keep the tests/data/uvm_support/ prefix
// even though this file lives inside that directory.

// Include path: uvm_macros.svh and the macros/ tree live here.
-I tests/data/uvm_support/uvm/src
-I tests/data/uvm_support/small_uvm_tb

// UVM's DPI layer needs a compiled C library; the server only needs to elaborate.
-D UVM_NO_DPI

// The UVM base library.
tests/data/uvm_support/uvm/src/uvm_pkg.sv

// Testbench compilation roots. Order does not matter to slang.
//
// Only the two .sv roots are listed. Everything else reaches the compilation
// through my_testbench_pkg.sv, which `include-s my_sequence.svh, my_driver.svh
// and dut.svh. Listing any of those here as well would define their classes
// (and the dut/dut_if design units) twice.
tests/data/uvm_support/small_uvm_tb/my_testbench_pkg.sv
tests/data/uvm_support/small_uvm_tb/tb.sv
