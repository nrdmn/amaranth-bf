import amaranth as am
import amaranth.lib.memory
import amaranth.lib.fifo
from amaranth.lib import enum

class Op(enum.Enum, shape=3):
    ADD = 0
    SUB = 1
    SHL = 2
    SHR = 3
    PRINT = 4
    INPUT = 5
    LOOP = 6
    LOOPEND = 7

class State(enum.Enum, shape=3):
    HALT = 0
    RESET = 1
    EXEC = 2
    LOOPFORWARD = 3
    LOOPBACK = 4

def convert(l):
    def cv(c):
        if c == '+':
            return Op.ADD
        elif c == '-':
            return Op.SUB
        elif c == '>':
            return Op.SHR
        elif c == '<':
            return Op.SHL
        elif c == '[':
            return Op.LOOP
        elif c == ']':
            return Op.LOOPEND
        elif c == '.':
            return Op.PRINT
        else:
            return Op.INPUT
    return list(map(cv, filter(lambda c: c in "+-><[].,", l)))

class Cpu(am.lib.wiring.Component):
    reset: am.lib.wiring.In(1)

    prog_read_addr: am.lib.wiring.Out(16)
    prog_read_data: am.lib.wiring.In(Op.as_shape())

    mem_read_addr: am.lib.wiring.Out(16)
    mem_read_data: am.lib.wiring.In(8)
    mem_write_addr: am.lib.wiring.Out(16)
    mem_write_data: am.lib.wiring.Out(8)

    tx_rdy: am.lib.wiring.In(1)
    tx_ack: am.lib.wiring.Out(1)
    tx_data: am.lib.wiring.Out(8)

    rx_rdy: am.lib.wiring.In(1)
    rx_ack: am.lib.wiring.Out(1)
    rx_data: am.lib.wiring.In(8)

    def __init__(self):
        self.state = am.Signal(State.as_shape(), init=State.HALT)
        self.tmp = am.Signal(16, init=0)
        super().__init__()

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.tx_fifo = self.tx_fifo = am.lib.fifo.SyncFIFO(width=8, depth=4)
        m.d.comb += [
            self.tx_ack.eq(self.tx_fifo.r_rdy),
            self.tx_data.eq(self.tx_fifo.r_data),
            self.tx_fifo.r_en.eq(self.tx_fifo.r_rdy & self.tx_rdy),
        ]

        m.d.comb += self.tx_fifo.w_data.eq(self.mem_read_data)

        m.submodules.rx_fifo = self.rx_fifo = am.lib.fifo.SyncFIFO(width=8, depth=4)
        m.d.comb += [
            self.rx_ack.eq(self.rx_fifo.w_rdy),
            self.rx_fifo.w_en.eq(self.rx_rdy),
            self.rx_fifo.w_data.eq(self.rx_data),
        ]

        with m.If(self.reset):
            m.d.sync += self.state.eq(State.RESET)

        with m.Switch(self.state):
            with m.Case(State.HALT):
                pass
            with m.Case(State.RESET):
                m.d.sync += [
                        self.prog_read_addr.eq(0),
                        self.mem_read_addr.eq(0),
                        self.mem_write_addr.eq(0),
                ]
                with m.If(self.reset == 0):
                    m.d.sync += self.state.eq(State.EXEC)
            with m.Case(State.EXEC):
                with m.Switch(self.prog_read_data):
                    with m.Case(Op.ADD):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data + 1)
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                    with m.Case(Op.SUB):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data - 1)
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                    with m.Case(Op.SHL):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                        m.d.sync += [
                                self.prog_read_addr.eq(self.prog_read_addr + 1),
                                self.mem_read_addr.eq(self.mem_read_addr - 1),
                                self.mem_write_addr.eq(self.mem_write_addr - 1),
                        ]
                    with m.Case(Op.SHR):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                        m.d.sync += [
                                self.prog_read_addr.eq(self.prog_read_addr + 1),
                                self.mem_read_addr.eq(self.mem_read_addr + 1),
                                self.mem_write_addr.eq(self.mem_write_addr + 1),
                        ]
                    with m.Case(Op.PRINT):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                        with m.If(self.tx_fifo.w_en == 0):
                            with m.If(self.tx_fifo.w_rdy == 1):
                                m.d.sync += self.tx_fifo.w_en.eq(1)
                        with m.Else():
                            m.d.sync += self.tx_fifo.w_en.eq(0)
                            m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                    with m.Case(Op.INPUT):
                        with m.If(self.rx_fifo.r_en == 0):
                            with m.If(self.rx_fifo.r_rdy == 1):
                                m.d.sync += self.rx_fifo.r_en.eq(1)
                        with m.Else():
                            m.d.comb += self.mem_write_data.eq(self.rx_fifo.r_data)
                            m.d.sync += self.rx_fifo.r_en.eq(0)
                            m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                    with m.Case(Op.LOOP):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                        with m.If(self.mem_read_data == 0):
                            m.d.sync += self.state.eq(State.LOOPFORWARD)
                    with m.Case(Op.LOOPEND):
                        m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                        m.d.sync += self.state.eq(State.LOOPBACK)
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr - 1)
            with m.Case(State.LOOPFORWARD):
                m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                m.d.sync += self.prog_read_addr.eq(self.prog_read_addr + 1)
                with m.Switch(self.prog_read_data):
                    with m.Case(Op.LOOP):
                        m.d.sync += self.tmp.eq(self.tmp + 1)
                    with m.Case(Op.LOOPEND):
                        with m.If(self.tmp == 0):
                            m.d.sync += self.state.eq(State.EXEC)
                        with m.Else():
                            m.d.sync += self.tmp.eq(self.tmp - 1)
            with m.Case(State.LOOPBACK):
                m.d.comb += self.mem_write_data.eq(self.mem_read_data)
                with m.Switch(self.prog_read_data):
                    with m.Case(Op.LOOP):
                        with m.If(self.tmp == 0):
                            m.d.sync += self.state.eq(State.EXEC)
                        with m.Else():
                            m.d.sync += self.tmp.eq(self.tmp - 1)
                            m.d.sync += self.prog_read_addr.eq(self.prog_read_addr - 1)
                    with m.Case(Op.LOOPEND):
                        m.d.sync += self.tmp.eq(self.tmp + 1)
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr - 1)
                    with m.Default():
                        m.d.sync += self.prog_read_addr.eq(self.prog_read_addr - 1)

        return m

from amaranth.sim import Simulator

class Testbench:
    def __init__(self, p, d):
        self.m = m = am.Module()

        m.submodules.cpu = self.cpu = Cpu()

        m.submodules.prog = self.prog = am.lib.memory.Memory(shape=Op.as_shape(), depth=len(p), init=p)
        self.prp = self.prog.read_port(domain="comb")
        m.d.comb += self.prp.addr.eq(self.cpu.prog_read_addr)
        m.d.comb += self.cpu.prog_read_data.eq(self.prp.data)

        m.submodules.mem = self.mem = am.lib.memory.Memory(shape=8, depth=len(d), init=d)
        self.mrp = self.mem.read_port(domain="comb")
        m.d.comb += self.mrp.addr.eq(self.cpu.mem_read_addr)
        m.d.comb += self.cpu.mem_read_data.eq(self.mrp.data)
        self.mwp = self.mem.write_port()
        m.d.comb += self.mwp.addr.eq(self.cpu.mem_write_addr)
        m.d.comb += self.mwp.data.eq(self.cpu.mem_write_data)

        m.d.comb += self.mwp.en.eq(1)

    def t1():
        t = Testbench(convert("++++++[>+++++++<-]>[]"), [0]*512)

        async def bench(ctx):
            ctx.set(t.cpu.reset, 1)
            await ctx.tick()
            ctx.set(t.cpu.reset, 0)
            await ctx.tick().repeat(1000)
            assert ctx.get(t.mrp.data) == 42

        sim = Simulator(t.m)
        sim.add_clock(1e-8)
        sim.add_testbench(bench)
        sim.run()

    def t2():
        t = Testbench(convert("+++++++++++[>++++++>+++++++++>++++++++>++++>+++>+<<<<<<-]>++++++.>++.+++++++..+++.>>.>-.<<-.<.+++.------.--------.>>>+.>-.[-]+[]"), [0]*512)

        async def bench(ctx):
            ctx.set(t.cpu.reset, 1)
            await ctx.tick()
            ctx.set(t.cpu.reset, 0)
            output = ""
            for i in range(1, 2000):
                ctx.set(t.cpu.tx_rdy, 1)
                await ctx.tick()
                if ctx.get(t.cpu.tx_ack):
                    ctx.set(t.cpu.tx_rdy, 0)
                    output += chr(ctx.get(t.cpu.tx_data))
            print(output)
            assert output == "Hello, World!\n"

        sim = Simulator(t.m)
        sim.add_clock(1e-8)
        sim.add_testbench(bench)
        sim.run()

    def t3():
        t = Testbench(convert(",[.,]"), [0]*512)

        async def bench(ctx):
            ctx.set(t.cpu.reset, 1)
            await ctx.tick()
            ctx.set(t.cpu.reset, 0)
            for i in range(1, 2000):
                await ctx.tick()
                if ctx.get(t.cpu.rx_ack):
                    ctx.set(t.cpu.rx_rdy, 1)
                    ctx.set(t.cpu.rx_data, 0x41)
                else:
                    ctx.set(t.cpu.rx_rdy, 0)

        sim = Simulator(t.m)
        sim.add_clock(1e-8)
        sim.add_testbench(bench)
        with sim.write_vcd("t3.vcd"):
            sim.run()

Testbench.t1()
Testbench.t2()
Testbench.t3()
