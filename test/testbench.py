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

async def i2c_repeated_start(dut):
    """Repeated START: ohne vorheriges STOP einen neuen START erzeugen."""
    dut.sda_master_low.value = 0          # SDA freigeben → geht auf high (pullup)
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")
    dut.SCL.value = 1                     # SCL high, während SDA high
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.sda_master_low.value = 1          # fallende SDA-Flanke bei high SCL → (RE)START
    await Timer(SCL_HALF_PERIOD_NS, unit="ns")
    dut.SCL.value = 0
    await Timer(SCL_QUARTER_PERIOD_NS, unit="ns")

async def i2c_write_single(dut, index, value):
    """Hilfsfunktion: eine komplette Einzel-Schreibtransaktion."""
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), f"Kein ACK auf Adresse (Index 0x{index:02X})"
    await i2c_send_byte(dut, index)
    assert await i2c_read_ack(dut), f"Kein ACK auf Index 0x{index:02X}"
    await i2c_send_byte(dut, value)
    assert await i2c_read_ack(dut), f"Kein ACK auf Daten 0x{value:02X}"
    await i2c_stop(dut)

async def i2c_read_single(dut, index):
    """Komplette Einzel-Lese-Transaktion: Index setzen, RESTART, ein Byte lesen, STOP."""
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), f"Kein ACK auf Adresse (Index-Phase, 0x{index:02X})"
    await i2c_send_byte(dut, index)
    assert await i2c_read_ack(dut), f"Kein ACK auf Index 0x{index:02X}"

    await i2c_repeated_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
    assert await i2c_read_ack(dut), f"Kein ACK auf Adresse (Read, 0x{index:02X})"

    value = await i2c_read_byte(dut)
    await i2c_send_ack(dut, ack=False)
    await i2c_stop(dut)
    return value

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
    await Timer(1000, unit="ns")

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


#---------------------------------------------------------------------------------
#----------- Master writing to then reading from slave with restart --------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_repeated_start_read(dut):
    """Wert in Register 3 schreiben, dann per Repeated START gezielt zurücklesen."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    test_value = 0x42
    test_index = 0x03

    # --- Wert vorbereiten: regulärer Schreibvorgang ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Write)"
    await i2c_send_byte(dut, test_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index"
    await i2c_send_byte(dut, test_value)
    assert await i2c_read_ack(dut), "Kein ACK auf das Datenbyte"
    await i2c_stop(dut)
    await Timer(5000, unit="ns")

    # --- Lesen mit Repeated START: erst Index setzen, dann ohne STOP umschalten ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Index-Phase)"
    await i2c_send_byte(dut, test_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index (Index-Phase)"

    await i2c_repeated_start(dut)         # <-- kein STOP dazwischen!
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Read)"

    read_value = await i2c_read_byte(dut)
    await i2c_send_ack(dut, ack=False)    # NACK: nur ein Byte
    await i2c_stop(dut)

    dut._log.info(f"Register 0x{test_index:02X}: geschrieben 0x{test_value:02X}, "
                  f"gelesen 0x{read_value:02X}")
    assert read_value == test_value, \
        f"Gelesener Wert 0x{read_value:02X} != 0x{test_value:02X}"
    dut._log.info("Repeated-START-Read korrekt — bestanden!")


#---------------------------------------------------------------------------------
#------------------------ Master bulk writing to slave ---------------------------
#---------------------------------------------------------------------------------
async def reg_write_monitor(dut, captured):
    """Sammelt im Hintergrund alle reg_write-Pulse (addr, data) über den ganzen Test."""
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if str(dut.uut.i2c_inst.reg_write.value) == "1":
            captured.append((
                int(dut.uut.i2c_inst.reg_addr.value),
                int(dut.uut.i2c_inst.data_out.value),
            ))


@cocotb.test()
async def test_bulk_write(dut):
    """Bulk-Write: ein Index, mehrere Datenbytes, Auto-Increment der reg_addr."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    captured = []
    cocotb.start_soon(reg_write_monitor(dut, captured))

    start_index = 0x02
    data_bytes  = [0x11, 0x22, 0x33]

    # Adresse (Schreiben) + Index
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse"
    await i2c_send_byte(dut, start_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index"

    # Mehrere Datenbytes hintereinander, jeweils mit ACK
    for i, b in enumerate(data_bytes):
        await i2c_send_byte(dut, b)
        assert await i2c_read_ack(dut), f"Kein ACK auf Datenbyte {i} (0x{b:02X})"

    await i2c_stop(dut)

    # ein paar Takte, damit der letzte reg_write-Puls sicher erfasst ist
    for _ in range(5):
        await RisingEdge(dut.clk)

    # 1) Genau so viele Schreibzugriffe wie gesendete Bytes?
    assert len(captured) == len(data_bytes), \
        f"Erwartete {len(data_bytes)} reg_write-Pulse, bekam {len(captured)}"

    # 2) Jeder Puls an der richtigen, fortlaufenden Adresse mit dem richtigen Wert?
    for i, (addr, data) in enumerate(captured):
        exp_addr = start_index + i
        exp_data = data_bytes[i]
        dut._log.info(f"Puls {i}: addr=0x{addr:02X}, data=0x{data:02X}")
        assert addr == exp_addr, \
            f"Byte {i}: reg_addr 0x{addr:02X} != erwartet 0x{exp_addr:02X}"
        assert data == exp_data, \
            f"Byte {i}: data 0x{data:02X} != erwartet 0x{exp_data:02X}"

    # 3) Und sind die Werte auch physisch in den Registern gelandet?
    for i, b in enumerate(data_bytes):
        reg_val = int(dut.uut.reg_block_a.registers[start_index + i].value)
        assert reg_val == b, \
            f"registers[{start_index + i}] = 0x{reg_val:02X}, erwartet 0x{b:02X}"

    dut._log.info("Bulk-Write korrekt — alle drei Bytes am richtigen Platz!")


#---------------------------------------------------------------------------------
#----------------------- Master bulk reading from slave --------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_bulk_read(dut):
    """Mehrere Register füllen, dann als Sequenz mit Auto-Increment zurücklesen."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    start_index = 0x03
    values      = [0xDE, 0xAD, 0xBE, 0xEF]

    # --- Register vorbereiten (Bulk-Write) ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Write)"
    await i2c_send_byte(dut, start_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index"
    for i, v in enumerate(values):
        await i2c_send_byte(dut, v)
        assert await i2c_read_ack(dut), f"Kein ACK auf Schreib-Byte {i}"
    await i2c_stop(dut)

    # --- Lese-Pointer setzen, dann per Repeated START umschalten ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Index-Phase)"
    await i2c_send_byte(dut, start_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index (Index-Phase)"

    await i2c_repeated_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
    assert await i2c_read_ack(dut), "Kein ACK auf die Adresse (Read)"

    # --- Sequenziell lesen: ACK nach jedem Byte außer dem letzten ---
    read_values = []
    for i in range(len(values)):
        byte = await i2c_read_byte(dut)
        read_values.append(byte)
        is_last = (i == len(values) - 1)
        await i2c_send_ack(dut, ack=not is_last)   # letzte: NACK, sonst ACK

    await i2c_stop(dut)

    dut._log.info(f"Geschrieben: {[f'0x{v:02X}' for v in values]}")
    dut._log.info(f"Gelesen:     {[f'0x{v:02X}' for v in read_values]}")

    assert read_values == values, \
        f"Bulk-Read stimmt nicht: {read_values} != {values}"
    dut._log.info("Bulk-Read korrekt — komplette Sequenz mit Auto-Increment!")


#---------------------------------------------------------------------------------
#------------------------------- Address decoding --------------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_address_decoding(dut):
    """Schreibzugriffe landen im richtigen Block; der andere bleibt unberührt."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    # je ein Register in Block A und in Block B beschreiben
    await i2c_write_single(dut, 0x02, 0xA5)   # Block A (0x00..0x07)
    await i2c_write_single(dut, 0x07, 0x5B)   # Block B (0x08..0x0F)

    # 1) Wert in Block A korrekt angekommen?
    a_val = int(dut.uut.reg_block_a.registers[0x02].value)
    assert a_val == 0xA5, f"Block A registers[5] = 0x{a_val:02X}, erwartet 0xA5"

    # 2) Wert in Block B korrekt angekommen? (lokaler Index = 0x0B - 0x08 = 0x03)
    b_val = int(dut.uut.reg_block_a.registers[0x07].value)
    assert b_val == 0x5B, f"Block B registers[3] = 0x{b_val:02X}, erwartet 0x5B"

    dut._log.info("Adress-Dekodierung korrekt — A und B sauber getrennt!")


#---------------------------------------------------------------------------------
#----------------- Writing to non existing register address ----------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_unmapped_address(dut):
    """Zugriff auf eine Register-Adresse, für die kein reg_block zuständig ist."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    unmapped_index = 0x20    # außerhalb beider Blöcke (A: 0x00-0x0F, B: 0x10-0x17)

    # einen Referenzwert in ein belegtes Register schreiben, um später Kollision auszuschließen
    await i2c_write_single(dut, 0x05, 0x99)

    # --- Schreibversuch auf die unbelegte Adresse: Slave ACKed trotzdem ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Slave hat die Geräteadresse nicht ge-ACKed"
    await i2c_send_byte(dut, unmapped_index)
    assert await i2c_read_ack(dut), "Slave hat den (unbelegten) Index nicht ge-ACKed"
    await i2c_send_byte(dut, 0xCC)
    assert await i2c_read_ack(dut), "Slave hat das Datenbyte nicht ge-ACKed"
    await i2c_stop(dut)

    # 1) Das belegte Register darf unverändert sein (kein versehentlicher Treffer)
    ref = int(dut.uut.reg_block_a.registers[0x05].value)
    assert ref == 0x99, f"Register 0x05 wurde fälschlich verändert: 0x{ref:02X}"

    # --- Leseversuch von der unbelegten Adresse: OR-Tree liefert 0x00 ---
    await i2c_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
    assert await i2c_read_ack(dut), "Kein ACK (Index-Phase)"
    await i2c_send_byte(dut, unmapped_index)
    assert await i2c_read_ack(dut), "Kein ACK auf den Index"

    await i2c_repeated_start(dut)
    await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
    assert await i2c_read_ack(dut), "Kein ACK (Read)"

    read_value = await i2c_read_byte(dut)
    await i2c_send_ack(dut, ack=False)
    await i2c_stop(dut)

    dut._log.info(f"Lesen von unbelegter Adresse 0x{unmapped_index:02X}: "
                  f"0x{read_value:02X}")
    assert read_value == 0x00, \
        f"Unbelegte Adresse sollte 0x00 liefern, war aber 0x{read_value:02X}"
    dut._log.info("Unbelegte Adresse korrekt behandelt — ACK ohne Wirkung, Lesen = 0x00!")


#---------------------------------------------------------------------------------
#----------------------------- Block B is read-only ------------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_block_b_is_read_only(dut):
    """Schreibversuch auf eine B-Adresse darf den Inhalt nicht verändern."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    target_addr  = 0x0A      # mitten in Block B
    forbidden    = 0xFF      # auffälliger Wert, den wir reinzudrücken versuchen

    # Wert vor dem Schreibversuch lesen (Referenz)
    before = await i2c_read_single(dut, target_addr)
    dut._log.info(f"B[0x{target_addr:02X}] vor Schreibversuch: 0x{before:02X}")

    # Schreibversuch — der Slave wird ACKen, aber das LFSR-Modul ist der einzige
    # Schreiber für Block B, also darf der Wert NICHT 0xFF werden.
    await i2c_write_single(dut, target_addr, forbidden)

    # Sofort wieder lesen, BEVOR das LFSR einen Tick gemacht haben könnte
    after = await i2c_read_single(dut, target_addr)
    dut._log.info(f"B[0x{target_addr:02X}] nach Schreibversuch:  0x{after:02X}")

    assert after != forbidden, \
        f"Block B hat den Schreibversuch akzeptiert! Wert ist 0x{after:02X}"
    dut._log.info("Block B ist read-only — Schreibversuch korrekt ignoriert.")


#---------------------------------------------------------------------------------
#------------------------------ LFSR is active -----------------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_lfsr_is_active(dut):
    """Mehrfaches Lesen eines B-Registers über die Zeit muss unterschiedliche Werte liefern."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    target_addr  = 0x09
    n_samples    = 4
    wait_between = 2  # ms — länger als die ~1.3 ms Update-Periode pro Register

    samples = []
    for i in range(n_samples):
        value = await i2c_read_single(dut, target_addr)
        samples.append(value)
        dut._log.info(f"Sample {i}: B[0x{target_addr:02X}] = 0x{value:02X}")
        if i < n_samples - 1:
            await Timer(wait_between, unit="ms")

    unique_values = set(samples)
    assert len(unique_values) >= 2, \
        f"LFSR scheint zu hängen: alle {n_samples} Lesungen lieferten {samples}"
    dut._log.info(f"LFSR ist aktiv — {len(unique_values)} verschiedene Werte in {n_samples} Lesungen.")


#---------------------------------------------------------------------------------
#----------------------- All B registers get updated -----------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_all_b_registers_updated(dut):
    """Über die Zeit muss das LFSR jedes einzelne Register in Block B beschreiben."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    raw_b = dut.uut.reg_block_b.RESET_VALUES.value
    base_addr = int(dut.uut.reg_block_b.BASE_ADDR.value)
    n_regs = int(dut.uut.reg_block_b.BASE_ADDR.value)

    reset_values_local = {i: (int(raw_b) >> (i * 8)) & 0xFF for i in range(n_regs)}
    # Auf Bus-Adressen mappen
    reset_values = {base_addr + i: v for i, v in reset_values_local.items()}


    # Warten, bis das LFSR mehrere komplette Adress-Umläufe gemacht hat.
    # Ein Umlauf dauert ~1.3 ms (8 Register x 4096 Ticks x 40 ns), wir nehmen 5 ms.
    await Timer(5, unit="ms")

    changed_count = 0
    for addr in range(0x08, 0x10):
        value = await i2c_read_single(dut, addr)
        dut._log.info(f"B[0x{addr:02X}] = 0x{value:02X} (Reset war 0x{reset_values[addr]:02X})")
        if value != reset_values[addr]:
            changed_count += 1

    # Strikteste sinnvolle Aussage: KEIN Register darf auf dem Reset-Wert hängen.
    # Das LFSR sollte längst jedes Register mehrfach überschrieben haben.
    assert changed_count == 8, \
        f"Nur {changed_count}/8 B-Register wurden vom LFSR aktualisiert"
    dut._log.info("LFSR bedient alle acht B-Register zuverlässig.")


#---------------------------------------------------------------------------------
#------------------------- Block A unaffected by LFSR ----------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_block_a_unaffected_by_lfsr(dut):
    """Das LFSR darf keine Werte in Block A schreiben, auch nicht über lange Zeit."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    # Erkennbares Muster in jedes A-Register schreiben
    pattern = {addr: 0xA0 | (addr & 0x07) for addr in range(0x00, 0x08)}
    # ergibt: 0x00→0xA0, 0x01→0xA1, ..., 0x07→0xA7
    for addr, value in pattern.items():
        await i2c_write_single(dut, addr, value)

    # Lange warten — viele LFSR-Umläufe (5 ms = ~4 komplette Umläufe durch Block B)
    await Timer(5, unit="ms")

    # Alle A-Register müssen exakt das geschriebene Muster zeigen
    for addr, expected in pattern.items():
        value = await i2c_read_single(dut, addr)
        dut._log.info(f"A[0x{addr:02X}] = 0x{value:02X}, erwartet 0x{expected:02X}")
        assert value == expected, \
            f"A[0x{addr:02X}] wurde verändert: 0x{value:02X} statt 0x{expected:02X}"

    dut._log.info("Block A bleibt vom LFSR unberührt — saubere Bereichstrennung.")


#---------------------------------------------------------------------------------
#--------------- Bulk read stress test over LFSR activity ------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_bulk_read_stress(dut):
    """Wiederholte Bulk-Reads über lange Zeit — Design muss konsistent funktionieren."""
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    n_iterations    = 20
    n_bytes_per_read = 4
    start_index     = 0x09
    all_reads       = []

    for iteration in range(n_iterations):
        # Pointer setzen und in den Lesemodus wechseln
        await i2c_start(dut)
        await i2c_send_byte(dut, (DEVICE_ADDR << 1) | WRITE_BIT)
        assert await i2c_read_ack(dut), \
            f"Iter {iteration}: Kein ACK auf Adresse (Index-Phase)"
        await i2c_send_byte(dut, start_index)
        assert await i2c_read_ack(dut), \
            f"Iter {iteration}: Kein ACK auf Index"

        await i2c_repeated_start(dut)
        await i2c_send_byte(dut, (DEVICE_ADDR << 1) | READ_BIT)
        assert await i2c_read_ack(dut), \
            f"Iter {iteration}: Kein ACK auf Adresse (Read)"

        # Bulk-Read
        bytes_this_iter = []
        for i in range(n_bytes_per_read):
            byte = await i2c_read_byte(dut)
            bytes_this_iter.append(byte)
            is_last = (i == n_bytes_per_read - 1)
            await i2c_send_ack(dut, ack=not is_last)

        await i2c_stop(dut)
        all_reads.append(bytes_this_iter)

        # Nach jeder Transaktion: State zurück auf IDLE?
        for _ in range(5):
            await RisingEdge(dut.clk)
        state = int(dut.uut.i2c_inst.state.value)
        assert state == S_IDLE, \
            f"Iter {iteration}: State nicht IDLE nach Bulk-Read, ist {state}"

        # Werte alle plausibel?
        assert all(0 <= v <= 255 for v in bytes_this_iter), \
            f"Iter {iteration}: ungültige Werte {bytes_this_iter}"

        # Etwas Pause zwischen den Iterationen, damit das LFSR weiterläuft
        await Timer(500, unit="us")

    # --- Aggregierte Analyse über alle Iterationen ---
    # Pro Adress-Slot prüfen, dass nicht immer derselbe Wert kam
    for slot in range(n_bytes_per_read):
        values_in_slot = [reads[slot] for reads in all_reads]
        unique = set(values_in_slot)
        dut._log.info(
            f"Slot {slot} (Adr 0x{start_index + slot:02X}): "
            f"{len(unique)} verschiedene Werte über {n_iterations} Iter"
        )
        assert len(unique) >= 2, \
            f"Slot {slot}: alle {n_iterations} Werte identisch ({values_in_slot}) — LFSR hängt?"

    # Sanity-Nachprobe: Slave funktioniert auch nach all dem noch
    final_check = await i2c_read_single(dut, 0x00)
    dut._log.info(f"Nach {n_iterations} Bulk-Reads: A[0x00] = 0x{final_check:02X}")

    dut._log.info(f"Stresstest bestanden: {n_iterations} Bulk-Reads, "
                  f"jeweils {n_bytes_per_read} Bytes, alles konsistent.")
    

#---------------------------------------------------------------------------------
#------------------------ Mixed read/write stress --------------------------------
#---------------------------------------------------------------------------------
@cocotb.test()
async def test_mixed_stress(dut):
    """Zufällige Mischung aus Read- und Write-Transaktionen über lange Zeit."""
    import random
    rng = random.Random(42)  # fester Seed für Reproduzierbarkeit

    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset_dut(dut)

    n_iterations = 100
    # Schattenmodell: was Python erwartet, dass in Block A steht
    # initial: die Reset-Werte aus dem RTL
   
    raw_b = dut.uut.reg_block_a.RESET_VALUES.value
    base_addr = int(dut.uut.reg_block_a.BASE_ADDR.value)
    n_regs = int(dut.uut.reg_block_a.BASE_ADDR.value)

    reset_a_local = {i: (int(raw_b) >> (i * 8)) & 0xFF for i in range(n_regs)}
    
    expected_a = {0x00 + i: v for i, v in reset_a_local.items()}

    for iteration in range(n_iterations):
        op = rng.choice(["write", "read"])

        if op == "write":
            addr  = rng.randint(0x00, 0x07)         # nur Block A (schreibbar)
            value = rng.randint(0x00, 0xFF)
            await i2c_write_single(dut, addr, value)
            expected_a[addr] = value
            dut._log.info(f"Iter {iteration}: WRITE A[0x{addr:02X}] = 0x{value:02X}")

        else:  # read
            addr = rng.randint(0x00, 0x0F)          # A oder B
            value = await i2c_read_single(dut, addr)
            dut._log.info(f"Iter {iteration}: READ  [0x{addr:02X}] = 0x{value:02X}")
            # Bei A-Adressen gegen das Schattenmodell prüfen
            if addr in expected_a:
                assert value == expected_a[addr], \
                    f"Iter {iteration}: A[0x{addr:02X}] = 0x{value:02X}, "  \
                    f"Modell sagt 0x{expected_a[addr]:02X}"

        # Nach jeder Iteration: State zurück auf IDLE?
        for _ in range(5):
            await RisingEdge(dut.clk)
        state = int(dut.uut.i2c_inst.state.value)
        assert state == S_IDLE, \
            f"Iter {iteration}: State nicht IDLE, ist {state}"

        await Timer(200, unit="us")

    # --- Finale Validierung: alle A-Register gegen das Modell ---
    for addr, expected in expected_a.items():
        value = await i2c_read_single(dut, addr)
        assert value == expected, \
            f"Final: A[0x{addr:02X}] = 0x{value:02X} != Modell 0x{expected:02X}"

    dut._log.info(f"Mixed-Stresstest bestanden: {n_iterations} zufällige Operationen, "
                  f"Schattenmodell konsistent.")