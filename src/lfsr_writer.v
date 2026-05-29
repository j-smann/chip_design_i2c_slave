module lfsr_writer #(
        parameter [7:0]    BASE_ADDR    = 8'h08,
        parameter          N_REGS       = 8,
        parameter [15:0]   SEED         = 16'h0001,
        parameter          TICK_DIVIDER = 4096
) (
        input  wire        clk,
        input  wire        N_RST,
        output reg  [7:0]  waddr,
        output wire [7:0]  wdata,
        output reg         we
);
        // --- 16-Bit-LFSR with taps [16,15,13,4] ---
        reg [15:0] lfsr;
        wire feedback = lfsr[15] ^ lfsr[14] ^ lfsr[12] ^ lfsr[3];

        always @(posedge clk) begin
                if (!N_RST)
                        lfsr <= SEED;
                else
                        lfsr <= {lfsr[14:0], feedback};
        end

        // taking upper 8 bits for writing wdata
        assign wdata = lfsr[15:8];

        // --- Tick-counter ---
        reg [11:0] tick_counter;
        wire tick = (tick_counter == TICK_DIVIDER - 1);

        always @(posedge clk) begin
                if (!N_RST)
                        tick_counter <= 0;
                else if (tick)
                        tick_counter <= 0;
                else
                        tick_counter <= tick_counter + 1;
        end

        // --- cycling waddr based through address space set by BASE_ADDR and N_REGS  ---
        always @(posedge clk) begin
                if (!N_RST)
                        waddr <= BASE_ADDR;
                else if (tick) begin
                        if (waddr == BASE_ADDR + N_REGS - 1)
                                waddr <= BASE_ADDR;
                else
                        waddr <= waddr + 8'd1;
                end
        end

        // --- pulsing write_enable ---
        always @(posedge clk) begin
                if (!N_RST)
                        we <= 1'b0;
                else
                        we <= tick;
    end
endmodule