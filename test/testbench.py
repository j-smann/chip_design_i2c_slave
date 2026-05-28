# tb_top_level.py
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge, ReadOnly

#---------------------------------------------------------------------------------
#---------------------------------- Parameters -----------------------------------
#---------------------------------------------------------------------------------
SCL_HALF_PERIOD_NS      = 500
SCL_QUARTER_PERIOD_NS   = SCL_HALF_PERIOD_NS // 2
DEVICE_ADDR             = 0x55
WRITE_BIT               = 0
READ_BIT                = 1

# Zustandskodierung — muss mit den localparam-Werten im i2c_slave übereinstimmen
S_IDLE     = 0
S_RCV_ADDR = 1
S_RCV_PTR  = 2
S_WRITE    = 3
S_READ     = 4


#---------------------------------------------------------------------------------
#------------------------------- Helper functions --------------------------------
#---------------------------------------------------------------------------------
async def reset_dut(dut):
    dut.SCL.value = 1
    dut.SDA.value = 1
    dut.N_RST.value = 0
    await Timer(200, unit="ns")
    dut.N_RST.value = 1
    await Timer(5000, unit="ns")
    await RisingEdge(dut.clk)
    dut._log.info("Reset abgeschlossen")

async def scl_clock_pulse(dut):
    """Erzeugt einen SCL-Puls. SDA muss VOR dem Aufruf gesetzt sein.
    SCL geht hoch (Slave sampelt), bleibt high, fällt wieder."""
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")   # Hold-Zeit nach der Fallflanke

async def i2c_start(dut):
    dut.sda_master_low.value = 0    # SDA loslassen → pullup macht 1
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.sda_master_low.value = 1    # SDA low → fallende Flanke bei high SCL = START
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")

async def i2c_stop(dut):
    """STOP: steigende SDA-Flanke bei high SCL."""
    dut.sda_master_low.value = 1          # SDA low
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.sda_master_low.value = 0          # loslassen → steigende Flanke → STOP
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")

async def i2c_send_bit(dut, bit):
    dut.sda_master_low.value = 1 if bit == 0 else 0   # 0-Bit: low ziehen; 1-Bit: loslassen
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")

async def i2c_send_byte(dut, byte):
    for i in range(8):
        await i2c_send_bit(dut, (byte >> (7 - i)) & 1)

async def i2c_read_ack(dut):
    dut.sda_master_low.value = 0    # Master lässt los, Slave darf treiben
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    sda_value = str(dut.SDA.value)
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    return sda_value == "0"

async def do_address_phase(dut, rw_bit):
    """START + Adressbyte mit R/W-Bit senden + ACK einlesen.
    Returns: True wenn der Slave ge-ACKed hat."""
    address_byte = (DEVICE_ADDR << 1) | rw_bit
    dut._log.info(f"Sende Adressbyte 0x{address_byte:02X} (R/W={rw_bit})")
    await i2c_start(dut)
    await i2c_send_byte(dut, address_byte)
    ack = await i2c_read_ack(dut)
    # Warten, bis der Slave die fallende ACK-Flanke verarbeitet hat
    for _ in range(5):
        await RisingEdge(dut.clk)
    return ack

async def capture_reg_write(dut, timeout_cycles=40):
    """Wartet auf den reg_write-Puls und liest reg_addr/data_out im selben Takt."""
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        # await ReadOnly()          # ans Ende des Zeitschritts: alle <=-Updates sind committed
        if str(dut.uut.i2c_inst.reg_write.value) == "1":
            return (int(dut.uut.i2c_inst.reg_addr.value),
                    int(dut.uut.i2c_inst.data_out.value))
    return None

async def i2c_read_byte(dut):
    """Liest ein Byte vom Slave (MSB zuerst). Master lässt SDA los, Slave treibt."""
    dut.sda_master_low.value = 0          # Master gibt SDA frei → Slave darf treiben
    byte = 0
    for _ in range(8):
        await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
        dut.SCL.value = 1
        await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
        bit = 1 if str(dut.SDA.value) == "1" else 0   # Mitte der High-Phase abtasten
        byte = (byte << 1) | bit
        await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
        dut.SCL.value = 0
        await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    return byte


async def i2c_send_ack(dut, ack):
    """Master quittiert: ack=True → SDA low (ACK), ack=False → loslassen (NACK)."""
    dut.sda_master_low.value = 1 if ack else 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 1
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.sda_master_low.value = 0          # nach dem Slot wieder freigeben


#---------------------------------------------------------------------------------
#--------------------- Slave ACKing matching address + write ----------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_write_address(dut):
    """Adresse + Schreib-Bit: ACK erwartet, danach Zustand S_RCV_PTR."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    ack = await do_address_phase(dut, WRITE_BIT)

    assert ack, "Slave hat die Adresse nicht ge-ACKed"

    state = int(dut.uut.i2c_inst.state.value)
    assert state == S_RCV_PTR, (
        f"Nach Schreib-Adresse erwartet S_RCV_PTR ({S_RCV_PTR}), "
        f"Zustand ist aber {state}"
    )
    dut._log.info("ACK erhalten und Zustand korrekt S_RCV_PTR — bestanden!")


#---------------------------------------------------------------------------------
#--------------------- Slave ACKing matching address + read ----------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_read_address(dut):
    """Adresse + Lese-Bit: ACK erwartet, danach Zustand S_READ."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    ack = await do_address_phase(dut, READ_BIT)

    assert ack, "Slave hat die Adresse nicht ge-ACKed"

    state = int(dut.uut.i2c_inst.state.value)
    assert state == S_READ, (
        f"Nach Lese-Adresse erwartet S_READ ({S_READ}), "
        f"Zustand ist aber {state}"
    )
    dut._log.info("ACK erhalten und Zustand korrekt S_READ — bestanden!")


#---------------------------------------------------------------------------------
#----------------------- Slave NACKing unmatching address ------------------------
#---------------------------------------------------------------------------------
WRONG_ADDR = 0x42   # some address != DEVICE_ADDR (0x55)

@cocotb.test()
async def test_wrong_address_no_ack(dut):
    """Fremde Adresse: KEIN ACK erwartet, Slave bleibt/fällt nach IDLE."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    address_byte = (WRONG_ADDR << 1) | WRITE_BIT
    dut._log.info(f"Sende FALSCHES Adressbyte 0x{address_byte:02X}")

    await i2c_start(dut)
    await i2c_send_byte(dut, address_byte)
    ack = await i2c_read_ack(dut)

    for _ in range(5):
        await RisingEdge(dut.clk)

    assert not ack, "Slave hat eine fremde Adresse fälschlich ge-ACKed!"

    state = int(dut.uut.i2c_inst.state.value)
    assert state == S_IDLE, (
        f"Nach fremder Adresse erwartet S_IDLE ({S_IDLE}), "
        f"Zustand ist aber {state}"
    )
    dut._log.info("Kein ACK und Zustand korrekt S_IDLE — bestanden!")


#---------------------------------------------------------------------------------
#----------------------- Slave NACKing unmatching address ------------------------
#---------------------------------------------------------------------------------
WRONG_ADDR = 0x54   # address one below device address

@cocotb.test()
async def test_wrong_address_one_above_no_ack(dut):
    """Fremde Adresse: KEIN ACK erwartet, Slave bleibt/fällt nach IDLE."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    address_byte = (WRONG_ADDR << 1) | WRITE_BIT
    dut._log.info(f"Sende FALSCHES Adressbyte 0x{address_byte:02X}")

    await i2c_start(dut)
    await i2c_send_byte(dut, address_byte)
    ack = await i2c_read_ack(dut)

    for _ in range(5):
        await RisingEdge(dut.clk)

    assert not ack, "Slave hat eine fremde Adresse fälschlich ge-ACKed!"

    state = int(dut.uut.i2c_inst.state.value)
    assert state == S_IDLE, (
        f"Nach fremder Adresse erwartet S_IDLE ({S_IDLE}), "
        f"Zustand ist aber {state}"
    )
    dut._log.info("Kein ACK und Zustand korrekt S_IDLE — bestanden!")


#---------------------------------------------------------------------------------
#----------------------- Slave NACKing unmatching address ------------------------
#---------------------------------------------------------------------------------
WRONG_ADDR = 0x56   # address one above device address

@cocotb.test()
async def test_wrong_address_one_below_no_ack(dut):
    """Fremde Adresse: KEIN ACK erwartet, Slave bleibt/fällt nach IDLE."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    address_byte = (WRONG_ADDR << 1) | WRITE_BIT
    dut._log.info(f"Sende FALSCHES Adressbyte 0x{address_byte:02X}")

    await i2c_start(dut)
    await i2c_send_byte(dut, address_byte)
    ack = await i2c_read_ack(dut)

    for _ in range(5):
        await RisingEdge(dut.clk)

    assert not ack, "Slave hat eine fremde Adresse fälschlich ge-ACKed!"

    state = int(dut.uut.i2c_inst.state.value)
    assert state == S_IDLE, (
        f"Nach fremder Adresse erwartet S_IDLE ({S_IDLE}), "
        f"Zustand ist aber {state}"
    )
    dut._log.info("Kein ACK und Zustand korrekt S_IDLE — bestanden!")


#---------------------------------------------------------------------------------
#--------------------------- Master writing to register --------------------------
#---------------------------------------------------------------------------------
WRITE_INDEX = 0x03
WRITE_DATA  = 0x57

@cocotb.test()
async def test_full_write(dut):
    """Vollständiger Schreibvorgang: START, Adresse, Index, Daten, STOP."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    # 1) Adressphase (Schreiben)
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse"

    # 2) Register-Index
    await i2c_send_byte(dut, WRITE_INDEX)
    assert await i2c_read_ack(dut), "Kein ACK auf den Register-Index"

    # Datenbyte senden
    await i2c_send_byte(dut, WRITE_DATA)

    # Capture-Task starten, BEVOR das ACK gelesen wird —
    # der reg_write-Puls tritt während des ACK-Slots auf.
    capture_task = cocotb.start_soon(capture_reg_write(dut))

    assert await i2c_read_ack(dut), "Kein ACK auf das Datenbyte"

    result = await capture_task          # auf das Ergebnis der Task warten
    assert result is not None, "Slave hat keinen reg_write-Puls erzeugt"
    addr, data = result
    dut._log.info(f"reg_write: reg_addr={addr}, data_out={data}")

    await i2c_stop(dut)

    reg3 = int(dut.uut.reg_block_a.registers[3].value)
    assert reg3 == WRITE_DATA, f"regs[3] = 0x{reg3:02X}, erwartet 0x{WRITE_DATA:02X}"

    assert data == WRITE_DATA, \
        f"data_out 0x{data:02X} != gesendetes Byte 0x{WRITE_DATA:02X}"
    assert addr == WRITE_INDEX, \
        f"reg_write zeigt auf 0x{addr:02X}, erwartet Index 0x{WRITE_INDEX:02X}"
    dut._log.info("Schreibvorgang korrekt — bestanden!")


#---------------------------------------------------------------------------------
#------------------ Master writing to then reading from slave --------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_write_then_read(dut):
    """0x57 in Register 0 schreiben, danach zurücklesen und vergleichen."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    test_value = 0x57
    test_index = 0x00

    # --- Schreib-Transaktion ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Write)"
    await i2c_send_byte(dut, test_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index"
    await i2c_send_byte(dut, test_value)
    assert await i2c_read_ack(dut), "Kein ACK auf das Datenbyte"
    await i2c_stop(dut)

    # --- Lese-Transaktion (reg_addr ist nach STOP wieder 0) ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Read)"

    read_value = await i2c_read_byte(dut)
    await i2c_send_ack(dut, ack=False)    # NACK: nur ein Byte gewünscht
    await i2c_stop(dut)

    dut._log.info(f"Geschrieben: 0x{test_value:02X}, gelesen: 0x{read_value:02X}")
    assert read_value == test_value, \
        f"Gelesener Wert 0x{read_value:02X} != geschriebener 0x{test_value:02X}"
    dut._log.info("Write-then-Read-Roundtrip korrekt — bestanden!")