# bench — bring-up scripts and captures

```bash
sudo modprobe -a vcan can-isotp   # -a matters: without it can-isotp is treated as a
                                  # PARAMETER of vcan and silently never loads
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 mtu 72     # CAN-FD MTU; the default 16 is classic CAN
sudo ip link set up vcan0
```

Hardware: `canon1`, Jetson Orin, `ssh jetson@canon1`. The stock MC3 cassette image ships
**no** CAN userspace; `packagegroup-oxos-mc3-canonpoc` on `throwaway/canon_poc` adds
`can-utils`, `iproute2`, `kmod`, `libgpiod`.

## Root on the Jetson

`sudo` is restricted for `microc` (halt/poweroff/reboot/umount + a few named scripts — no
`modprobe`, no `ip link`). **`su -` works** with the same password; it needs a controlling
terminal, so drive it through the pty helper:

```bash
bash ~/mcx-monorepo/.claude/skills/jetson/scripts/jetson-ssh.sh <host> '<cmd>' --root
```

Address is DHCP and moves. WSL2's NAT drops multicast, so mDNS cannot be resolved from
inside WSL — resolve `cassette-canon1.local` on the Windows host and use the address.

## isotp_loopback.py

Two ISO-TP sockets on `vcan0`, 29-bit extended ids, SHA-256 verified on receipt. Needs no
`can-utils` subpackage — Python speaks ISO-TP via `PF_CAN/SOCK_DGRAM/6`. Measured the real
PDU ceiling on L4T 5.15 at **66000 bytes**, not the 8200 canon's R10 assumes.
