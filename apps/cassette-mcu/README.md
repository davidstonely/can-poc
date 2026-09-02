# apps/cassette-mcu — STM32C562RE (NUCLEO-C562RE)

Subaya app **33**, `ecosystem: stm32-cube`, device row 31.

The **half-generated** port, by design: `<ns>_stm_filters.h` states four facts and programs
nothing, and the six port functions are hand-written for this platform (they live in
`../../ports/`). The generated `<ns>_port_zephyr.c` is a convenience and is **not** a
supported binding.

- Gate **R2** — RTOS undecided; the freestanding core makes this deferrable
- Open: which spec node this plays (see `spec/README.md`)
