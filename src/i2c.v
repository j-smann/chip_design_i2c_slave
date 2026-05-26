module i2c_slave (
        input wire SCL,
        inout wire SDA,
        input wire N_RST,
        output reg[7:0] data_out,
        output reg [7:0] reg_addr,
        output reg reg_read,
        output reg reg_write
);
        
        localparam [2:0] S_IDLE         = 4'd0, 
                         S_RCV_ADDR     = 4'd1, 
                         S_RCV_PTR      = 4'd2, 
                         S_WRITE        = 4'd3, 
                         S_READ         = 4'd3;
        
        reg [2:0] state;

        reg start_detect;
        reg start_resetter;
        reg stop_detect;
        reg stop_resetter;

        reg master_ack;
        reg rw_bit;

        reg [3:0] bit_counter; // 0  to 9 for 8 data-bits + 1 ack-bit
        reg [7:0] input_reg;



        wire start_rst = !N_RST | start_resetter;
        wire stop_rst  = !N_RST | stop_resetter;

        wire lsb_bit = (bit_counter == 4'h7) && !start_detect;
        wire ack_bit = (bit_counter == 4'h8) && !start_detect;

//---------------------------------------------------------------------------------
//--------------------------- Start condition detection ---------------------------
//---------------------------------------------------------------------------------
        always @(negedge SDA or posedge start_rst) begin
                if (start_rst) 
                        start_detect <= 1'b0;
                else
                        start_detect <= SCL; //falling edge of SDA while SCL is high is a start condition                
        end

        always @(posedge SCL or negedge N_RST) begin
                if (N_RST) 
                        start_resetter <= 1'b0;
                else
                        start_resetter <= start_detect; //reset start_detect at next rising edge of SCL
        end


//---------------------------------------------------------------------------------
//--------------------------- Stop condition detection ----------------------------
//---------------------------------------------------------------------------------
        always @(posedge SDA or posedge stop_rst) begin
                if(stop_rst) 
                        stop_detect <= 1'b0;
                else
                        stop_detect <= SCL; //rising edge of SDA while SCL is high is a stop condition
        end

        always @(posedge SCL or negedge N_RST) begin
                if (N_RST) 
                        stop_resetter <= 1'b0;
                else
                        stop_resetter <= stop_detect; //reset stop_detect flag at next rising edge of SCL
        end


//---------------------------------------------------------------------------------
//--------------------------- Shifting in data from SDA ---------------------------
//---------------------------------------------------------------------------------
        always @(posedge SCL) begin                     // incrementing and resetting bit_counter
                if (start_detect || ack_bit)            // resetting when new byte starts (either when one byte finished or new start condition was detected)
                        bit_counter <= 4'd0;
                else
                        bit_counter <= bit_counter + 4'd1;
        end

        always @(posedge SCL) begin                     
                if (!ack_bit) 
                        input_reg <= {input_reg[6:0], SDA}; // shifting SDA bits into input_reg until ACK-bit is reached
        end


//---------------------------------------------------------------------------------
//------------------------------ Detecting master ACK -----------------------------
//---------------------------------------------------------------------------------
        always @(posedge SCL) begin
                if (ack_bit)
                        master_ack = !SDA;      // Master sent ACK if 9th bit is low 
        end


//---------------------------------------------------------------------------------
//--------------------------------- State machine ---------------------------------
//---------------------------------------------------------------------------------
        always @(negedge SCL or negedge N_RST) begin
                if (N_RST)
                        state <= S_IDLE;
                else if (start_detect)
                        state <= S_RCV_ADDR;
                else if (stop_detect)
                        state <= S_IDLE;
                else if (ack_bit) begin
                        case (state)
                                S_IDLE:
                                        state <= S_IDLE;
                                
                                S_RCV_ADDR:
                                        if (!address_match) 
                                                state <= S_IDLE;
                                        else if (rw_bit)
                                                state <= S_READ;
                                        else
                                                state <= S_RCV_PTR;

                                S_READ:
                                        if(master_ack)
                                                state <= S_READ;
                                        else
                                                state <= S_IDLE;

                                S_RCV_PTR:
                                        state <= S_WRITE;

                                S_WRITE:
                                        state <= S_WRITE;
                        endcase
                end
        end


//---------------------------------------------------------------------------------
//---------------------------------- State logic ----------------------------------
//---------------------------------------------------------------------------------
        always @(negedge SCL or negedge N_RST) begin
                if (!N_RST || stop_detect)
                        reg_addr <= 8'd0;
                else if (ack_bit)
                



                
        end

endmodule