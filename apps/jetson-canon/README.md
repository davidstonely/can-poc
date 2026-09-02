# apps/jetson-canon — Jetson Orin, hosted C++

canon node `jetson` (address 0x01, `language: cpp`, `platform: linux-socketcan`,
`cpp_profile: hosted`). The **fully generated** port — a thin `main` over
`<ns>_port_socketcan.c`, so a failure here indicts the generator, not our glue.

- Hardware: `canon1`, `ssh jetson@canon1`
- Image: `~/mcx-monorepo` branch `throwaway/canon_poc` (Yocto tree stays there, not vendored)
- Gates: **R1** (hermetic build vs. build-time generation), **R10** (ISO-TP on the image),
  **R11** (hosted C++20 under Yocto GCC 13)

Not yet registered as a Subaya app (`suya app add`).
