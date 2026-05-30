 module tb_harness_libi2c (
    input wire clk,
    input wire N_RST,
    input wire scl_master_drive,    // 0 = Master zieht SCL low, 1 = loslassen
    input wire sda_master_drive,    // 0 = Master zieht SDA low, 1 = loslassen
    output wire scl_observed,       // was tatsächlich auf der Leitung liegt
    output wire sda_observed
);
    wire SCL;
    wire SDA;

    // Open-Drain für beide: nur low aktiv treiben, sonst hochohmig
    assign SCL = scl_master_drive ? 1'bz : 1'b0;
    assign SDA = sda_master_drive ? 1'bz : 1'b0;

    pullup(SCL);
    pullup(SDA);

    assign scl_observed = SCL;
    assign sda_observed = SDA;

    top_level uut (
        .clk(clk),
        .N_RST(N_RST),
        .SCL(SCL),
        .SDA(SDA)
    );
endmodule