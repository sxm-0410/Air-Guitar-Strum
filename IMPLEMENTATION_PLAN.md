# Implementation Plan — Air Guitar Strum

This plan is ordered by **risk, front-loaded**. The CSI stream is the highest-risk step;
nothing downstream matters until it works, so it comes first and gets a hard go/no-go gate.

---

## Phase 0 — Hardware & environment (0.5 day)

**Bill of materials**
- 2× ESP32 dev boards (one TX, one RX). Two ESP32s beat router+ESP32 for controllable CSI.
- 1× SSD1306 OLED (I²C) for live gesture label.
- 1× passive/active buzzer for the "recognized" beep.
- USB cables, breadboard, jumpers, a laptop with USB.

**Setup**
- Install ESP-IDF (v5.x) and PlatformIO (VS Code extension).
- Mount RX ESP32 at the strum location (desk edge / mic stand). Keep **line-of-sight** to TX — CSI amplitude sensitivity to hand motion depends on it.
- Fix the TX/RX geometry and mark positions (reproducibility + drift control).

**Exit criteria:** Both boards flash a blink sketch; toolchains build.

---

## Phase 1 — CSI firmware + serial pipe  ⚠️ HIGHEST RISK (3–4 days)

> Do not write CSI parsing from scratch — it's a solved problem.

**Steps**
1. Clone Steven Hernandez's **`esp32-csi-tool`** (built on the ESP-IDF `wifi_csi_rx` example).
2. Flash **TX firmware**: broadcast UDP pings at a fixed interval (~100 pkt/s).
3. Flash **RX firmware**: enable CSI callback, dump per-subcarrier amplitude/phase as CSV over serial.
4. Build a **Python serial logger** (`pyserial`) that timestamps and writes CSI rows to disk.
5. Sanity-check: wave a hand between TX/RX and confirm visible amplitude perturbation in a quick live plot.

**Deliverables**
- `firmware/tx/` and `firmware/rx/` (PlatformIO projects).
- `tools/csi_logger.py`.
- A short recording proving hand motion visibly moves the CSI.

**Exit criteria (GO/NO-GO):** A stable ~100 pkt/s CSI stream logs to disk and visibly
responds to hand motion. **Do not proceed to Phase 2 until this holds.**

---

## Phase 2 — Data collection & labeling (2–3 days)

**Protocol**
- Classes: `down_strum`, `up_strum`, `down_up_down`, `palm_mute`, `rest`, `background`
  (start with the core 4: `down_strum`, `up_strum`, `rest`, `background`).
- **≥100–150 samples per class.** Vary distance from sensor, strum speed, and hand angle. This is the step people skimp on and it tanks generalization.
- **Labeling:** key-press logger — hit a key at each strum onset so the timestamp aligns with ground truth.
- **Segmentation:** amplitude-variance onset detector auto-trims ~0.5–1 s windows; manual trim for small volumes.

**Deliverables**
- `tools/label_logger.py` (keypress → timestamped label).
- `data/raw/` recordings + `data/labels.csv`.
- `tools/segment.py` producing windowed samples in `data/windows/`.

**Exit criteria:** A balanced, labeled, windowed dataset with per-class counts reported.

---

## Phase 3 — Preprocessing + baseline (2–3 days)

> Reuse/adapt the prior indoor-CSI preprocessing pipeline.

**Pipeline**
1. Subcarrier selection — drop noisy edge subcarriers.
2. Amplitude normalization.
3. Optional Hampel filter for outlier spikes.
4. Sliding-window segmentation → tensors.

**Baseline model**
- Hand-crafted features: variance, peak count, energy → **SVM**.
- Report baseline accuracy/confusion matrix — this is the bar the CNN must clear to earn its complexity.

**Deliverables**
- `src/preprocess.py` (reusable, parameterized).
- `src/baseline_svm.py` + baseline metrics report.

**Exit criteria:** Reproducible preprocessing + a documented SVM baseline number.

---

## Phase 4 — 1D-CNN training + tuning (3–4 days)

**Architecture** (same family as the indoor-mapping project)
```
Input (window × subcarriers)
 → [Conv1D → BatchNorm → ReLU → MaxPool] × 2–3
 → Flatten/GlobalAvgPool → Dense → Softmax(n_classes)
```

**Training**
- TensorFlow/Keras on laptop. Fixed seeds. Train/val/test split (subject/session-aware to avoid leakage).
- Track accuracy, per-class precision/recall, confusion matrix.
- Light tuning: window size, subcarrier band, learning rate, #blocks. Don't over-engineer — 3 layers should suffice for ~6 classes.

**Deliverables**
- `src/train_cnn.py`, `models/cnn_v1.keras`, `reports/metrics_cnn.md`.
- Comparison table: SVM vs CNN.

**Exit criteria:** ≥85% held-out accuracy on core classes and CNN > baseline.

---

## Phase 5 — Real-time inference + feedback, Tier A (2–3 days)

**Loop**
1. Laptop reads the live serial CSI stream.
2. Applies the same preprocessing, runs the CNN on sliding windows.
3. Debounces predictions (avoid double-fire per strum).
4. Sends the recognized class back to the RX ESP32 over serial.
5. RX firmware renders the label on the **OLED** and pulses the **buzzer** on a confident recognition.

**Deliverables**
- `src/realtime_infer.py`.
- RX firmware feedback handler (`firmware/rx/` OLED + buzzer).
- Measured end-to-end latency (<300 ms target).

**Exit criteria:** Live gesture → OLED label + beep within latency budget.

---

## Phase 6 — Practice-logging layer + dashboard (2–3 days)

**Data**
- Log `(timestamp, gesture, confidence)` per recognition to a local file and/or **Supabase** (reuse existing Supabase setup).

**Dashboard**
- Strums/day, pattern accuracy over time, streaks.
- Simple web dashboard (or notebook) reading the log.

**Deliverables**
- `src/logger_sink.py` (file + optional Supabase writer).
- `dashboard/` (minimal app) with strums/day, accuracy trend, streak view.

**Exit criteria:** A dashboard rendering at least one multi-day practice streak.

---

## Phase 7 — On-device inference, Tier B (optional, 3–5 days)

> The differentiator — portfolio-grade vs class-demo.

**Steps**
1. Post-training quantize the CNN to int8.
2. Convert to a **TFLite Micro** flatbuffer; embed in RX firmware.
3. Run inference on-device; OLED/buzzer driven without the laptop.
4. Validate accuracy delta vs the float model; profile RAM/latency against ESP32 limits.

**Deliverables**
- `models/cnn_v1_int8.tflite`, embedded model header.
- `firmware/rx/` on-device inference path.
- Accuracy/latency/memory report.

**Exit criteria:** Standalone RX board classifies strums without the laptop.

---

## Proposed repository layout

```
Air-Guitar-Strum/
├── PRD.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── firmware/
│   ├── tx/                  # UDP pinger (PlatformIO)
│   └── rx/                  # CSI rx + OLED/buzzer (PlatformIO)
├── tools/
│   ├── csi_logger.py        # serial → disk
│   ├── label_logger.py      # keypress ground truth
│   └── segment.py           # onset detection + windowing
├── src/
│   ├── preprocess.py
│   ├── baseline_svm.py
│   ├── train_cnn.py
│   ├── realtime_infer.py
│   └── logger_sink.py
├── models/
├── data/                    # gitignored (raw + windows)
├── reports/
└── dashboard/
```

---

## Dependencies & stack

- **Embedded:** ESP-IDF v5.x, PlatformIO, `esp32-csi-tool`, SSD1306 driver, TFLite Micro (Tier B).
- **Host:** Python 3.11+, `pyserial`, NumPy, SciPy, scikit-learn, TensorFlow/Keras, Matplotlib.
- **Product:** Supabase (optional), a minimal web/dashboard stack.

## Cross-cutting practices
- Version models + preprocessing params together; never ship a model without its preprocessing config.
- Session-aware splits to prevent leakage.
- `.gitignore` large `data/` and model binaries (or use Git LFS / releases).
- Document the exact firmware config that produced a given dataset.
