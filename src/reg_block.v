module reg_block #(
        parameter [7:0] BASE_ADDR = 8'h00,
        parameter       N_REGS    = 16
) (
        input wire         clk,
        input wire         N_RST,

        input  wire [7:0]  reg_addr,
        input  wire [7:0]  data_in,
        output wire [7:0]  data_out,
        input wire         reg_write
);
    

//---------------------------------------------------------------------------------
//-------------------------------- Adress decoding --------------------------------
//---------------------------------------------------------------------------------
wire selected = (reg_addr >= BASE_ADDR) &&      // check if reg_addr is within the range of this register block instance
                (reg_addr < BASE_ADDR + N_REGS);

wire [7:0] local_addr = reg_addr - BASE_ADDR; // calculate local address within the register block


//---------------------------------------------------------------------------------
//-------------------------------- Register array ---------------------------------
//---------------------------------------------------------------------------------
reg [7:0] registers [0:N_REGS-1]; // array of N_REGS x 8-bit registers

integer i;
always @(posedge clk) begin
        if (!N_RST) begin
                // reset all registers to 0 on active low reset
                for (i = 0; i < N_REGS; i = i + 1) 
                        registers[i] <= 8'd0;
        end
        else if (selected && reg_write) 
                // write data_in to the addressed register when selected and reg_write is high
                registers[local_addr] <= data_in;
end


//---------------------------------------------------------------------------------
//-------------------------------- Register array ---------------------------------
//---------------------------------------------------------------------------------
assign data_out = selected ? registers[local_addr] : 8'd0; // output the value of the addressed register when selected, otherwise output 0

endmodule