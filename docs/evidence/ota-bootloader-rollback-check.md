# Bootloader rollback check (X3, read-only)

Run 2026-10-11 with the owner present ("awake, hands off"). esptool v5.3.0, `--chip esp32c3`, by-id port. Two read-only `read-flash` calls: `0x0` (length `0x9000`: bootloader + partition table) and `0xE000` (length `0x2000`: otadata). NVS (`0x9000`–`0xE000`) was deliberately not read, because it holds the device key. Both calls exited 0 and hard-reset the X3 into its normal firmware. The raw dumps and full logs stay in the session scratchpad and are not committed.

## Findings

- The device bootloader (first 18,688 B) is byte-identical to the fork build's `.pio/build/default/bootloader.bin` (sha256 prefix `46893df6619f0c7d`). It reports ESP-IDF v5.5.5.
- That bootloader is compiled through the build's `custom_sdkconfig` hybrid framework build. The resulting framework config (`framework-arduinoespressif32-libs/esp32c3/sdkconfig`) has `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` and `CONFIG_APP_ROLLBACK_ENABLE=y`. Anti-rollback is not set. The overlay `sdkconfig.crosspoint` doesn't touch rollback.
- otadata: entry0 `ota_seq=1`, entry1 `ota_seq=0`, both with state UNDEFINED. The running slot is `ota_0` (app0 at `0x10000`, where every app-only flash went). UNDEFINED is expected for an image written by esptool rather than over the air.

## Verdict

Rollback support is **enabled at the configuration level**. This is config evidence, not a behavioral test. The real rollback is exercised on the device in t17 scenario (e). The first OTA will write `ota_1`, which boots as PENDING_VERIFY into t10's health check.
