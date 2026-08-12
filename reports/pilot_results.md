# Pilot Results — CSI Strum Classification

**Date:** 2026-08-12
**Setup:** Single ESP32 (router mode, RSSI ~−56 dBm), laptop ping-driven CSI, 64 subcarriers.
**Data:** 1 session, 89 samples — still ×29, down_strum ×30, up_strum ×30 (1.5 s windows).
**Model:** RandomForest (300 trees) on 13 hand-crafted features, 5-fold stratified CV.

## Headline numbers
| Task | Accuracy | Chance |
|---|---|---|
| 3-class (still / down / up) | **62.9% ± 11%** | 33.7% |
| still vs strum (motion detection) | 70.8% | ~67% |
| down vs up (direction) | 80.0% | 50% |
| packet-count-only baseline | 42.5% | 33.7% |

CSI features add **+20%** over the packet-count-only baseline → the CSI carries real information.

## Confusion matrix (3-class, CV predictions)
```
            down_str     still  up_strum
down_strum      22         5         3
still            8        17         4
up_strum         8         5        17
```

## Top features
rssi_mean, gap_std (packet-timing jitter), lowhigh_ratio (subcarrier shape),
amp_std, amp_mean, n_packets, fc_std/fc_max (frame-to-frame change).

## Interpretation
- **Works, but limited.** Well above chance and CSI helps — the pipeline is sound.
- **Motion detection (still vs strum) is weak (≈ chance).** "Still" was recorded as a
  *stationary hand in the zone*, which attenuates the link much like a moving hand, so
  presence dominates over motion in this blocky (packet-loss-driven) signal.
- **Direction (down vs up) looks strong (80%)** but is suspect: down-strum averaged 39
  packets/sample vs up-strum's 21, so the model may be keying on *execution differences*
  (speed/position/timing) rather than robust motion-direction physics.

## Recommended next steps
1. **Improve signal quality** — steady high-rate traffic (direct UDP instead of lossy pings)
   + geometry that yields *graded* per-subcarrier CSI rather than blocking. This is the
   biggest lever.
2. **Collect more, more consistently** — 100+ reps/class, deliberately varying speed/position
   so the model can't latch onto per-class execution habits.
3. **Then revisit a 1D-CNN** on resampled sequences once the signal is cleaner.
