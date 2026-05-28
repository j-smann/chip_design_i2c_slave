module i2c_slave #(
        parameter [6:0] DEVICE_ADDRESS = 7'h55
)(
        input wire clk,
        input wire SCL,
        inout wire SDA,
        input wire N_RST,
        input wire [7:0] data_in,
        output reg[7:0] data_out,
        output reg [7:0] reg_addr,
        output reg reg_write
);
        
        localparam [2:0] S_IDLE         = 3'd0, 
                         S_RCV_ADDR     = 3'd1, 
                         S_RCV_PTR      = 3'd2, 
                         S_WRITE        = 3'd3, 
                         S_READ         = 3'd4;

        
        reg [2:0] state;

        reg master_ack;
        reg rw_bit;

        reg [3:0] bit_counter;  // 0  to 9 for 8 data-bits + 1 ack-bit
        reg [7:0] input_reg;    // for incomming bits by master
        reg [7:0] output_reg;   // for outgoing bits to master

        wire address_detect = (input_reg[7:1] == DEVICE_ADDRESS);     // comparing received address bits with module's device address
        wire read_write_bit = input_reg[0];                           // LSB of received byte is the read/write bit

        reg output_control; // control signal for when to drive SDA low (when output_control is low) or release SDA (when output_control is high, high impedance)


//---------------------------------------------------------------------------------
//--------------------------- I2C Input Synchronization ---------------------------
//---------------------------------------------------------------------------------
reg [2:0] scl_sync; // 3-stage shift register for synchronizing SCL to clk domain
reg [2:0] sda_sync; // 3-stage shift register for synchronizing SDA to clk domain

// Synchronize SCL and SDA to clk domain using 3-stage shift registers to avoid metastability and ensure reliable edge detection
always @(posedge clk) begin
    if (!N_RST) begin
        scl_sync <= 3'b111; // initialize to 1s to avoid false start/stop condition detection at reset (SCL and SDA are high when bus is idle)
        sda_sync <= 3'b111;
    end else begin
        scl_sync <= {scl_sync[1:0], SCL};
        sda_sync <= {sda_sync[1:0], SDA};
    end
end

// Using the second stage of the shift registers as the synchronized versions of SCL and SDA for edge detection and state machine logic
wire scl_q = scl_sync[1];
wire sda_q = sda_sync[1];

// Detecting rising and falling edges of SCL and SDA for start/stop condition detection and bit sampling
wire scl_rising  =  scl_sync[1] & ~scl_sync[2];
wire scl_falling = ~scl_sync[1] &  scl_sync[2];
wire sda_rising  =  sda_sync[1] & ~sda_sync[2];
wire sda_falling = ~sda_sync[1] &  sda_sync[2];


//---------------------------------------------------------------------------------
//------------------------- I2C Start condition detection -------------------------
//---------------------------------------------------------------------------------
wire start_detect = sda_falling && scl_q; // falling edge of SDA while SCL is high is a start condition

reg start_pending; // for memorizing start condition

// Set start_pending when a start condition is detected, and clear it on the next falling edge of SCL (when the first bit is being sampled) to ensure the state machine processes the start condition correctly
always @(posedge clk) begin
    if (!N_RST)
        start_pending <= 1'b0;
    else if (start_detect)
        start_pending <= 1'b1;
    else if (scl_falling)
        start_pending <= 1'b0;
end

wire lsb_bit = (bit_counter == 4'h7) && !start_pending;
wire ack_bit = (bit_counter == 4'h8) && !start_pending;


//---------------------------------------------------------------------------------
//------------------------- I2C Stop condition detection --------------------------
//---------------------------------------------------------------------------------
wire stop_detect = sda_rising && scl_q; // rising edge of SDA while SCL is high is a stop condition


//---------------------------------------------------------------------------------
//--------------------------- Shifting in data from SDA ---------------------------
//---------------------------------------------------------------------------------
        always @(posedge clk) begin
                if (!N_RST) 
                      bit_counter <= 4'd0;
                else if (scl_falling) begin
                        if (start_pending || ack_bit) 
                                bit_counter <= 4'd0; // reset bit counter at start condition or when ACK bit is reached (one byte received)
                        else
                                bit_counter <= bit_counter + 4'd1; // increment bit counter on each falling edge of SCL while receiving bits from master
                end
        end

        always @(posedge clk) begin     
                if (!N_RST)
                        input_reg <= 8'd0;       
                else if (scl_rising && !ack_bit) 
                        input_reg <= {input_reg[6:0], sda_q}; // shift in bits from SDA on rising edge of SCL while not at ACK bit (to capture 8 data bits before ACK bit)
        end


//---------------------------------------------------------------------------------
//------------------------------ Detecting master ACK -----------------------------
//---------------------------------------------------------------------------------
        always @(posedge clk) begin
                if (scl_rising && ack_bit)
                        master_ack <= ~sda_q; // sample SDA on rising edge of SCL when at ACK bit position to detect if master sent ACK (SDA low) or NACK (SDA high)
        end

//---------------------------------------------------------------------------------
//--------------------------------- State machine ---------------------------------
//---------------------------------------------------------------------------------
        always @(posedge clk) begin
                if (!N_RST)
                        state <= S_IDLE;
                else if (stop_detect)
                        state <= S_IDLE; // transition back to IDLE state on stop condition to be ready for next transaction
                else if (scl_falling) begin
                        if (start_pending)
                                state <= S_RCV_ADDR; // transition to receiving address state on start condition
                        else if (ack_bit) begin
                                case (state)
                                        S_IDLE: 
                                                state <= S_IDLE; // stay in IDLE state until start condition is detected
                                        
                                        S_RCV_ADDR: 
                                                if (!address_detect) // if received address does not match device address, go back to IDLE state to ignore the transaction
                                                        state <= S_IDLE;
                                                else if (read_write_bit) // if received address matches and read/write bit is 1 (read), transition to READ state to prepare for sending data to master
                                                        state <= S_READ;
                                                else // if received address matches and read/write bit is 0 (write), transition to RCV_PTR state to receive register address from master
                                                        state <= S_RCV_PTR;
                                        
                                        S_RCV_PTR: 
                                                state <= S_WRITE; // after receiving register address from master, transition to WRITE state to receive data to write to register
                                        
                                        S_WRITE: 
                                                state <= S_WRITE; // stay in WRITE state to receive more data bytes if master continues to ACK, or transition back to IDLE on stop condition
                                        
                                        S_READ: 
                                                if (master_ack) // if master ACKed received data, stay in READ state to send next byte from next register address
                                                        state <= S_READ;
                                                else // if master NACKed received data, transition back to IDLE state to end the transaction
                                                        state <= S_IDLE;
                                        
                                endcase
                        end
                end
        end


//---------------------------------------------------------------------------------
//---------------------------------- State logic ----------------------------------
//---------------------------------------------------------------------------------
        // updating module output reg_addr if master transmitted register adddress or incremented register address for repeated/bulk read
        always @(posedge clk) begin
                if (!N_RST)
                        reg_addr <= 8'd0;
                else if (stop_detect) 
                        reg_addr <= 8'd0;
                else if (scl_falling && ack_bit && (state == S_RCV_PTR))
                        reg_addr <= input_reg;            // Index laden
                else if (scl_falling && ack_bit &&                                                      // Read: increment address instantly
                                        ((state == S_READ) ||                                           // for S_READ or
                                         (state == S_RCV_ADDR && address_detect && read_write_bit)))    // when in S_RCV_ADDR, and next state will be S_READ
                        reg_addr <= reg_addr + 8'd1;
                else if (reg_write)
                        reg_addr <= reg_addr + 8'd1;      // Write: increment only after rising edge of reg_write (to precent writing received data to wron register)
        end


        // writing received data to register
        always @(posedge clk) begin
                if (!N_RST) begin
                        data_out <= 8'd0;
                        reg_write <= 1'b0;
                end
                else if (scl_falling && (state == S_WRITE) && ack_bit) begin // when in WRITE state and ACK bit (end of Byte) is reached, update data_out with received data from master to write to register
                        data_out <= input_reg;  // update data_out with received data from master 
                        reg_write <= 1'b1;      // set reg_write high to indicate new data is available to write to register file
                end
                else
                        reg_write <= 1'b0;
        end


        // updating output_reg with data to send to master 
        always @(posedge clk) begin
                if (!N_RST)
                        output_reg <= 8'd0;
                else if (scl_falling) begin
                        if (lsb_bit)
                                output_reg <= data_in; // update output_reg with data_in from register file when LSB bit is reached (one byte transmitted and ACK bit is next)
                        else
                                output_reg <= {output_reg[6:0], 1'b0}; // shift output_reg bits to the left to transmit next bit on SDA
                end
        end


//---------------------------------------------------------------------------------
//--------------------------------- Output logic ----------------------------------
//---------------------------------------------------------------------------------
assign SDA = output_control ? 1'bz : 1'b0; // drive SDA low when output_control is low, otherwise release SDA (high impedance)

always @(posedge clk) begin
        if(!N_RST)
                output_control <= 1'b1; // release SDA at reset
        else if (scl_falling) begin
                if (start_pending)
                        output_control <= 1'b1;
                else if (lsb_bit) begin
                        output_control <= !(((state == S_RCV_ADDR) && address_detect) ||
                                            (state == S_RCV_PTR)                      ||
                                            (state == S_WRITE)); // drive SDA low to send ACK bit after receiving device address, register address or data byte from master
                end
                else if (ack_bit) begin
                        if (((state == S_READ) && master_ack) || // if master ACKed received data in READ state, send MSB of next data byte
                            ((state == S_RCV_ADDR) && address_detect && read_write_bit)) // master just finished sending matching device address with read bit set, so send MSB of data in next cycle
                                output_control <= output_reg[7]; // drive SDA according to MSB of output_shift which is the next bit to send to master
                        else
                                output_control <= 1'b1; // release SDA if master did not ACK received data
                end
                else if (state == S_READ)
                        output_control <= output_reg[7]; // drive SDA according to next data bit when in READ state
                else
                        output_control <= 1'b1; // release SDA in all other cases
        end
end

endmodule