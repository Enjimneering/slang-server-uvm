class uart_rx_agent extends uvm_component;
  
  `uvm_component_utils(uart_rx_agent)
  uart_config cfg;
  
  //components
  uvm_analysis_port #(tx_seq_item) ap;
  uart_rx_monitor rx_monitor;
  
  function new(string name= "uart_rx_agent", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    
    if( !uvm_config_db #(uart_config)::get(this,"", "cfg", cfg)) begin 
      `uvm_error("UART RX Agent Build_phase", "cfg not set for uart rx agent")
    end
    rx_monitor = uart_rx_monitor::type_id::create("rx_monitor", this);
        
  endfunction: build_phase
  
  function void connect_phase(uvm_phase phase);
    rx_monitor.vif = cfg.vif;
    ap = rx_monitor.ap;
        
  endfunction: connect_phase
endclass
