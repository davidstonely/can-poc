# apps/detector-fpga — Agilex 5 A5EA008B (AXE5000)

Subaya app **32** (default), device row 30. canon node `fpga_main`
(address 0x04, `language: sv`, `platform: none`, 32 filter slots).

The **hand-written** port: canon emits no RTL endpoint. Its bus attachment (CAN controller
driver + single-frame ISO-TP framing) has no precedent in house — that is gate **R12**,
closed today in *simulation only* against a reference endpoint that is never emitted and
never shipped. This app is the first hardware endpoint.

- Scope is bounded to messages and registers (design §6.5)
- Fallback if it stalls: reach FPGA registers through an MCU node over AXI4-Lite
- QSPI lives on this board and is driven by the FPGA — not by the Jetson OS
