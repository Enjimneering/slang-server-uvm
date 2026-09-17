interface uart_if(
  input logic       i_Clock); //,
  
  logic       i_Tx_DV;
  logic [7:0] i_Tx_Byte; 
  logic       o_Tx_Active;
  logic 	  	o_Tx_Serial;
  logic      	o_Tx_Done;
  
  logic       i_Rx_Serial;
  logic       o_Rx_DV;
  logic [7:0] o_Rx_Byte;
  logic       loopback;
 
  modport tx (input i_Clock, i_Tx_DV, i_Tx_Byte,
              output o_Tx_Active, o_Tx_Serial, o_Tx_Done);
  
  modport rx (input i_Clock, .i_Rx_Serial(o_Tx_Serial),
              output o_Rx_DV, o_Rx_Byte);

endinterface
