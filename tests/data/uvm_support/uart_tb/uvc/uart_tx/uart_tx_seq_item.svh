class tx_seq_item extends uvm_sequence_item;
  
  `uvm_object_utils(tx_seq_item)
  
  //Data Members
  rand logic dv;
  rand logic [7:0] data;
  
  //response
  //logic active;
  logic done;
  
  constraint dv_c { dv == 1;}
  
  function new(string name = "tx_seq_item");
    super.new(name);
  endfunction
  
  function void do_copy(uvm_object rhs);
    tx_seq_item rhs_;
    
    if(!$cast(rhs_,rhs))begin
      `uvm_fatal("do_copy", "object cast failed")
    end
    super.do_copy(rhs);
    dv = rhs_.dv;
    data = rhs_.data;
    //active = rhs_.active;
    done = rhs_.done;
  endfunction:do_copy
  
  function bit do_compare(uvm_object rhs, uvm_comparer comparer);
    tx_seq_item rhs_;
    
    if(!$cast(rhs_,rhs))begin
      `uvm_error("do_compare","cast of rhs failed")
      return 0;
    end
    return super.do_compare(rhs, comparer) &&
    	dv == rhs_.dv &&
    	data == rhs_.data  &&
    	//active == rhs_.active &&
    	done == rhs_.done;
  endfunction:do_compare
  
  function string convert2string();
    string s;
    
    $sformat(s, "%s\n", super.convert2string());
    $sformat(s, "%s dv\t%0b\n tx data\t%0h\n tx done\t%0b\n", s, dv, data, done);
    return s;
  endfunction:convert2string
  
  function void do_print(uvm_printer printer);
    if(printer.knobs.sprint == 0) begin
      $display(convert2string);
    end
    else begin
      printer.m_string = convert2string();
    end
  endfunction:do_print
  
  function void do_record(uvm_recorder recorder);
    super.do_record(recorder);
    `uvm_record_field("data", data)
  endfunction:do_record
endclass
    
