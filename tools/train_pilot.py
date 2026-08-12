#!/usr/bin/env python3
"""
Air Guitar Strum — pilot trainer.

Loads collected CSI windows (data/pilot/session_*.csv), extracts per-sample
features that capture motion dynamics + signal shape, and cross-validates a
classifier. Prints CV accuracy, a confusion matrix, per-class report, and the
most important features. Also compares against a "packet-count only" baseline
to show how much the actual CSI adds beyond the crude rate signal.

    .venv/bin/python tools/train_pilot.py
"""
import glob, csv, sys
import numpy as np
from collections import defaultdict
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.metrics import confusion_matrix, classification_report

def load_samples(pattern='data/pilot/session_*.csv'):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit("No data files. Run tools/collect_csi.py first.")
    # group rows by (file, gesture, sample_id) so reps from different sessions stay distinct
    groups = defaultdict(list)
    for fi, f in enumerate(files):
        for r in csv.DictReader(open(f)):
            amps = np.array([float(x) for x in r['amps'].split()], dtype=float)
            groups[(fi, r['gesture'], r['sample_id'])].append(
                (float(r['t_rel']), int(r['rssi']), amps))
    return files, groups

def features(rows):
    """rows: list of (t_rel, rssi, amp_vector). Return feature dict or None."""
    rows = sorted(rows, key=lambda x: x[0])
    # keep only the modal subcarrier length (drop malformed packets)
    lens = [len(a) for _, _, a in rows]
    if not lens: return None
    modal = max(set(lens), key=lens.count)
    A = np.array([a for _, _, a in rows if len(a) == modal])
    ts = np.array([t for t, _, a in rows if len(a) == modal])
    rssi = np.array([r for _, r, a in rows if len(a) == modal], dtype=float)
    if len(A) < 3:  # too few packets to describe dynamics
        return {'n_packets': float(len(A)), 'amp_mean': A.mean() if A.size else 0.0,
                'amp_std': 0.0, 'subc_var_mean': 0.0, 'subc_var_max': 0.0,
                'fc_mean': 0.0, 'fc_std': 0.0, 'fc_max': 0.0,
                'rssi_mean': rssi.mean() if rssi.size else 0.0, 'rssi_std': 0.0,
                'gap_mean': 0.0, 'gap_std': 0.0, 'lowhigh_ratio': 1.0}
    # frame-to-frame change (motion dynamics)
    d = np.abs(np.diff(A, axis=0)).mean(axis=1)
    # per-subcarrier temporal variance (motion energy per subcarrier)
    subc_var = A.var(axis=0)
    gaps = np.diff(ts)
    half = A.shape[1] // 2
    low = A[:, :half].mean(); high = A[:, half:].mean()
    return {
        'n_packets':     float(len(A)),
        'amp_mean':      float(A.mean()),
        'amp_std':       float(A.std()),
        'subc_var_mean': float(subc_var.mean()),
        'subc_var_max':  float(subc_var.max()),
        'fc_mean':       float(d.mean()),
        'fc_std':        float(d.std()),
        'fc_max':        float(d.max()),
        'rssi_mean':     float(rssi.mean()),
        'rssi_std':      float(rssi.std()),
        'gap_mean':      float(gaps.mean()),
        'gap_std':       float(gaps.std()),
        'lowhigh_ratio': float(low / high) if high else 1.0,
    }

def main():
    files, groups = load_samples()
    X, y, names = [], [], None
    for (fi, g, sid), rows in groups.items():
        feat = features(rows)
        if feat is None: continue
        if names is None: names = sorted(feat.keys())
        X.append([feat[k] for k in names]); y.append(g)
    X = np.array(X); y = np.array(y)
    classes = sorted(set(y))
    print(f"Loaded {len(files)} session(s) | {len(X)} samples | {len(names)} features")
    for c in classes:
        print(f"  {c:12s}: {(y==c).sum()} samples")
    print(f"chance (majority) = {max((y==c).mean() for c in classes):.1%}\n")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    clf = RandomForestClassifier(n_estimators=300, random_state=0, class_weight='balanced')

    scores = cross_val_score(clf, X, y, cv=cv)
    print(f"=== RandomForest (all features) ===")
    print(f"5-fold CV accuracy: {scores.mean():.1%} ± {scores.std():.1%}  (folds: {np.round(scores,2)})")

    pred = cross_val_predict(clf, X, y, cv=cv)
    cm = confusion_matrix(y, pred, labels=classes)
    print("\nConfusion matrix (rows=true, cols=pred):")
    print("            " + "  ".join(f"{c[:8]:>8s}" for c in classes))
    for i, c in enumerate(classes):
        print(f"  {c:10s}" + "  ".join(f"{cm[i][j]:8d}" for j in range(len(classes))))
    print("\n" + classification_report(y, pred, labels=classes, digits=2, zero_division=0))

    # feature importance
    clf.fit(X, y)
    imp = sorted(zip(names, clf.feature_importances_), key=lambda x: -x[1])
    print("Top features:")
    for n, v in imp[:8]:
        print(f"  {n:16s} {v:.3f}")

    # baseline: packet-count only (is CSI adding anything beyond crude rate?)
    pc = X[:, [names.index('n_packets')]]
    base = cross_val_score(clf, pc, y, cv=cv).mean()
    print(f"\nBaseline (packet-count only): {base:.1%}   "
          f"→ CSI features add {scores.mean()-base:+.1%}")

if __name__ == '__main__':
    main()
