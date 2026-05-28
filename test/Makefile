.PHONY: cocotb clean_vcd

cocotb: clean_vcd
	$(MAKE) -f $(shell cocotb-config --makefiles)/Makefile.sim \
		SIM=icarus \
		WAVES=1 \
		VERILOG_SOURCES="$(PWD)/../src/top_level.v $(PWD)/../src/i2c_slave.v $(PWD)/../src/reg_block.v $(PWD)/tb_harness.v $(PWD)/cocotb_dump.v" \
		TOPLEVEL=tb_harness \
		COCOTB_TEST_MODULES=testbench

clean_vcd:
	rm -f $(PWD)/sim_build/top_level.vcd