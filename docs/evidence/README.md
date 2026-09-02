# evidence — canon's bench validation record

**This repo is oxos-canon's bench evidence.** Its design §3.1 lists "three reference target
repos (STM32, FPGA, Jetson/Yocto) for validation" as in scope for v1; this is that item.
`v1.0.0` means *validated* and cannot be cut until these files exist.

One file per gate. Each records host, kernel, toolchain versions, the exact commands, and
their **real** output. canon's `docs/tool-validation.md` is written from these, so "it
worked" is worthless.

| Gate | What closes it |
|---|---|
| R1 | Yocto hermetic build vs. build-time generation (fallback: zipapp artifact) |
| R4 | 29-bit arbitration cost, measured on the bench |
| R5 | Bit timing + bus-load budget against real message rates |
| R10 | ISO-TP on the MC3 Yocto image — **RED** on stock L4T R36.4.7 |
| R11 | Hosted C++20 under Yocto **GCC 13** — closed only on L4T g++ 11.4 |
| R12 | First **hardware** RTL endpoint; sim-only today |

A gate that fails is a successful outcome.

## The gate that does not exist yet: shared-bus interoperability

canon has **no** gate for three heterogeneous nodes on one physical segment. E2/E3/E4 prove
byte-identical emitter output on golden vectors in a host harness; that is not
interoperability. Propose this as a new evidence item (E9 / a new R-gate) and produce it here:

- three nodes on one CAN-FD segment, one spec, one identifier layout
- three *different* controllers: Orin `mttcan` (out-of-tree), STM32 FDCAN, MCP251863 on the
  FPGA board — no common silicon, so bit timing agreement is a real result
- arbitration under contention (feeds **R4**), error frames, bus-off recovery
- per-node filter behaviour as declared in the spec

Physical-layer prerequisite: the Jetson's transceiver STB/EN pins are muxed to `dmic3`/`dmic5`
rather than GPIO. Until the DTS pinmux changes, the Jetson cannot enable its transceiver and
there is no shared bus to measure.
