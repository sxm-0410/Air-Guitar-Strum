# 🎸 Air Guitar Strum

**Recognize air-guitar strumming gestures from WiFi signals — no camera, no wearables, no instrument.**

Air Guitar Strum uses **WiFi Channel State Information (CSI)** to sense hand motion. Two
ESP32 boards form a transmitter/receiver pair; as your hand strums through the radio
field between them, it distorts the channel. A lightweight **1D-CNN** classifies that
distortion into strum gestures in real time, drives an **OLED + buzzer** for instant
feedback, and logs your practice to a **consistency dashboard**.

> Motion sensing, not audio. It reads *how* you strum, not *what* you play.

---

## ✨ Features

- 📡 **WiFi CSI sensing** — ESP32 TX/RX pair, ~100 packets/sec CSI stream.
- 🧠 **1D-CNN gesture classifier** — down-strum, up-strum, patterns, palm-mute, rest, background.
- ⚡ **Real-time feedback** — OLED gesture label + buzzer beep, <300 ms end-to-end.
- 📊 **Practice dashboard** — strums/day, pattern accuracy, streaks (local file / Supabase).
- 🔬 **SVM baseline** — proves the CNN earns its complexity.
- 🚀 **On-device stretch goal** — quantized TFLite Micro inference on the ESP32 itself.

---

## 🧩 How it works

```
 ┌──────────┐   WiFi packets    ┌──────────┐   serial CSI    ┌──────────┐
 │ TX ESP32 │ ────────────────▶ │ RX ESP32 │ ──────────────▶ │  Laptop  │
 │ (pinger) │  (hand distorts   │ (CSI rx) │  (amp/phase)    │ inference│
 └──────────┘   the channel)    └────┬─────┘                 └────┬─────┘
                            OLED /    │  ▲ result over serial      │
                            buzzer ◀──┘  └────────────────────────┘
                                                                   ▼
                                                     Practice log + dashboard
```

Your hand moving through the TX→RX radio path perturbs the per-subcarrier CSI amplitude.
Those perturbations are windowed, preprocessed, and classified into strum gestures.

---

## 🛠️ Hardware

| Component | Purpose |
|---|---|
| 2× ESP32 dev board | TX pinger + RX CSI receiver |
| SSD1306 OLED (I²C) | Live gesture label |
| Buzzer | "Recognized" beep |
| Laptop (USB) | Logging, training, inference (Tier A) |

Keep **line-of-sight** between TX and RX — CSI sensitivity to hand motion depends on it.

---

## 📦 Tech stack

- **Embedded:** ESP-IDF v5.x · PlatformIO · [`esp32-csi-tool`](https://github.com/StevenMHernandez/ESP32-CSI-Tool) · TFLite Micro (on-device stretch)
- **ML / Host:** Python 3.11+ · pyserial · NumPy/SciPy · scikit-learn · TensorFlow/Keras
- **Product:** Supabase (optional) · minimal web dashboard

---

## 🚀 Getting started

> ⚠️ The CSI stream is the highest-risk step. Get it working and validated **before** anything else.

1. **Flash firmware** — flash the TX pinger and RX CSI receiver (see [`firmware/`](firmware/)), built on the ESP32-CSI-Tool.
2. **Stream CSI** — run the serial logger and confirm a stable ~100 pkt/s stream that visibly reacts to hand motion:
   ```bash
   python tools/csi_logger.py --port /dev/tty.usbserial-XXXX
   ```
3. **Collect data** — record ≥100–150 samples per gesture with the keypress labeler, varying distance/speed/angle.
4. **Preprocess + train** — run the preprocessing pipeline, the SVM baseline, then the 1D-CNN.
5. **Go real-time** — stream → infer → OLED/buzzer feedback.
6. **Log & review** — log recognitions and open the practice dashboard.

Full details in the [Implementation Plan](IMPLEMENTATION_PLAN.md).

---

## 🎯 Gesture classes

`down_strum` · `up_strum` · `down_up_down` · `palm_mute` · `rest` · `background`

Core MVP set: `down_strum`, `up_strum`, `rest`, `background`.

---

## 🗺️ Roadmap

- [ ] Phase 1 — CSI firmware + serial pipe (stable stream)
- [ ] Phase 2 — Labeled dataset across all classes
- [ ] Phase 3 — Preprocessing + SVM baseline
- [ ] Phase 4 — 1D-CNN trained to ≥85% held-out accuracy
- [ ] Phase 5 — Real-time OLED/buzzer feedback (Tier A)
- [ ] Phase 6 — Practice-logging dashboard
- [ ] Phase 7 — On-device TFLite Micro inference (Tier B, stretch)

---

## 📚 Documentation

- [Product Requirements (PRD.md)](PRD.md)
- [Implementation Plan (IMPLEMENTATION_PLAN.md)](IMPLEMENTATION_PLAN.md)

---

## 🙏 Acknowledgements

- [ESP32-CSI-Tool](https://github.com/StevenMHernandez/ESP32-CSI-Tool) by Steven M. Hernandez — CSI extraction firmware.
- Espressif ESP-IDF `wifi_csi_rx` example.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
