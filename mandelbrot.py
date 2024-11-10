import amaranth as am
import amaranth.lib.memory
from amaranth_stdio import serial

import amaranth_boards.orangecrab_r0_2 as orangecrab

from cpu import *


class Mandelbrot(am.lib.wiring.Elaboratable):
    def __init__(self):
        self.tmp = am.Signal(1, init=0)
        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.serial = self.serial = serial.AsyncSerial(divisor=410)

        m.submodules.cpu = self.cpu = Cpu()

        mandel = convert(list(open('mandelbrot.bf').read()))
        m.submodules.prog = self.prog = am.lib.memory.Memory(shape=Op.as_shape(), depth=len(mandel), init=mandel)
        self.prp = self.prog.read_port(domain="comb")
        m.d.comb += [
                self.prp.addr.eq(self.cpu.prog_read_addr),
                self.cpu.prog_read_data.eq(self.prp.data),
        ]

        m.submodules.mem = self.mem = am.lib.memory.Memory(shape=8, depth=500, init=[])
        self.mrp = self.mem.read_port(domain="comb")
        m.d.comb += [
                self.mrp.addr.eq(self.cpu.mem_read_addr),
                self.cpu.mem_read_data.eq(self.mrp.data),
        ]

        self.mwp = self.mem.write_port()
        m.d.comb += [
                self.mwp.addr.eq(self.cpu.mem_write_addr),
                self.mwp.data.eq(self.cpu.mem_write_data),
        ]

        m.d.comb += self.mwp.en.eq(1)

        # TX
        m.d.comb += [
                self.serial.tx.ack.eq(self.cpu.tx_ack),
                self.cpu.tx_rdy.eq(self.serial.tx.rdy),
                self.serial.tx.data.eq(self.cpu.tx_data),
        ]

        platform.add_resources([
            am.build.Resource("uart", 0, am.build.Pins("0", dir="o", conn=("io", 0))),
        ])
        uart = platform.request("uart", 0).o

        m.d.comb += uart.eq(self.serial.tx.o)

        # RX
        m.d.comb += [
                self.serial.rx.ack.eq(self.cpu.rx_ack),
                self.cpu.rx_rdy.eq(self.serial.rx.rdy),
                self.cpu.rx_data.eq(self.serial.rx.data),
        ]

        platform.add_resources([
            am.build.Resource("uart1", 0, am.build.Pins("1", dir="i", conn=("io", 0))),
        ])
        uart1 = platform.request("uart1", 0).i

        m.d.comb += self.serial.rx.i.eq(uart1)

        with m.If(self.tmp == 0):
            m.d.sync += self.cpu.reset.eq(1)
            m.d.sync += self.tmp.eq(1)
        with m.Else():
            m.d.sync += self.cpu.reset.eq(0)
            m.d.sync += self.tmp.eq(1)

        return m

if __name__ == "__main__":
    orangecrab.OrangeCrabR0_2Platform().build(Mandelbrot(), do_program=True)
