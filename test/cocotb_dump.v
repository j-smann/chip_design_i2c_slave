module cocotb_iverilog_dump();
    initial begin
        $dumpfile("sim_build/top_level.vcd");
        $dumpvars(0, tb_harness);

        $dumpvars(0, tb_harness.uut.reg_block_a.registers[0]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[1]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[2]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[3]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[4]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[5]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[6]);
        $dumpvars(0, tb_harness.uut.reg_block_a.registers[7]);
        
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[0]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[1]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[2]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[3]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[4]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[5]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[6]);
        $dumpvars(0, tb_harness.uut.reg_block_b.registers[7]);
        
    end
endmodule