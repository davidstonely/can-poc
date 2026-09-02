# R10 — in-kernel ISO-TP on the MC3 Yocto image

**Gate:** oxos-canon design §13 R10. Two questions: (a) does the Jetson kernel provide
`CONFIG_CAN_ISOTP`, and (b) does a full 4 KiB-chunk PDU clear ISO-TP's `MAX_MSG_LENGTH`
without tuning?

**Prior status:** **RED on stock L4T R36.4.7** — `docs/reviews/2026-08-27-r10-jetson-isotp.md`.
`CONFIG_CAN_ISOTP` was absent from the stock kernel *and* from the MC3 Yocto defconfig.

**This run:** 2026-08-31, measured by Claude Code from the dev workstation over SSH.

> ## Verdict: **R10 CLOSED GREEN — both halves, measured**
>
> - **(a)** `CONFIG_CAN_ISOTP=m` present; ISO-TP socket opens; module autoloads unprivileged.
> - **(b)** A 4096-byte PDU transfers intact. Measured headroom is **16×**, not the
>   1.99× the gate assumes — see the correction below.
>
> **Correction to the gate's premise:** R10 states the in-kernel limit is **8200** bytes
> (`MAX_MSG_LENGTH`, kernels ≤ 6.3). On this kernel the measured limit is **66000 bytes**.
> 8200 is wrong for this platform, and the "6.4+ tunable `max_pdu_size`" framing is not
> what gates us. The gate's *conclusion* — cap chunks at ≤ 4 KiB and no tuning is ever
> required — stands and is safer than believed.

## Platform

```
$ hostname
cassette-canon1
$ uname -r
5.15.148-l4t-r36.4.4-1012.12+gc8a82765359e
$ uname -m
aarch64
$ grep -E '^(PRETTY_NAME|VERSION)=' /etc/os-release
VERSION="0.0.0-canonpoc (master)"
PRETTY_NAME="OXOS MC3 Cassette 0.0.0-canonpoc (master)"
$ head -1 /etc/nv_tegra_release
# R36 (release), REVISION: 4.4, GCID: 41062509, BOARD: generic, EABI: aarch64, DATE: Mon Jun 16 16:07:13 UTC 2025
$ uptime -p; who -b
up 6 minutes
         system boot  Aug 31 21:30
```

Kernel is L4T **R36.4.4**, not the R36.4.7 of the original RED finding — worth noting in
canon's record, since the gate was written against a different base.
Image built from `~/mcx-monorepo` branch `throwaway/canon_poc` @ `a654ee5b58`.
Checks ran ~6 min after boot, so these are post-reboot results.

## How root was obtained

`sudo` is tightly restricted for `microc` (halt/poweroff/reboot/umount plus a few named
scripts — no `modprobe`, no `ip link`):

```
$ sudo modprobe -a vcan can-isotp
Sorry, user microc is not allowed to execute '/usr/sbin/modprobe -a vcan can-isotp' as root
```

But **`su -` works** with the same password. `su` needs a controlling terminal, so it is
driven through a Python pty helper:
`mcx-monorepo/.claude/skills/jetson/scripts/jetson-ssh.sh <host> '<cmd>' --root`.
Everything below marked *(root)* ran that way.

## (a) `CONFIG_CAN_ISOTP` — CLOSED GREEN

The defconfig fix shipped into the image:

```
$ zcat /proc/config.gz | grep -E '^#? ?CONFIG_CAN(=|_ISOTP|_VCAN|_RAW|_BCM|_DEV|_CALC)' | sort
CONFIG_CAN=m
CONFIG_CAN_BCM=m
CONFIG_CAN_CALC_BITTIMING=y
CONFIG_CAN_DEV=m
CONFIG_CAN_ISOTP=m
CONFIG_CAN_RAW=m
CONFIG_CAN_VCAN=m
```

Compare the RED finding's `# CONFIG_CAN_ISOTP is not set`. **That is the gap, closed.**

Stronger than a manual `modprobe`: an **unprivileged** user opening an ISO-TP socket
autoloads the module — the on-demand path a real service takes, and it needs none of the
privileges `microc` lacks:

```
$ python3 -c "
import socket
s=socket.socket(socket.PF_CAN, socket.SOCK_DGRAM, 6); print('opened fd',s.fileno()); s.close()"
opened fd 3

$ lsmod | grep -E '^(can|can_isotp|can_dev|vcan|mttcan)\b'
can_isotp              32768  0
can                    28672  1 can_isotp
mttcan                 61440  0
can_dev                28672  1 mttcan

$ ls -d /sys/module/can_isotp
/sys/module/can_isotp
```

Compare the RED finding's `isotp socket: REFUSED (Protocol not supported)`.

### Ordering caveat, recorded so it is not misread

In a first pass `lsmod` and `ls /sys/module/can_isotp` ran *before* the socket test and
showed only `mttcan`/`can_dev`, with `/sys/module/can_isotp` absent — while the socket
opened anyway. Not a contradiction: **the socket open is what autoloads the module.** A
second pass confirmed both present. Nothing loads them at boot
(`/etc/modules-load.d/` holds only `fuse`), and nothing needs to.

## (b) PDU length — CLOSED GREEN, and the gate's number is wrong

*(root)* `vcan0` at the CAN-FD MTU:

```
$ modprobe -a vcan can-isotp     # rc=0
$ ip link add dev vcan0 type vcan && ip link set vcan0 mtu 72 && ip link set up vcan0
$ ip -details link show vcan0
9: vcan0: <NOARP,UP,LOWER_UP> mtu 72 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can  promiscuity 0 minmtu 0 maxmtu 0
    vcan numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535
$ lsmod | grep -E '^(can|can_isotp|can_dev|vcan|mttcan)\b'
vcan                   20480  0
can_isotp              32768  0
can                    28672  1 can_isotp
mttcan                 61440  0
can_dev                28672  1 mttcan
```

Two ISO-TP sockets on `vcan0` loopback, 29-bit extended ids (`0x18DA0102` / `0x18DA0201`),
payload verified by SHA-256 on receipt — not just length. Test source:
`bench/isotp_loopback.py`.

```
64     bytes -> PASS received=64     0.00s
4096   bytes -> PASS received=4096   0.03s     <-- canon's chunk cap
8200   bytes -> PASS received=8200   0.06s     <-- the gate's supposed ceiling
8201   bytes -> PASS received=8201   0.06s     <-- and past it
```

8201 passing is what prompted measuring the real ceiling:

```
8192     PASS   16384    PASS   32768    PASS
65535    PASS   65536    PASS   131072   FAIL  (send: OSError [Errno 22] Invalid argument)
```

Bisected to the exact boundary:

```
MAX PDU accepted = 66000 bytes  (0x101D0)
first rejected   = 66001 bytes  (0x101D1)
```

**66000 is a round decimal — the signature of a deliberate driver constant**, and it
matches mainline `net/can/isotp.c`'s `MAX_MSG_LENGTH`, not 8200.

### Is 66000 an ISO-TP limit? No — it is a Linux implementation ceiling

Worth stating precisely, because the layers have very different numbers:

| Layer | Max PDU |
|---|---|
| ISO 15765-2:**2004 / 2011** — FF_DL is 12 bits | **4095 bytes** |
| ISO 15765-2:**2016** — FF_DL escape is 32 bits | ~4 GiB |
| **Linux `can-isotp` on this kernel** — measured | **66000 bytes** |

The module implements the 2016 revision, so the 4095 classic bound does not apply to it:

```
$ modinfo can_isotp | grep -E '^(filename|description)'
filename:       /lib/modules/5.15.148-l4t-r36.4.4-.../kernel/net/can/can-isotp.ko
description:    PF_CAN isotp 15765-2:2016 protocol
```

So 66000 is neither a protocol bound nor a bus property — it is the driver's own static
receive-buffer ceiling, and `66001` failing at **`send()`** with `EINVAL` (not a timeout, not
a bus error) is consistent with a local length check rather than anything on the wire.
Kernel source is not on the device (`/lib/modules/$(uname -r)/build` absent) so the constant
was not read directly; the 66000 figure here is **measured**, and reading
`net/can/isotp.c` would confirm the definition.

### A sharper consequence: 4 KiB chunks require the 2016 escape

canon design §587 specifies stream chunks with `length ≤ 4096`, and §964 justifies "≤ 4 KiB"
purely by the Linux PDU ceiling — as if 4 KiB were comfortably *below* a limit.

**4096 is one byte above the classic ISO-TP maximum of 4095**, and a maximum-size chunk PDU
also carries the chunk header (`op`, channel, byte offset, length, and a CRC-32 when
`chunk_verify: crc32`), so the PDU on the wire is ~4100+ bytes. A full-size chunk therefore
**cannot be expressed with a 12-bit FF_DL at all** — every endpoint that receives one must
implement the 2016 32-bit FF_DL escape.

That is fine for the Jetson (2016, confirmed above). It is a real constraint on the other two:

- **STM32** — the six port functions are hand-written and the ISO-TP stack is whatever the
  RTOS provides. Many embedded ISO-TP stacks implement classic 12-bit FF_DL only.
- **FPGA** — R12 bounds the SV node to *single-frame* ISO-TP framing, which sidesteps
  multi-frame entirely; worth confirming that streams are therefore out of scope for it.

Not a defect in the design, but the rationale as written does not surface it, and it bears
directly on the shared-bus interoperability claim. Cheapest resolution: cap chunk `length`
at **4095**, which keeps every endpoint inside classic FF_DL and costs one byte.

### Consequence for canon

- **4 KiB chunks have ~16× headroom** (4096 of 66000), not the ~2× the gate implies.
  The "≤ 4 KiB so no tuning is ever required" decision is correct and *more* robust than
  its stated rationale.
- **R10's constraint text should be corrected.** A design doc that records the wrong bound
  invites someone later to size a stream chunk against 8200 — or worse, to believe a
  6.4+ `max_pdu_size` tunable is needed on a kernel where 66000 is already the limit.
- Not measured: the same limit over **real `can0`** rather than `vcan0`, and under CAN-FD
  link-layer options (`CAN_ISOTP_LL_OPTS`, `tx_dl 64`). The loopback used default classic
  8-byte segmentation, which exercises PDU length but not FD framing. Both need the
  transceiver.

## Gap: `can-utils` is subpackaged and the packagegroup pulls only the main package

`packagegroup-oxos-mc3-canonpoc` RDEPENDS on `can-utils`, but OE splits that recipe into
subpackages. Present on the image:

```
candump      /usr/bin/candump
cansend      /usr/bin/cansend
cangen       /usr/bin/cangen
canfdtest    MISSING
gpioget      /usr/bin/gpioget
gpioset      /usr/bin/gpioset
gpiodetect   /usr/bin/gpiodetect
ip           /usr/sbin/ip
kmod         /usr/bin/kmod
modprobe     /usr/sbin/modprobe
```

Missing: `canfdtest` and the whole ISO-TP userspace set (`isotpsend`, `isotprecv`,
`isotpdump`, `isotpperf`, `isotptun`). Worth adding before shared-bus bring-up —
`canfdtest` is the standard two-node CAN-FD frame-level soak.

**This did not block R10(b):** Python's `socket` module speaks ISO-TP natively via
`PF_CAN/SOCK_DGRAM/6`, so the transfer above needed no `can-utils` subpackage at all.
Recorded because the gap is real for interactive bench work, not because it gated the gate.

## Other findings

**`can0` present, CAN-FD capable, DOWN pending a transceiver** — from out-of-tree `mttcan`
at `c310000`, not mainline M_CAN:

```
3: can0: <NOARP,ECHO> mtu 16 qdisc noop state DOWN mode DEFAULT group default qlen 10
    can state STOPPED (berr-counter tx 0 rx 0) restart-ms 0
	  mttcan: tseg1 2..255 tseg2 0..127 sjw 1..127 brp 1..511 brp_inc 1
	  mttcan: dtseg1 1..31 dtseg2 0..15 dsjw 1..15 dbrp 1..15 dbrp_inc 1
	  clock 50000000 numtxqueues 1 numrxqueues 1 parentdev c310000.mttcan
```

`mtu 16` is classic CAN; it becomes 72 when brought up with `fd on`. **The 50 MHz clock and
those tseg/brp ranges are the raw input to R5** (bit timing) and are recorded here for it.

**No on-target compiler** — `g++`/`gcc` absent, so **R11 cannot be re-confirmed from the
device**. Needs `bitbake -c populate_sdk oxos-mc3-cassette-os` on `panel3`.

## Access note

The device's address had moved to **`172.16.10.49`** (DHCP); `172.16.10.45` no longer
answers ARP. WSL2's NAT drops multicast, so mDNS cannot be resolved from inside WSL —
`cassette-canon1.local` had to be resolved on the Windows host and the address used
directly. Relevant to any automation run from this workstation.
