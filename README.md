# VeSync with dual-basket air fryer support

A custom replacement for Home Assistant's built-in `vesync` integration (copied from core
2026.10.4) that adds the **Cosori Dual Blaze (`CAF-TF101S` / `CAF-TF102S`)** and the
**Turbo Tower Pro (`CAF-DC111S-AEU`)** air fryers. All your other VeSync devices keep working
as they do in core.

Only the Dual Blaze read path has been checked on a real device (a `CAF-TF102S`). Everything
else (program limits, recipe names, the Turbo Tower Pro) comes from
[charlie508010/pyvesync `proposal/device-fixes`](https://github.com/charlie508010/pyvesync/tree/proposal/device-fixes)
(pyvesync PRs [#564](https://github.com/webdjoe/pyvesync/pull/564),
[#552](https://github.com/webdjoe/pyvesync/pull/552) and
[#536](https://github.com/webdjoe/pyvesync/pull/536)) and is untested on the TF102S.

## Entities per air fryer

| Kind | Entities |
| --- | --- |
| Sensors | status, set temperature and remaining time per basket; program; set cooking time; remaining time including waiting |
| Selects | program per basket (Dry and Proof only on the Turbo Tower Pro) |
| Numbers | temperature and time per basket, limited by the chosen program |
| Buttons | prepare / stop per basket; prepare both the same; prepare both to finish together; stop both; refresh now |

Choose program, temperature and time, then press **prepare**. The fryer still needs its
Start button pressed. Prepare stops the basket's current program first, as the fryer refuses
a new program on a basket that has one. The chosen values reset on a Home Assistant restart.

## Polling

Every 60 seconds (core's interval, set by VeSync's daily API quota of
`3200 + 1500 × devices`). While a basket is `cooking` the fryer is polled every 10 seconds;
other devices still update once a minute. After 2 hours of continuous `cooking` it falls back
to 60 seconds.

## Install

1. HACS → Custom repositories → add `https://github.com/fma965/ha-vesync-fryer` as an
   **Integration**.
2. Download it and restart Home Assistant. Home Assistant installs the pinned pyvesync fork
   from GitHub on startup, so it needs internet access and `git`.
3. Your existing VeSync config entry and entity IDs are kept (entity unique IDs are
   `<cid>-zone_1_status`, `zone_1_temperature`, `zone_1_remaining` and the same for zone 2).

To go back to core's integration, remove the repository in HACS, delete
`custom_components/vesync` and restart.

## Updating pyvesync

The pin is in `custom_components/vesync/manifest.json`. The fork is
[fma965/pyvesync](https://github.com/fma965/pyvesync) (`tf102s-on-device-fixes`): charlie508010's
branch plus one commit that maps the TF101S/TF102S to the multi-chamber fryer class.

## Licence

Apache-2.0, as Home Assistant core. See `LICENSE` and `NOTICE`.
