# t19 evidence: X3 bring-up

Unit: Xteink X3, ESP32-C3 rev 0.4, MAC `68:c6:3a:3b:c2:4c`, 16 MB flash.

## Lock probe (2026-10-06 22:04, esptool v5.4.0 `get-security-info`)

- Secure Boot: Disabled
- Flash Encryption: Disabled, `SPI_BOOT_CRYPT_CNT` 0x0
- All key blocks `USER/EMPTY`

The unit is USB-flashable.

## Stock backup (`xteink device backup --apply`)

- 16,777,216 bytes, sha256
  `2530a86270debbfdfc95247f242eb3c61e79e3089d15810ecb72d80ee6857002`
  (verified with `sha256sum -c`), stored outside the repo under the operator's
  xteink data dir (`backups/68C63A3BC24C/`, mode 600).
- Valid image: bootloader magic `0xE9` at 0x0; stock partition table has
  `app0`/`app1` at 0x770000 each (fork uses 0x640000).
- Restore: `esptool --chip esp32c3 write-flash 0x0 <backup>.bin`.

## Flash

- Image: `firmware.factory.bin` from xteink-firmware `feat/issue-1` @ `e0aec33f`
  (env `default`), sha256
  `bfa336ba5cb0b46bb2a7b88a41dfa8cedad3b3f6f6746c19c5cab847af11ab65`.
- First attempt was interrupted mid-write (the operator was asked to wake the
  device while the flash was armed to start on port appearance; a button press
  reset the chip). Result: new bootloader and partition table, empty `app0`,
  "No bootable app partitions". The ROM loader stayed intact.
- The device re-enumerated as `/dev/ttyACM1` (ttyACM0 still held), so the retry
  loop watching ttyACM0 never fired. Recovery used the stable path
  `/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_68:C6:3A:3B:C2:4C-if00`:
  wrote 5,949,424 bytes in 20.3 s, "Hash of data verified".

## First boot (serial log)

- `Xteink probe scores: pass1=3 pass2=3 verdict=1`
- `X3 stock probe VER=FF FF FF BUSY-timeout=0 -> UC8253` (panel controller is
  UC8253, not SSD1677 as assumed in frame claim c29)
- IMU and RTC initialized
- Idle heap on home: free 141,152 B, min free 140,408 B, largest block 114,676 B
- Operator confirmed the xteink theme UI is on screen.
