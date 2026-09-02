# can-poc — CAN proof-of-concept for MC3

A three-target CAN-FD bring-up. Its real purpose is **validation of tooling**, not
shipping firmware: this repo is the first bench exercise of three things that have
never been used together, and finding where they break is the deliverable.

| Validating | First-ever use | Status coming in |
|---|---|---|
| Subaya / `suya` | 2nd project on the platform, 1st multi-target | see *Subaya* below |
| oxos-canon | 1st consumer outside its own test suite | feature-complete, **NOT validated** |
| MC3 Yocto on Jetson Orin | 1st CAN userspace on the image | image builds, ISO-TP unconfirmed |

## The three targets

There is **no MC3 spec yet** — `~/oxos-canon/tests/fixtures/mc3-full/` is a canon **test
fixture**, so its node names and addresses are illustrative. This POC authors a
POC-specific spec shaped toward the predicted MC3 spec (REQ-48). Shape:

| Node | Addr | Lang | canon platform / port | This repo's target |
|---|---|---|---|---|
| `jetson` | 0x01 | cpp (hosted) | `linux-socketcan` — **generated in full** | Jetson Orin, MC3 Yocto |
| `cassette_mcu` | 0x02… | c | `stm32` — filters generated, **6 port fns hand-written** | STM32C562RE (NUCLEO-C562RE) |
| `fpga_main` | 0x04 | **c** (Nios V) | 4th port type — bare-metal C over SPI, **hand-written** | Agilex 5 A5EC008B (AXE5000) |

Network: CAN-FD, 500 kbit/s nominal, 5 Mbit/s data, 29-bit extended ids, BRS on.

The three targets are not three copies of one problem — they exercise the three
*different* canon port maturity levels, which is why this POC is worth running at all.

**Architectural boundary:** the Jetson only talks CAN. QSPI lives on the FPGA board and
is driven by the FPGA, not by the Jetson OS — no MTD/SPI tooling belongs in the image.
(Source: the `packagegroup-oxos-mc3-canonpoc.bb` scope note.)

## The headline claim: one shared CAN bus

**Jetson, FPGA and MCU sit on a single physical CAN-FD segment.** That is the thing being
validated, and oxos-canon is a large part of why it should work: three independently-built
things, generated from one spec, must agree on the wire. canon's own scoping rule is
"interfaces where two independently-built things must agree" — this is the first time that
claim meets copper.

**No existing canon gate covers it.** E2/E3/E4 prove that generated C, C++ and SystemVerilog
produce *byte-identical output on golden vectors* — a statement about emitters, in a host
harness. Byte-identity is not interoperability. A shared segment adds everything the
harness cannot: real arbitration under contention, three different CAN controllers agreeing
on bit timing, per-node filter behaviour, error frames and bus-off recovery, and the fact
that all three must share one permanent identifier layout (R6). Every one of those is
untested today.

Three different controllers is the crux — same bus, no common silicon:

| Node | Controller | Notes |
|---|---|---|
| Jetson Orin | NVIDIA **out-of-tree `mttcan`** (DT `mttcan@c310000`) | CAN-FD confirmed on `canon1`; mainline `CONFIG_CAN_M_CAN` is **off**, `CONFIG_CAN_CALC_BITTIMING=y` |
| STM32C562RE | FDCAN peripheral | filter slots declared in the spec (`E0405` proves sufficiency) |
| Agilex 5 | hand-written endpoint | the MCP251863's own SPI register map is a board-local hand-written driver *below* the generated layer, deliberately outside canon's scope |

They must agree on: 500 kbit/s nominal, 5 Mbit/s data, sample points 0.80/0.75, 29-bit
extended ids, BRS on — which is precisely why **R5** (bit timing unspecified) stops being
academic here.

**Known pending physical-layer problem:** on the Jetson the CAN transceiver STB/EN pins are
muxed to `dmic3`/`dmic5` rather than GPIO, so they cannot be driven as-is. `libgpiod-tools`
is in the canon-poc packagegroup to poke them, but the DTS pinmux still needs changing. A
transceiver that cannot be enabled means no shared bus at all, so treat this as gating.

The dev boards constrain which GPIOs are available, and the expectation is that what is
needed is there. **Deferred:** specific pin selection, the pinmux change, and requirements
belong to the planning stage — do not design them ahead of it.

## Key objective: stream an FPGA config image over CAN

The **primary target of the stream primitive is the FPGA**: push a configuration image
(~1 MiB) from the Jetson over CAN; the FPGA writes it to its own QSPI. Mender
orchestration is **out of scope** for this POC — the CAN-side stream is the objective.

**BLOCKED by canon, mechanically** — `error[E0316] SV_NODE_UNSUPPORTED`: a SystemVerilog
node cannot terminate a stream (§6.5/R12 bound SV nodes to messages and registers, and
§3.3 puts FPGA Remote System Update over CAN out of scope entirely). Filed as
`davidstonely/oxos-canon#9`; the exclusion is agreed to be a mistake. Full reproduction and
the throughput consequences of R12's single-frame bound are in
`docs/evidence/streams-to-fpga-blocked-e0316.md`.

Held blocked, not worked around. Options (route via an MCU hop, or move the update path
outside canon) belong to the planning stage.

### QSPI: A/B images plus an 18 MB calibration region in 32 MB

The FPGA normally **boots from QSPI**; the objective is to make that image field-updatable
over CAN, with **A/B slots** and fallback. The same flash must also hold the detector
**gain map** — 3k x 3k at 2 bytes/pixel, ~18 MB, the size of one detector image — and it
must be retrievable.

The AXE5000 configures from a **256 Mbit (32 MB) QSPI** "with space for additional data
storage" (AXE5000 User Guide p4, rag doc 349). So capacity is the binding constraint:

| | |
|---|---|
| QSPI total | 32 MB |
| Gain map | ~18 MB |
| Left for **all** config | **~14 MB** |
| A/B, no factory image | ~7 MB per slot |
| A/B + factory image | ~4.6 MB per slot |

Whether an Agilex 5 bitstream fits in that decides whether the plan is feasible on this
board. **Blocked on data:** the real `.rbf` size (one Quartus build), and the board guide
names the FPGA `A5EC008BM16AE6S` while the Subaya catalog has `A5EA008B` — different
variants; resolve before sizing anything.

Notes that shape the design:

- **A/B should use Altera RSU**, not an invented scheme, and the cal region should be an
  RSU sub-partition rather than an unmanaged offset — an unmanaged region is liable to be
  clobbered by a future `quartus_pfg` layout change.
- **This does not conflict with canon §3.3.** canon excludes SDM mailbox *tunnelling* from
  itself; the split is canon streams the bytes and the FPGA-side RSU write plus slot switch
  is board-local, below the generated layer — the same boundary as the MCP251863 driver. So
  `oxos-canon#9` only needs SV nodes to *terminate a stream*.
- **The 128 Mb (16 MB) HyperRAM is a staging buffer** for a received image before it is
  committed to QSPI. Volatile, so it cannot hold cal data, but it decouples the slow CAN
  transfer from the flash write.
- **18 MB over CAN takes minutes**, not seconds (~60 s at theoretical line rate before
  ISO-TP flow control, per-chunk acks and contention). If detector images reach the Jetson
  over a faster link, the gain map probably belongs on that path with CAN carrying only the
  request. Open decision on REQ-31.

Requirements: REQ-12 (boot + field update), REQ-28 (A/B), REQ-29 (memory map), REQ-30
(capacity), REQ-31 (gain map).

## Working agreements

### Stay blocked on purpose

When platform or tooling breaks, **do not work around it.** A workaround destroys the
reproduction that its fix has to be verified against. Instead:

1. Capture the exact failing commands, output, and **real** exit codes into a baseline file.
2. File an issue (routing below).
3. Stop, and say what is blocked.

Offer a workaround only as an explicitly-labelled option; never apply one unasked.
Current preserved fixture: `.subaya-baseline-2026-08-31.txt`.

### Verify a finding before filing it

Two false positives have already been caught this way. In particular: **`$?` after a
pipe reports the last element of the pipeline, not your command.** `cmd | head; echo $?`
reports `head`. Redirect to files and check the real status instead. (This trap is itself
`Seiraiyu/subaya-platform#585`.)

### Where issues go

| Finding in | Repo | `gh` account |
|---|---|---|
| Subaya platform, `suya` CLI, planner skills | `Seiraiyu/subaya-platform` | `stonelyd` |
| oxos-canon (generator, spec language, ports) | `davidstonely/oxos-canon` (private, ADMIN) | `davidstonely` |
| MC3 Yocto image, recipes, defconfig | `oxosmedical/mcx-monorepo` (private, WRITE) | `davidstonely` |

```bash
gh auth switch --user stonelyd      # file platform issues
gh auth switch --user davidstonely  # ALWAYS switch back for project work
```

## Subaya

Project **348** (`can-poc`), workspace 154, org 243, host `subaya-dev.com`.
Context resolves from `.subaya/config.toml` (machine-local, gitignored) — no `--project`
flag needed. Two apps are registered server-side: `apps/detector-fpga` (Agilex, default)
and `apps/cassette-mcu` (STM32, `ecosystem: stm32-cube`). A Jetson app is not yet
registered.

`suya doctor` exits 0. **Blocked:** no repo connected — the GitHub App installation
(`158042761`) is orphaned; Subaya never bound it to org 243. Held deliberately as the
repro for `subaya-platform#640`. Do not uninstall/reinstall the App.

No design profile exists yet, so the design phase (`brainstorm-fpga`) has not run.

## oxos-canon

`~/oxos-canon` — one versioned YAML spec generates C, C++, SystemVerilog, docs, DBC and
golden vectors, so firmware, Jetson services, FPGA and the controlled document cannot
disagree.

**Integration contract** (`docs/tool-validation.md`, `docs/porting.md`):

- Consumers **pin a release tag and generate at build time. Nothing generated is committed.**
  Pin **`v0.7.0`** (tag pending as of 2026-08-31 — the record is filled; the newest cut tag
  is `v0.6.0`). Do **not** pin a branch as a workaround: R1 tests a *hermetic* Yocto build,
  which fetches a pinned `SRC_URI` with a checksum, so an immutable tag is a prerequisite
  for the first gate rather than a nicety.
- `canon.lock` **is** committed — it keeps identifier allocation stable across regeneration.
- Generated code is freestanding: it never calls the platform. The port is six functions
  plus four lifecycle calls, specified in `docs/porting.md`. A port must **not** fall back
  to promiscuous mode when filter programming fails — report the error.

**Status honestly stated by its own record:** v0.7.0 is *feature-complete and NOT YET
VALIDATED*. There is **no bench evidence of any kind** — nothing has run against real CAN
hardware, a real STM32, or a real FPGA. Open gates that this POC touches:

- **R10 — RED.** `CONFIG_CAN_ISOTP` absent from stock L4T. Fixed in the MC3 Yocto
  defconfig; **not re-confirmed on that image**. Every directed service (register
  read/write, command invoke, stream chunks) rides ISO 15765-2, so R10 gates most of the POC.
- **R11 — closed on L4T, needs re-confirming on the Yocto image** (hosted C++20 / `std::span`).
- **R12 — simulation only.** No hardware RTL endpoint exists.
- **R1, R2, R4, R5 open** — Yocto hermetic build, RTOS choice, bus load, bit timing.

### This repo *is* canon's bench evidence

Not a consumer that happens to generate findings — **the** bench evidence. canon's design
§3.1 lists "three reference target repos (STM32, FPGA, Jetson/Yocto) for validation" as in
scope for v1, and this is that item. Its record's "no bench evidence of any kind" is the
gap this project closes, and `v1.0.0` cannot be cut until it does.

So evidence is the primary output, not a byproduct. Shape it to close named gates:

| Gate | What closes it here | Where |
|---|---|---|
| **R1** | Does a Yocto hermetic build permit generating at build time? Fallback is a zipapp release artifact | `docs/evidence/r1-*` |
| **R4** | 29-bit arbitration cost — "measure on the bench in Phase 7" | `docs/evidence/r4-*` |
| **R5** | Real bit timing + bus-load budget against actual message rates | `docs/evidence/r5-*` |
| **R10** | Re-confirm ISO-TP on the **MC3 Yocto image** (RED on stock L4T) | `docs/evidence/r10-*` |
| **R11** | Re-confirm hosted C++20 under Yocto **GCC 13** (closed on L4T g++ 11.4) | `docs/evidence/r11-*` |
| **R12** | First **hardware** RTL endpoint — sim-only today; FPGA register access unproven | `docs/evidence/r12-*` |

R2 (RTOS choice) and R3 (an RTL engineer reviewing generated output on timing/reset) are
decisions and reviews rather than bench runs, but both are exercised by this POC's targets.

An evidence file records the host, kernel, toolchain versions, the exact commands, and
their **real** output — canon's record is written from these, so "it worked" is worthless.
A gate that fails is a successful outcome of this project.

```bash
cd ~/oxos-canon && uv run canon --version     # 0.7.0
canon check spec/mc3.yaml                     # validate; all errors at once, file:line:col
canon lock  spec/mc3.yaml                     # update canon.lock — commit it
canon emit c   spec/... -o gen/ --node <node>
canon emit cpp spec/... -o gen/ --profile hosted
canon vectors  spec/... -o gen/               # golden vectors + conformance harnesses
```

## Jetson / MC3 Yocto

- Hardware: **`canon1`**, Jetson Orin, `ssh jetson@canon1`. Stock is L4T R36.4.7,
  kernel 5.15.148-tegra, Ubuntu 22.04, g++ 11.4.
- Image source: `~/mcx-monorepo`, branch **`throwaway/canon_poc`** (3.4 GB monorepo; the
  Yocto tree is `mcx-infrastructure/mc3-yocto-os/layers/meta-oxos-mc3/`).
  Its commits are marked *THROWAWAY — do not merge to main*.
- That branch already: sets `CONFIG_CAN_ISOTP=m` in the MC3 defconfig (the R10 fix), adds
  `packagegroup-oxos-mc3-canonpoc` (`can-utils`, `iproute2`, `kmod`, `libgpiod` — the stock
  cassette image ships **no** CAN userspace), and builds a full image.

Bench CAN setup, and the trap that wasted a cycle upstream:

```bash
sudo modprobe -a vcan can-isotp   # -a matters: without it can-isotp is treated as a
                                  # PARAMETER of vcan and silently never loads
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 mtu 72     # CAN-FD MTU; the default 16 is classic CAN
sudo ip link set up vcan0
```

**The Yocto tree is not vendored here.** This repo references the monorepo branch; image
work happens there. Only what is specific to this POC lives in this repo.

## Decisions recorded (2026-09-02)

Full rationale lives on the requirements and in design docs 202/203; these are the
one-liners so nobody re-litigates them.

- **RSU over CAN via the Mailbox Client IP is the primary objective** (REQ-12), not a
  subgoal. §4.5.5's non-HPS path applies — `A5EC008B` has no HPS.
- **Nios V hosts the FPGA's CAN endpoint and RSU host**, so `fpga_main` is a canon
  `language: c` node, not `sv`. That is what makes `E0316` inapplicable and unblocks
  streams to the FPGA without waiting on `oxos-canon#9`. **Soft** pending the Nios V ↔
  AXI4-Lite investigation (design 202 Q1).
- **No RTOS on the Nios V** (REQ-54) — bare-metal superloop, ISR-driven CAN FIFO drain.
  CAN (SPI) and flash (Avalon/mailbox) are independent hardware, so the ~6 ms FIFO
  deadline and tens-of-ms erases do not contend.
- **Zephyr on the STM32** (REQ-20), overriding the profile's bare-metal default — for its
  in-tree ISO-TP, upstream `nucleo_c562re` support with an onboard transceiver, and the
  task-watchdog subsystem REQ-34 needs.
- **No bootloader at all on the MCU** (REQ-20 notes, design 203 §7) — flat image, no
  reserved slots. A knowing departure from corpus B.4.
- **The gain map travels over MIPI CSI-2, not CAN** (REQ-31). CSI-2 is one-way
  detector→Jetson, the right direction and orders of magnitude faster. CAN carries only
  the request, so the stream primitive is sized for the ~1 MB config image.
- **The factory image is JTAG recovery only** (design 202 Q4) — no CAN→SDM path, and none
  will be built. CAN update runs from an application image. Both slots bad ⇒ JTAG.
- **No HyperRAM staging** (REQ-11) — chunks go straight to QSPI. Erase the destination
  slot once up front, then program incrementally.
- **Jetson apps are out of Subaya's target scope** (REQ-50). No Subaya App for the Jetson;
  its requirements stay project-scoped.
- **The Yocto SDK and the Jetson app build live on the Ubuntu box (panel3)**, not on the
  Jetson (REQ-24). The image ships no compiler and must stay that way — it is one of the
  things under validation. The Jetson keeps the runtime only; `gdbserver` for debugging.
- **POC-specific canon spec**, shaped toward the predicted MC3 spec (REQ-48). There is no
  MC3 spec yet — `oxos-canon/tests/fixtures/mc3-full/` is a *test fixture*.
- **canon is extended to fit the design**, not worked around. Changes needed are listed in
  design 202 Q2.

## Repo layout

```
spec/                     canon YAML for this POC + canon.lock (committed)
apps/detector-fpga/       Agilex 5 — Nios V C endpoint + RSU host, Subaya app 32
apps/cassette-mcu/        STM32C562RE — Zephyr, 6 port fns hand-written, Subaya app 33
apps/jetson-canon/        Jetson hosted C++ — thin main over the generated socketcan port
                          (NOT a Subaya app — out of scope by decision, REQ-50)
ports/                    hand-written port implementations, one dir per platform
bench/                    bring-up scripts, vcan setup, candump captures, run records
docs/decisions/           recorded decisions for this POC
docs/evidence/            bench evidence — the output that feeds canon's validation record
gen/                      GENERATED, gitignored — never committed
.subaya/                  machine-local project binding, gitignored
```

`apps/*` paths match what Subaya already has registered; keep them in sync with
`suya app list`.

## Conventions

- Never commit generated output. `gen/` is ignored; `canon.lock` is not.
- Record bench runs as evidence files with host, kernel, tool versions and real command
  output — canon's validation record is written from these, so "it worked" is not enough.
- Prefer `bash` for file inspection and edits in this repo (`cat`, `sed -n`, `grep`).
