module register #(
    parameter START_ADDR = 7'd0,
    parameter END_ADDR   = 7'd127
)(
    input  wire        clk,
    input  wire [7:0]  data_in,
    input  wire [7:0]  addr,
    input  wire        write,
    input  wire        n_reset,
    output reg [7:0] data_out
);

// internal memory vector
reg [END_ADDR * 8 : START_ADDR * 8] data_storage;

// async reset implementation
always @(posedge clk or negedge n_reset) begin

    //low active reset
    if (!n_reset) begin
        data_out <= 8'd0;
        data_storage <= 0;
    end
    //read or write only if being adressed
    else if (addr >= START_ADDR && addr <= END_ADDR) begin
        if (write)
            data_storage <= data_storage | (data_in << (addr*8));
        else
            data_out <= data_storage & (8'b11111111 << (addr*8));
    end
end

endmodule