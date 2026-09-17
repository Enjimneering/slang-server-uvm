// Code your testbench here
// or browse Examples
`timescale 1ns/10ps

// uart_test.svh (included below) uses `uvm_* macros, so the macro header must
// be preprocessed before it.
`include "uvm_macros.svh"

module top_tb;
  import uvm_pkg::*;
  import uart_pkg::*;

  `include "uart_test.svh"
  
  parameter CLKS_PER_BIT = 2; //87;
  reg clk;
  
  uart_if uif(.i_Clock(clk));
  
  uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) tx (uif.tx);
  uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) rx (uif.rx);
  
  initial begin
    $monitor("@%0t clk:%0h, TX Bus Data:%0h, Tx_Frame:%b, Tx_DV:%0h, Tx_Active:%0b, Tx_Done:%0h",$time, clk, uif.i_Tx_Byte, uif.o_Tx_Serial, uif.i_Tx_DV, uif.o_Tx_Active, uif.o_Tx_Done);
    $dumpfile("dump.vcd");
    $dumpvars;
    uvm_config_db #(virtual uart_if)::set( null, "uvm_test_top", "vif", uif);
    run_test();
  end
  
  initial begin
    clk = 0;
    //reset = 1;
    #5;
    //reset = 0;
    forever begin
      #50 clk = ~clk;
    end
  end
endmodule
    
  
