module top_level #(
    parameter [7:0]  BASE_ADDR_BLOCK_A    = 8'h00, // --- Addresses 0x00..0x07 ---
    parameter        N_REGS_BLOCK_A       = 8,    
    parameter [7:0]  BASE_ADDR_BLOCK_B    = 8'h08, // --- Addresses 0x08..0x0F ---
    parameter        N_REGS_BLOCK_B       = 8  
) (
    input  wire clk,
    input  wire N_RST,
    input  wire SCL,
    inout  wire SDA
);

//--------------------------------------------
//----------- Internal connections -----------
//--------------------------------------------
wire [7:0]  reg_addr_i2c;
wire [7:0]  data_from_i2c;
wire [7:0]  data_to_i2c;
wire        reg_write_i2c;

wire [7:0]  reg_addr_lfsr;
wire [7:0]  data_from_lfsr;
wire        reg_write_lfsr;

// Internal wires to connect multiple register blocks to the I2C slave
wire [7:0] data_out_blok_a, data_out_blok_b;

// OR-Tree: only addressed register block will output data, the other will output 0
assign data_to_i2c = data_out_blok_a | data_out_blok_b;

//-----------------------------------------------------------------------
//------------------------------ I2C Slave ------------------------------
//-----------------------------------------------------------------------
i2c_slave i2c_inst (
    .clk        (clk),
    .N_RST      (N_RST),
    .SDA        (SDA),
    .SCL        (SCL),
    .reg_addr   (reg_addr_i2c),
    .data_in    (data_to_i2c),
    .data_out   (data_from_i2c),
    .reg_write  (reg_write_i2c)
);

//-----------------------------------------------------------------------
//------------- lfsr random number generator for reg_block_b ------------
//-----------------------------------------------------------------------
lfsr_writer #(
    .BASE_ADDR      (BASE_ADDR_BLOCK_B),
    .N_REGS         (N_REGS_BLOCK_B)
) lfsr (
    .clk            (clk),
    .N_RST          (N_RST),     
    .waddr          (reg_addr_lfsr),
    .wdata          (data_from_lfsr),
    .we             (reg_write_lfsr)
);


//-----------------------------------------------------------------------
//----------------- Register Block A - Master writable ------------------
//-----------------------------------------------------------------------
reg_block #(
    .BASE_ADDR      (BASE_ADDR_BLOCK_A),
    .N_REGS         (N_REGS_BLOCK_A),
    // Register:        7     6     5     4     3     2     1     0
    .RESET_VALUES   ({8'h76,8'h94,8'h20,8'h42,8'h06,8'h96,8'h74,8'h20})
) reg_block_a (
    .clk        (clk),
    .N_RST      (N_RST),
    .waddr(reg_addr_i2c), .wdata(data_from_i2c), .we(reg_write_i2c),
    .raddr(reg_addr_i2c), .rdata(data_out_blok_a)
);

//-----------------------------------------------------------------------
//---------------- Register Block B - Master read-only ------------------
//-----------------------------------------------------------------------
reg_block #(
    .BASE_ADDR      (BASE_ADDR_BLOCK_B),
    .N_REGS         (N_REGS_BLOCK_B),
    .RESET_VALUES   ({8'h00,8'h00,8'h00,8'h00,8'hDE,8'hAD,8'h00,8'hFF})
) reg_block_b (
    .clk        (clk),
    .N_RST      (N_RST),
    .waddr(reg_addr_lfsr), .wdata(data_from_lfsr), .we(reg_write_lfsr),
    .raddr(reg_addr_i2c),  .rdata(data_out_blok_b)
);


endmodule
