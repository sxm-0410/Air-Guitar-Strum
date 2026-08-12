# Product Requirements Document — Air Guitar Strum

**Version:** 0.1
**Status:** Draft
**Last updated:** 2026-08-12

---

## 1. Overview

**Air Guitar Strum** is a WiFi-sensing system that recognizes strumming gestures in
mid-air — no instrument, no wearables, no camera — by reading the Channel State
Information (CSI) of WiFi signals distorted by hand motion. Two ESP32 boards form a
transmitter/receiver pair; a lightweight 1D-CNN classifies the CSI stream into strum
gestures in real time. On top of the classifier sits a practice-logging layer that turns
the sensing demo into a small product: a "practice consistency" dashboard tracking
strums per day, pattern accuracy, and streaks.

### 1.1 Problem statement

Musicians who want to drill rhythm and strumming patterns have no frictionless way to
log practice. Camera-based tracking is privacy-invasive and lighting-dependent; wearables
are fiddly. WiFi CSI senses motion through the ambient radio field, works in the dark,
needs no line-of-sight to a camera, and reuses hardware the user already owns.

### 1.2 Goals

- Recognize 4–6 discrete strum gestures from live WiFi CSI with usable accuracy (≥85% on a held-out test set).
- Provide real-time feedback (OLED label + buzzer beep) within a perceptible latency budget (<300 ms end-to-end).
- Log recognized gestures to a persistent store and surface a practice-consistency dashboard.
- Reuse and adapt the author's prior indoor-CSI preprocessing + 1D-CNN pipeline (continuity story for portfolio/interviews).

### 1.3 Non-goals

- Continuous chord/pitch recognition — this is gesture (motion) recognition, not audio.
- Multi-user simultaneous tracking.
- Production-grade robustness across arbitrary rooms/furniture without recalibration.
- Replacing a real instrument or a metronome app.

---

## 2. Users & use cases

| Persona | Use case |
|---|---|
| **Hobbyist learner** | Drills a strum pattern; wants a streak/consistency log without touching a phone mid-practice. |
| **Portfolio reviewer / interviewer** | Evaluates the ML + embedded + product narrative end-to-end. |
| **Maker / student** | Reproduces a WiFi-sensing gesture pipeline as a learning project (CNNs, model deployment). |

**Primary use case:** User sits/stands near the receiver ESP32, performs strum gestures in
mid-air, sees the recognized label on the OLED and hears a confirmation beep, and later
reviews a dashboard of their practice session.

---

## 3. Gesture classes (v1)

| Class | Description |
|---|---|
| `down_strum` | Single downward strum motion. |
| `up_strum` | Single upward strum motion. |
| `down_up_down` | Basic composite rhythm pattern. |
| `palm_mute` | Short damped tap / palm-mute gesture. |
| `rest` | Deliberate mute/rest (hand present, no strum). |
| `background` | No motion / ambient (negative class). |

Minimum viable set: `down_strum`, `up_strum`, `rest`, `background`. The composite and
palm-mute classes are stretch classes added once the base four are reliable.

---

## 4. Functional requirements

### 4.1 CSI acquisition
- **FR-1** TX ESP32 emits a steady CSI-inducing packet stream (UDP, ~100 packets/sec, fixed interval).
- **FR-2** RX ESP32 extracts per-subcarrier CSI amplitude and phase and streams it over serial.
- **FR-3** A laptop-side logger captures the serial CSI stream with timestamps to disk.

### 4.2 Data collection & labeling
- **FR-4** A key-press labeling tool records a ground-truth timestamp at each strum onset.
- **FR-5** Collected data supports ≥100–150 samples per gesture class, across varied distance, speed, and hand angle.
- **FR-6** An onset detector (amplitude variance threshold) auto-segments fixed windows (~0.5–1 s) around strum events, with manual override.

### 4.3 Preprocessing
- **FR-7** Drop noisy edge subcarriers; select the informative subcarrier band.
- **FR-8** Amplitude normalization + optional Hampel outlier filter.
- **FR-9** Sliding-window segmentation into model-ready tensors.

### 4.4 Modeling
- **FR-10** Train a 1D-CNN (Conv1D → BatchNorm → ReLU → pool ×2–3 → dense → softmax) over the gesture classes.
- **FR-11** Maintain a hand-crafted-feature baseline (variance, peak count, energy) + SVM to justify CNN complexity.
- **FR-12** Persist trained model + preprocessing parameters as versioned artifacts.

### 4.5 Real-time inference
- **FR-13 (Tier A — required)** Laptop runs inference on the streamed CSI and sends the result back to the RX ESP32 over serial to drive OLED + buzzer.
- **FR-14 (Tier B — stretch)** Quantized TFLite Micro model runs on-device on the RX ESP32; laptop optional.

### 4.6 Practice-logging layer
- **FR-15** Recognized gesture sequences are logged with timestamps to a local file and/or Supabase.
- **FR-16** A dashboard shows strums/day, pattern accuracy over time, and streaks.

---

## 5. Non-functional requirements

| Attribute | Target |
|---|---|
| End-to-end latency (gesture → feedback) | < 300 ms (Tier A) |
| Classification accuracy (held-out) | ≥ 85% on core classes |
| CSI stream rate | ~100 packets/sec, stable |
| Data volume | ≥ 100–150 samples/class |
| Reproducibility | Documented firmware config, fixed seeds, versioned artifacts |
| Privacy | No audio/video captured; CSI only |

---

## 6. System architecture

```
 ┌──────────┐   WiFi packets    ┌──────────┐   serial CSI    ┌──────────┐
 │ TX ESP32 │ ────────────────▶ │ RX ESP32 │ ──────────────▶ │  Laptop  │
 │ (pinger) │  (hand distorts   │ (CSI rx) │  (amp/phase)    │ logger + │
 └──────────┘   the channel)    └────┬─────┘                 │ inference│
                                     │  ▲                    └────┬─────┘
                            OLED /   │  │ result over serial      │
                            buzzer ◀─┘  └─────────────────────────┘
                                                                  │
                                                        ┌─────────▼─────────┐
                                                        │ Practice log +    │
                                                        │ dashboard (local  │
                                                        │ file / Supabase)  │
                                                        └───────────────────┘
```

Tier B moves the inference block onto the RX ESP32 via TFLite Micro.

---

## 7. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| CSI stream setup is fiddly (highest-risk step) | High | Use Espressif `esp32-csi-tool` (Hernandez) — do not parse CSI from scratch. Validate stream before anything else. |
| Poor model generalization | Medium | Enforce data-collection variety (distance/speed/angle); keep SVM baseline as sanity check. |
| Multipath/environment drift | Medium | Fixed TX/RX geometry; per-session normalization; recalibration procedure documented. |
| TFLite Micro memory limits on ESP32 | Medium | Keep model small (≤3 conv blocks); quantize; treat Tier B as optional stretch. |
| Latency budget missed | Low | Batch small windows; profile serial round-trip. |

---

## 8. Success metrics

- **Technical:** ≥85% held-out accuracy on core classes; <300 ms feedback latency; stable 100 pkt/s CSI.
- **Product:** A working dashboard showing at least one multi-day practice streak.
- **Narrative:** Demonstrable reuse of prior CSI preprocessing + 1D-CNN pipeline.

---

## 9. Milestones

| Phase | Deliverable | Est. |
|---|---|---|
| 1 | CSI firmware + serial pipe streaming stable CSI | 3–4 days |
| 2 | Full labeled dataset across all classes | 2–3 days |
| 3 | Preprocessing + SVM baseline | 2–3 days |
| 4 | 1D-CNN trained + tuned to target accuracy | 3–4 days |
| 5 | Real-time integration + OLED/buzzer (Tier A) | 2–3 days |
| 6 | Practice-logging layer + dashboard | 2–3 days |
| 7 (opt) | TFLite Micro on-device inference (Tier B) | 3–5 days |

**Total:** ~2–3 weeks part-time (core), +1 week for the on-device stretch.
