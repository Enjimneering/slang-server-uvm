class uart_env extends uvm_env;
  
  `uvm_component_utils(uart_env)
  
  uart_config cfg;
  uart_tx_agent tx_agent;
  uart_rx_agent rx_agent;
  
  //uart_scoreboard m_scoreboard;
  
  function new(string name = "uart_env",
               uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (cfg == null) begin
      if(!uvm_config_db #(uart_config)::get(this, "", "cfg", cfg)) begin 
      `uvm_fatal("build_phase", "unable to get uart_config")
      end
       cfg = uart_config::type_id::create("cfg",this);
    end
       
       uvm_config_db #(uart_config)::set(this,"tx_agent", "cfg", cfg);
       tx_agent = uart_tx_agent::type_id::create("tx_agent", this);
   
       uvm_config_db #(uart_config)::set(this,"rx_agent", "cfg", cfg);
       rx_agent = uart_rx_agent::type_id::create("rx_agent", this);

  endfunction: build_phase      
       
  function void connect_phase(uvm_phase phase);
    
   // if(cfg.has_uart_scoreboard) begin
      //m_uart_agent.ap.connect(m_scoreboard.analysis_export);
   // end
  endfunction: connect_phase
endclass    
