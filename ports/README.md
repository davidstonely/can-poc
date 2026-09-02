# ports — hand-written platform bindings

Generated code is freestanding: it never calls the platform. A port is six functions plus
four lifecycle calls, specified by `~/oxos-canon/docs/porting.md`. Ports live here rather
than inside `apps/` because two of the three are hand-written — this is the surface under
test, not boilerplate.

| Port | canon status | Consumer |
|---|---|---|
| `linux-socketcan` | generated in full | `apps/jetson-canon` |
| `stm32` | filter table generated, **six functions hand-written** | `apps/cassette-mcu` |
| RTL endpoint | **nothing emitted**, hand-written against design §8 | `apps/detector-fpga` |

A port must **not** silently fall back to promiscuous mode when filter programming fails —
report the error. `PortSend` must not block longer than one frame time at nominal rate.
