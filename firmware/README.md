# Firmware — Air Guitar Strum

ESP32 CSI firmware, adapted from [ESP32-CSI-Tool](https://github.com/StevenMHernandez/ESP32-CSI-Tool)
(Steven M. Hernandez) and **ported to ESP-IDF v5.3.5**.

## Layout
- `active_sta/` — **RX**: connects to a WiFi AP, extracts CSI, prints `CSI_DATA,...` rows over serial. This is the receiver used for sensing.
- `active_ap/` — **TX**: acts as a WiFi access point (used only in the two-ESP32 setup).
- `_components/` — shared CSI / socket / nvs / time helpers.

## ESP-IDF v5.x port fixes (already applied)
- `esp_spi_flash.h` → `esp_mac.h` in both `main.cc` (MACSTR/MAC2STR moved).
- `active_sta/main/main.cc`: task priority `100` → `5` (FreeRTOS max is 24 on v5.x).
- `_components/csi_component.h`: `wifi_csi_config_t configuration_csi = {}` (zero-init; v5.3 added fields).
- `sdkconfig.defaults`: `CONFIG_ESP_WIFI_CSI_ENABLED=y` (required, else `esp_wifi_set_csi()` fails), plus `CONFIG_SHOULD_COLLECT_CSI=y` and `CONFIG_SEND_CSI_TO_SERIAL=y`.

## Build & flash
```bash
source ~/.espressif/tools/activate_idf_v5.3.5.sh
export PATH="$IDF_PATH/tools:$PATH"
cd firmware/active_sta
idf.py set-target esp32
idf.py -p /dev/cu.usbserial-XXXX flash
```

## ⚠️ WiFi credentials — never commit them
SSID/password live in the **generated `sdkconfig`**, which is **gitignored**. Set them with:
```bash
idf.py menuconfig   # → "ESP32 CSI Tool Config" → WiFi SSID / WiFi Password
```
Do **not** put credentials in `sdkconfig.defaults` (that file is committed).

## Two ways to run
1. **Router mode (single ESP32, recommended so far):** point `active_sta` at your home 2.4 GHz router. Strong signal (~−56 dBm on our bench). Drive a steady CSI stream by sending traffic to the ESP32's IP from a laptop, e.g. parallel pings:
   ```bash
   for i in $(seq 1 16); do ping -c 200 -i 0.1 <ESP32_IP> >/dev/null & done
   ```
2. **Two-ESP32 mode:** flash `active_ap` to a second board (TX) and `active_sta` to the RX. More controllable, but needs both boards to have healthy antennas (ours read a weak −87 dBm — suspected bad TX board).

## Known limitations / TODO
- Serial output is capped ~20 rows/s at 115200 baud (each CSI line is long). Raising `CONFIG_ESP_CONSOLE_UART_BAUDRATE` did not take effect in testing — needs investigation.
- In router mode, hand motion currently shows mostly as **packet-rate drop** (blocking) rather than graded CSI. Geometry/traffic tuning needed for cleaner per-subcarrier features.
