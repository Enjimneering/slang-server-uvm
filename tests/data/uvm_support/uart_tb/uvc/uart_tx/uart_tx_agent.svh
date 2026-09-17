class uart_tx_agent extends uvm_agent;
  
  `uvm_component_utils(uart_tx_agent)
  uart_config cfg;
  
  //components
  
  uart_tx_monitor tx_monitor;
  uart_sequencer tx_sequencer;
  uart_tx_driver tx_driver;
  uvm_analysis_port #(tx_seq_item) ap;
  
  function new(string name= "uart_tx_agent", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    ap = new("ap", this);
    if( !uvm_config_db #(uart_config)::get(this,"", "cfg", cfg)) begin
      `uvm_fatal("UART TX Agent Build_phase", "cfg not set for uart tx agent")
    end
    
    tx_monitor = uart_tx_monitor::type_id::create("tx_monitor", this);
    
    if(cfg.tx_active == UVM_ACTIVE) begin
      tx_driver = uart_tx_driver::type_id::create("tx_driver", this);
      tx_sequencer = uart_sequencer::type_id::create("tx_sequencer", this);
    end
  endfunction: build_phase
  
  function void connect_phase(uvm_phase phase);
    tx_monitor.vif = cfg.vif;
    ap = tx_monitor.ap;
    
    if(cfg.tx_active == UVM_ACTIVE) begin
      tx_driver.seq_item_port.connect(tx_sequencer.seq_item_export);
      tx_driver.vif = cfg.vif;
    end
  endfunction: connect_phase
endclass
