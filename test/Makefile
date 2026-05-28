.PHONY: cocotb

cocotb:
	$(MAKE) -f $(shell cocotb-config --makefiles)/Makefile.sim \
		SIM=icarus \
		WAVES=1 \
		VERILOG_SOURCES="$(PWD)/../src/top_level.v $(PWD)/../src/i2c_slave.v $(PWD)/../src/reg_block.v" \
		TOPLEVEL=top_level \
		MODULE=testbench