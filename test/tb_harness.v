module tb_harness (
    input wire clk,
    input wire N_RST,
    input wire SCL,
    input wire sda_master_low   // 1 = Master zieht SDA low, 0 = Master lässt los
);
    wire SDA;

    // Open-Drain-Treiber des Masters — exakt wie ein echter I2C-Master
    assign SDA = sda_master_low ? 1'b0 : 1'bz;

    // Bus-Pull-up
    pullup(SDA);

    // Das eigentliche Design
    top_level uut (
        .clk   (clk),
        .N_RST (N_RST),
        .SCL   (SCL),
        .SDA   (SDA)
    );
endmodule