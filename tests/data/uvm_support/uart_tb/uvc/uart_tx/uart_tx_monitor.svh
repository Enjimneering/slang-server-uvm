class uart_tx_monitor extends uvm_monitor;
  
  `uvm_component_utils(uart_tx_monitor)
  
  uvm_analysis_port #(tx_seq_item) ap;
  virtual uart_if.tx vif;
  uart_config cfg;
  int CLKS_PER_BIT;
  
  function new (string name = "", uvm_component parent = null);
    super.new(name,parent);
  endfunction
  
  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    ap = new("ap", this);
    if(!uvm_config_db #(uart_config)::get(this, "","cfg", cfg))
      `uvm_error("NOCONFIG","config not set for tx_monitor component")
    CLKS_PER_BIT = cfg.CLKS_PER_BIT;
  endfunction
  
  function void connect_phase( uvm_phase phase);
    super.connect_phase(phase);
    vif = cfg.vif;
  endfunction
  
  task run_phase( uvm_phase phase);
    
      tx_seq_item txn, txn_clone;
      reg [7:0] tx_mon;
      logic start_bit, stop_bit;
      int i = 0;
      txn = tx_seq_item::type_id::create("txn");
    forever @(posedge vif.i_Clock) begin
        if (vif.o_Tx_Active == 1) begin
          if(i== 9) begin
            stop_bit = vif.o_Tx_Serial;
          end
          else if (i == 1) begin
            for (int j=0; j<=8 ; j++) begin
               tx_mon[j] = vif.o_Tx_Serial;
               cfg.wait_for_clock(CLKS_PER_BIT-1);
               i++;
            end
          end
          else if (i == 0) begin
            start_bit = vif.o_Tx_Serial;
            i++;
            cfg.wait_for_clock(CLKS_PER_BIT-1);
          end
        end
        else begin // active =0
          if(i>9) begin
            txn.data = tx_mon;
            i = 0;
          end
        end // active == 1
        $cast(txn_clone, txn.clone());
        ap.write(txn_clone);
        
    end
  endtask
endclass
              
        
        
        
        
