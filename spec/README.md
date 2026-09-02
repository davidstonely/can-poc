# spec — canon interface specification for this POC

The YAML source of truth. `canon.lock` **is committed** — it keeps identifier allocation
stable across regeneration. Generated output goes to `gen/` and is never committed.

```bash
canon check .../mc3.yaml     # validate — all errors at once, file:line:column
canon lock  .../mc3.yaml     # update the lockfile; commit the result
canon ids   .../mc3.yaml     # allocated identifier table
```

Reference spec: `~/oxos-canon/tests/fixtures/mc3-full/`.

**Open:** which spec node `apps/cassette-mcu` plays. The MC3 spec declares four `stm32`
nodes — `charger_mcu`, `display_mcu`, `emitter_mcu`, `monoblock` — and none is named
"cassette". Adopting an existing node vs. adding one changes what lives here; adding one
exercises the spec language, `canon lock`, and the E8 compatibility gate deliberately.
