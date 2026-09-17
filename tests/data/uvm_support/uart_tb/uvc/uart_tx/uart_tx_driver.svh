class uart_tx_driver extends uvm_driver #(tx_seq_item);
  
  `uvm_component_utils(uart_tx_driver)
  
  virtual uart_if vif;
  uart_config cfg;
  
  tx_seq_item txn;
  int delay;
  
  function new (string name = "uart_tx_driver", uvm_component parent = null);
    super.new(name, parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if(cfg == null) begin
      if (!uvm_config_db #(uart_config)::get(this,"","cfg",cfg)) begin
        `uvm_error("NOCONFIG","config not set for tx_driver component")
      end
    end  
    delay = cfg.delay;
   endfunction: build_phase
  
  function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
//    if(!uvm_config_db #(virtual uart_if)::get(this,"","vif",cfg.vif)) 
//      `uvm_error("NOVIF",{"virtual interface not set for: ",get_full_name(),".vif"})
    vif = cfg.vif;
  endfunction: connect_phase
  
  task run_phase(uvm_phase phase);
    initialize();
    @(posedge vif.i_Clock);
    
    send_frame();
    
  endtask: run_phase
  
  task initialize();
    `uvm_info(get_type_name(), "Initializing", UVM_MEDIUM)
    vif.i_Tx_DV <= 0;
    vif.i_Tx_Byte <= 'h0;
    vif.i_Rx_Serial <= 1;
  endtask
  
  task send_frame();
    `uvm_info(get_type_name(), "Sending Frame", UVM_MEDIUM)
    @(posedge vif.i_Clock);
    //forever begin 
    
      seq_item_port.get_next_item(txn);
      void'(txn.randomize());
      vif.i_Tx_DV <= 1;
      vif.i_Tx_Byte <= txn.data;
      @(posedge vif.i_Clock);
      vif.i_Tx_DV <= 0;
      cfg.wait_for_tx_done();
      
      `uvm_info(get_type_name(), "Frame TX Done", UVM_MEDIUM)
       //txn.done = vif.o_Tx_Done;
      `uvm_info(get_type_name(),txn.convert2string(), UVM_MEDIUM)
      seq_item_port.item_done();
      //cfg.wait_for_clock(20);
     @(posedge vif.i_Clock);
    
    //end
  endtask: send_frame
  
endclass        
