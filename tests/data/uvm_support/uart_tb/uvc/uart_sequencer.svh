
class uart_sequencer extends uvm_sequencer #(tx_seq_item);
  
  virtual uart_if vif;
  uart_config cfg;
  
  `uvm_component_utils(uart_sequencer)
  
  function new (string name = "", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(cfg == null) 
      if (!uvm_config_db #(uart_config)::get(this, "", "cfg", cfg)) 
        `uvm_error("NOCONFIG", "uart_config not set for Uart Sequencer component")
        cfg = uart_config::type_id::create("cfg");
    
  endfunction: build_phase
  
endclass
