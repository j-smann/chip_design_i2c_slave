# tb_top_level.py
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge

SCL_HALF_PERIOD_NS = 500   # ~1 MHz SCL
DEVICE_ADDR        = 0x55  # 7-bit-Adresse des Slaves
WRITE_BIT          = 0     # 0 = Schreiben, 1 = Lesen


async def reset_dut(dut):
    """Reset und I²C-Idle-Zustand (beide Leitungen high)."""
    dut.SCL.value = 1
    dut.SDA.value = 1
    dut.N_RST.value = 0
    await Timer(200, unit="ns")
    dut.N_RST.value = 1
    await RisingEdge(dut.clk)
    dut._log.info("Reset abgeschlossen")


async def i2c_start(dut):
    """START: fallende SDA-Flanke bei high SCL."""
    dut.SDA.value = 1
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SDA.value = 0
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")


async def i2c_send_bit(dut, bit):
    """Ein Bit senden: SDA setzen während SCL low, dann SCL pulsen."""
    dut.SDA.value = bit
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0


async def i2c_send_byte(dut, byte):
    """Byte senden, MSB zuerst (I²C-Konvention)."""
    for i in range(8):
        bit = (byte >> (7 - i)) & 1
        await i2c_send_bit(dut, bit)


async def i2c_read_ack(dut):
    """SDA loslassen, SCL pulsen, ACK-Bit abtasten.
    Returns: True wenn ACK (SDA low), False wenn NACK."""
    dut.SDA.value = "z"
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS // 2, unit="ns")
    sda_value = str(dut.SDA.value)   # "0", "1", "x", oder "z"
    await Timer(SCL_HALF_PERIOD_NS // 2, unit="ns")
    dut.SCL.value = 0
    return sda_value == "0"


async def i2c_stop(dut):
    """STOP: steigende SDA-Flanke bei high SCL."""
    dut.SDA.value = 0
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SDA.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")


@cocotb.test()
async def test_address_ack(dut):
    """Slave mit eigener Adresse ansprechen — ACK erwartet."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    address_byte = (DEVICE_ADDR << 1) | WRITE_BIT
    dut._log.info(f"Sende Adresse 0x{address_byte:02X}")

    await i2c_start(dut)
    await i2c_send_byte(dut, address_byte)
    ack = await i2c_read_ack(dut)
    await i2c_stop(dut)

    assert ack, "Slave hat nicht ge-ACKed!"
    dut._log.info("Slave hat korrekt ge-ACKed — Test bestanden!")