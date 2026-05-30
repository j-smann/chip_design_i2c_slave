.PHONY: cocotb cocotb-libi2c clean_vcd

cocotb: clean_vcd
	$(MAKE) -f $(shell cocotb-config --makefiles)/Makefile.sim \
		SIM=icarus \
		WAVES=1 \
		VERILOG_SOURCES="$(PWD)/../src/top_level.v $(PWD)/../src/i2c_slave.v $(PWD)/../src/reg_block.v $(PWD)/../src/lfsr_writer.v $(PWD)/tb_harness.v $(PWD)/cocotb_dump.v" \
		TOPLEVEL=tb_harness \
		COCOTB_TEST_MODULES=testbench

cocotb-libi2c: clean_vcd
	$(MAKE) -f $(shell cocotb-config --makefiles)/Makefile.sim \
		SIM=icarus \
		WAVES=1 \
		VERILOG_SOURCES="$(PWD)/../src/top_level.v $(PWD)/../src/i2c_slave.v $(PWD)/../src/reg_block.v $(PWD)/../src/lfsr_writer.v $(PWD)/tb_harness_libi2c.v $(PWD)/cocotb-libi2c_dump.v" \
		TOPLEVEL=tb_harness_libi2c \
		COCOTB_TEST_MODULES=tb_with_i2cext

clean_vcd:
	rm -f $(PWD)/sim_build/top_level.vcd