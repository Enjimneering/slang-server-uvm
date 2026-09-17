class uart_seq extends uvm_sequence #(tx_seq_item);
  `uvm_object_utils(uart_seq)
  //`uvm_declare_p_sequencer(uart_sequencer)
  
  uart_config cfg;
  tx_seq_item txn;
  
  function new (string name = "uart_seq");
    super.new(name);
  endfunction
  
  task body;
    if (!uvm_config_db #(uart_config)::get(null, get_full_name(), "cfg",cfg)) 
      `uvm_error("SEQ Body ","uart config not found")
    txn = tx_seq_item::type_id::create("txn");
    start_item(txn);
    void'(txn.randomize() with { txn.dv == 1; });
    txn.print();
    finish_item(txn);
    
//    cfg.wait_for_tx_done();
    
  endtask: body
  
endclass: uart_seq
