class uart_config extends uvm_object;
  `uvm_object_utils(uart_config)
  
  virtual uart_if vif;
  int CLKS_PER_BIT = 2; // 87
  int num_bits = 8;
  int delay = num_bits*CLKS_PER_BIT;
  
  uvm_active_passive_enum tx_active = UVM_ACTIVE;
  uvm_active_passive_enum rx_active = UVM_PASSIVE;
  
  function new (string name = "uart_config");
    super.new(name);
  endfunction: new
  
  // wait for clock
  task wait_for_clock(int m = 1);
    repeat (m) begin
      @(posedge vif.i_Clock);
    end
  endtask: wait_for_clock
  
  //wait for TX done
  task wait_for_tx_done;
    @(posedge vif.o_Tx_Done);
  endtask: wait_for_tx_done
      
endclass
  
