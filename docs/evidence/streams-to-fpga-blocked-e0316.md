# Streams to the FPGA are rejected by canon — E0316

**Objective:** stream an FPGA configuration image (~1 MiB) from the Jetson over CAN to the
FPGA, which writes it to its own QSPI. Mender orchestration is **not** in scope for this
POC; the CAN-side stream is a key objective.

**Status: BLOCKED by oxos-canon, mechanically.** Not a doc-only scope note — a first-class
enforced semantic check. Recorded and not worked around, per this repo's working agreement.

## Reproduction

Minimal spec: canon's own `tests/fixtures/mc3-sv` (which ships **no** `streams.yaml`), plus
exactly the stream this project needs.

```yaml
# streams.yaml
streams:
  fpga_config_update:
    max_size: 1MiB
    chunk_verify: crc32
    resumable: true
    description: FPGA configuration image pushed from the Jetson to the FPGA, which writes it to QSPI.
    endpoints: { source: jetson, sink: fpga_main }
```

`nodes.yaml` is unmodified — `fpga_main: { address: 0x04, language: sv, platform: none, filter_slots: 32 }`.

```console
$ canon check mc3.yaml
streams.yaml:2:3: error[E0316]: SystemVerilog node 'fpga_main' cannot terminate
                  'fpga_config_update' (messages and registers only)
exit 1
```

The check is catalogued:

```
| `E0316` | `SV_NODE_UNSUPPORTED` | semantic checks over the IR | `SystemVerilog node '{node}' cannot {what} '{name}' (messages and registers only)` |
```

Measured with canon 0.7.0 (working tree, `10b6b64`) on 2026-08-31.

## Where the restriction comes from

Two independent places in the design, both deliberate:

1. **§6.5 / §8.2 / §8.3 / R12**, recorded in the Rev B changelog: *"SV nodes' bus
   participation bounded to messages and registers with a generated register service
   decoder and a hand-written RTL endpoint."* R12 adds that the SV node's framing is
   **single-frame ISO-TP** only.
2. **§3.3, explicitly out of scope:** *"FPGA Remote System Update over CAN (Altera SDM
   mailbox tunnelling). This is a separate project, not a later phase of oxos-canon. It
   would consume oxos-canon rather than live inside it… **Nothing in v1 should be shaped
   around it.**"*

So canon's v1 was scoped on the premise that FPGA update over CAN is somebody else's
project. This POC's objective is that project.

## Why this is a genuine collision, not a misunderstanding

The exclusion is narrower than the objective in one respect and wider in another:

- §3.3 excludes **Altera SDM mailbox tunnelling** — the RSU *mechanism*. This POC does not
  need that: the FPGA receives bytes and writes its own QSPI, and Mender is out of scope.
- But §6.5/E0316 excludes the FPGA node from being a **stream endpoint at all**, which is
  the part the objective actually requires. Delivering ~1 MiB to `fpga_main` means
  `fpga_main` terminates a stream, and that is exactly what E0316 forbids.

So the objective is blocked by the *node-role* restriction, not by the RSU exclusion.

## Consequence if the restriction stands: R12's single-frame framing costs 64× the round trips

R12 bounds the SV endpoint to **single-frame** ISO-TP. A CAN-FD single frame carries at most
64 bytes, so a chunk cannot exceed ~64 bytes minus the chunk header (`op`, channel, byte
offset, length, CRC-32). The stream protocol acknowledges **every chunk before the next is
sent** (§7.4).

Order-of-magnitude, for 1 MiB — **an estimate to be measured, this is R4's job**:

| | Chunks | Acknowledged round trips |
|---|---|---|
| Single-frame chunks (~60 B payload) | ~17,500 | ~17,500 |
| 4 KiB chunks (multi-frame) | 256 | 256 |

Frame count is dominated by payload either way (~16,400 frames of 64 B at 500 kbit/s
nominal / 5 Mbit/s data ≈ 3–4 s of pure frame time). What chunk size buys is **ack round
trips**: single-frame framing pays one turnaround per ~60 bytes instead of per 4 KiB. At a
1 ms endpoint turnaround that is ~17 s of pure latency versus ~0.3 s — so the transfer time
is set by the FPGA endpoint's response latency, not by the bus.

This interacts with the FF_DL finding in `r10-isotp-mc3-yocto.md`: 4 KiB chunks would also
require the ISO 15765-2:**2016** 32-bit FF_DL escape on the FPGA endpoint, since 4096 > 4095.
Single-frame framing avoids that entirely — the two constraints are consistent with each
other, and both point at the same decision.

## Options, for the planning stage

1. **canon allows SV nodes to terminate streams** — relax E0316, and give the SV emitter a
   stream sink. Largest change; makes the objective directly expressible.
2. **Keep E0316; route the image through an MCU node** — the R12 fallback shape (reach the
   FPGA via an MCU over AXI4-Lite). The MCU terminates the stream and forwards. Costs a hop
   and puts ~1 MiB through an STM32.
3. **The FPGA update lives outside canon** — as §3.3 intends, a separate project consuming
   canon for everything else. Then this POC validates canon for messages/registers and
   validates the update path as its own transport.

Option 2 is the only one that needs no canon change, and it is the one canon's own risk
register already names as the fallback. Option 1 is the only one that matches the stated
objective without an architectural hop.

**Not decided here.** Requirements and architecture belong to the planning stage.
