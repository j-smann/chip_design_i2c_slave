# Running the test
```
cd /foss/designs/chip_design_i2c_slave/test
make cocotb-libi2c
```

# To open waveforms in GTKwave
```
gtkwave --save view_config_cocotb-libi2c.gtkw  sim_build/top_level.vcd
```
