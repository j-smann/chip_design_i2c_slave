module top_level (
    input  wire clk,
    input  wire N_RST,
    input  wire SCL,
    inout  wire SDA
);

//--------------------------------------------
//----------- Internal connections -----------
//--------------------------------------------
wire [7:0]  reg_addr;
wire [7:0]  data_from_i2c;
wire [7:0]  data_to_i2c;
wire        reg_write;

// Internal wires to connect multiple register blocks to the I2C slave
wire [7:0] data_out_blok_a, data_out_blok_b;

// OR-Tree: only addressed register block will output data, the other will output 0
assign data_to_i2c = data_out_blok_a | data_out_blok_b;

//--------------------------------------------
//---------------- I2C Slave -----------------
//--------------------------------------------
i2c_slave i2c_inst (
    .clk        (clk),
    .N_RST      (N_RST),
    .SDA        (SDA),
    .SCL        (SCL),
    .reg_addr   (reg_addr),
    .data_in    (data_to_i2c),
    .data_out   (data_from_i2c),
    .reg_write  (reg_write)
);

//--------------------------------------------
//------------- Register Block A -------------
//--------------------------------------------
// --- Addresses 0x00..0x08 ---
reg_block #(
    .BASE_ADDR  (8'h00),
    .N_REGS     (8)
) reg_block_a (
    .clk        (clk),
    .N_RST      (N_RST),
    .reg_addr   (reg_addr),
    .data_in    (data_from_i2c),
    .data_out   (data_out_blok_a),
    .reg_write  (reg_write)
);

//--------------------------------------------
//------------- Register Block B -------------
//--------------------------------------------
// --- Addresses 0x09..0x0F ---
reg_block #(
    .BASE_ADDR  (8'h09),
    .N_REGS     (8)
) reg_block_b (
    .clk        (clk),
    .N_RST      (N_RST),
    .reg_addr   (reg_addr),
    .data_in    (data_from_i2c),
    .data_out   (data_out_blok_b),
    .reg_write  (reg_write)
);


endmodule
