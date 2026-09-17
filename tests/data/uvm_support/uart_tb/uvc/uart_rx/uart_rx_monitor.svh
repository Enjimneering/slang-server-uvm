class uart_rx_monitor extends uvm_monitor;
  
  `uvm_component_utils(uart_rx_monitor)
  
  uvm_analysis_port #(tx_seq_item) ap;
  virtual uart_if vif;
  uart_config cfg;
  //int CLKS_PER_BIT;
  
  function new (string name = "", uvm_component parent = null);
    super.new(name,parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    ap = new("ap", this);
    if(!uvm_config_db #(uart_config)::get(this, "","cfg", cfg))
      `uvm_error("NOCONFIG","config not set for rx_monitor component")
    
  endfunction
  
  function void connect_phase( uvm_phase phase);
    super.connect_phase(phase);
    vif = cfg.vif;
    
  endfunction
  
  task run_phase(uvm_phase phase);
//    tx_seq_item rxn, rxn_c;
    
//    rxn = tx_seq_item::type_id::create("rxn");
    
//    forever begin
//      @(posedge vif.i_Clock);
//      if(vif.o_Rx_DV == 1) begin
//        rxn.data <= vif.o_Rx_Byte;
//        @(posedge vif.i_Clock);
//        $cast(rxn_c, rxn.clone());
//        ap.write(rxn_c);
//      end
//    end
  endtask
endclass
