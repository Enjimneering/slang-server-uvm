// uart_env and friends come from uart_pkg, which testbench.sv imports
// before including this file. Do not re-include them here.

class uart_base_test extends uvm_test;

  
  `uvm_component_utils(uart_base_test)
  
  uart_env my_env;
  uart_config cfg;
  
  function new (string name = "uart_base_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    cfg = uart_config::type_id::create("cfg");
    //configure_env();
    uvm_config_db #(uart_config)::set(this, "*", "cfg", cfg);
    my_env = uart_env::type_id::create("my_env",this);
    if(!uvm_config_db #(virtual uart_if)::get(this,"","vif",cfg.vif))
      `uvm_fatal("uart_base_test","Can't read vif")
      uvm_config_db #(uart_config)::set(this,"*","uart_config",cfg);
    
  endfunction
  
endclass

class frame_test extends uart_base_test;
  `uvm_component_utils(frame_test)
  
  uart_seq my_seq;
  //uart_env my_env;
  
  function new (string name = "frame_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
  endfunction
  
  task run_phase(uvm_phase phase);
    my_seq = uart_seq::type_id::create("my_seq");
    phase.raise_objection(this, "Starting Uart Frame Sequence");
    my_seq.start(my_env.tx_agent.tx_sequencer);
    phase.drop_objection(this, "Finish Uart Sequence");
  endtask
endclass 
