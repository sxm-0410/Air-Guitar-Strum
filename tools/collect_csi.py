#!/usr/bin/env python3
"""
Air Guitar Strum — CSI data collector (pilot).

Records labeled windows of WiFi-CSI while you perform strum gestures, for the
single-ESP32 "router mode" setup. It:
  1. finds the ESP32's IP (via ARP by MAC) and floods it with pings to drive a
     steady CSI stream,
  2. reads CSI_DATA rows from the ESP32 over serial,
  3. walks you through N reps of each gesture with a countdown,
  4. saves everything to a CSV under data/pilot/.

Run it inside the ESP-IDF terminal (so pyserial is available):
    source ~/.espressif/tools/activate_idf_v5.3.5.sh
    python3 tools/collect_csi.py

Common options:
    --port /dev/cu.usbserial-110      serial port (auto-detects if omitted)
    --gestures still,down_strum,up_strum
    --count 30                        reps per gesture
    --window 1.5                      seconds recorded per rep
    --ip 192.168.0.101                ESP32 IP (auto-discovers if omitted)
    --mac b0:3f:d3:5a:ae:d0           MAC used for IP auto-discovery

Data layout (one row per CSI packet):
    gesture, sample_id, t_rel, rssi, n_sub, amps(space-separated)
Group by (gesture, sample_id) to reconstruct each window.
"""
import argparse, glob, os, re, subprocess, sys, time, signal
from datetime import datetime

def find_port():
    ports = sorted(glob.glob('/dev/cu.usbserial-*'))
    if not ports:
        sys.exit("No /dev/cu.usbserial-* found. Is the ESP32 plugged in?")
    return ports[0]

def discover_ip(mac):
    """Look up the ESP32's IP in the ARP table by MAC (normalize 0x-stripped bytes)."""
    def norm(m): return ':'.join(x.zfill(2) for x in m.lower().split(':'))
    target = norm(mac)
    try:
        out = subprocess.check_output(['arp', '-a', '-n'], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None
    for line in out.splitlines():
        m = re.search(r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+)', line, re.I)
        if m and norm(m.group(2)) == target:
            return m.group(1)
    return None

def start_ping_flood(ip, n=16):
    """Spawn n parallel pings to keep frames (and thus CSI) flowing to the ESP32."""
    procs = []
    for _ in range(n):
        p = subprocess.Popen(['ping', '-i', '0.1', ip],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
    return procs

def stop_pings(procs):
    for p in procs:
        try: p.terminate()
        except Exception: pass

def amp_str(line):
    """Parse a CSI_DATA line -> (rssi, 'a1 a2 ...' amplitude string) or None."""
    try:
        parts = line.split(',')
        rssi = int(parts[3])
        v = [int(x) for x in line.split('[')[1].split(']')[0].split()]
        amps = [round((v[i]*v[i] + v[i+1]*v[i+1]) ** 0.5, 2) for i in range(0, len(v)-1, 2)]
        if not amps: return None
        return rssi, ' '.join(str(a) for a in amps)
    except Exception:
        return None

def open_serial(port, baud):
    import serial
    s = serial.Serial(port, baud, timeout=1)
    s.dtr = False; s.rts = False
    # reset pulse so the board boots cleanly and reconnects
    s.setRTS(True); time.sleep(0.1); s.setRTS(False)
    return s

def wait_for_stream(s, timeout=25):
    t = time.time()
    while time.time() - t < timeout:
        line = re.sub(r'\x1b\[[0-9;]*m', '', s.readline().decode(errors='replace')).strip()
        if line.startswith('CSI_DATA'):
            return True
    return False

def record_window(s, seconds):
    """Read CSI rows for `seconds`, return list of (t_rel, rssi, amps_str)."""
    rows = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        line = re.sub(r'\x1b\[[0-9;]*m', '', s.readline().decode(errors='replace')).strip()
        if line.startswith('CSI_DATA'):
            r = amp_str(line)
            if r:
                rows.append((round(time.time() - t0, 4), r[0], r[1]))
    return rows

def oled(s, text):
    """Send a display command to the ESP32: 'top|bottom' (bottom optional)."""
    try:
        s.write(("OLED:" + text + "\n").encode()); s.flush()
    except Exception:
        pass

def countdown(msg, s=None, disp=None, n=3):
    print(msg)
    for i in range(n, 0, -1):
        if s is not None and disp: oled(s, f"{disp}|in {i}")
        print(f"  {i}...", end='', flush=True); time.sleep(1)
    if s is not None and disp: oled(s, f"{disp}|GO!")
    print("  GO!", flush=True)

def main():
    ap = argparse.ArgumentParser(description="CSI strum-gesture data collector")
    ap.add_argument('--port', default=None)
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--gestures', default='still,down_strum,up_strum')
    ap.add_argument('--count', type=int, default=30)
    ap.add_argument('--window', type=float, default=1.5)
    ap.add_argument('--ip', default=None)
    ap.add_argument('--mac', default='b0:3f:d3:5a:ae:d0')
    ap.add_argument('--outdir', default='data/pilot')
    ap.add_argument('--interleave', dest='interleave', action='store_true', default=True,
                    help='randomize gesture order across reps (default)')
    ap.add_argument('--blocked', dest='interleave', action='store_false',
                    help='collect each gesture in a block (old behavior)')
    ap.add_argument('--seed', type=int, default=1)
    args = ap.parse_args()

    port = args.port or find_port()
    gestures = [g.strip() for g in args.gestures.split(',') if g.strip()]
    os.makedirs(args.outdir, exist_ok=True)
    outpath = os.path.join(args.outdir, f"session_{datetime.now():%Y%m%d_%H%M%S}.csv")

    print(f"Port:     {port}")
    print(f"Gestures: {gestures}  x{args.count} reps  ({args.window}s each)")

    ip = args.ip or discover_ip(args.mac)
    if not ip:
        print("Could not auto-find ESP32 IP. Pass --ip <addr> (check your router / `arp -a`).")
        # try one broadcast ping to populate ARP, then retry
        subprocess.run(['ping', '-c', '2', '255.255.255.255'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ip = discover_ip(args.mac)
        if not ip:
            sys.exit("Still no IP. Aborting.")
    print(f"ESP32 IP: {ip}  (driving CSI with ping flood)")

    pings = start_ping_flood(ip)
    def cleanup(*_):
        stop_pings(pings); print("\nstopped pings."); sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)

    try:
        s = open_serial(port, args.baud)
        print("Waiting for CSI stream (connecting to router)...")
        if not wait_for_stream(s):
            stop_pings(pings)
            sys.exit("No CSI stream. Check the board is flashed with active_sta and joined the router.")
        print("Stream is live.\n")

        # build the trial list: interleaved (shuffled) by default so every gesture
        # is collected under identical conditions (removes block-order artifacts)
        import random
        trials = [g for g in gestures for _ in range(args.count)]
        if args.interleave:
            random.Random(args.seed).shuffle(trials)
            print(f"INTERLEAVED order ({len(trials)} trials). You'll be told which gesture each time.\n")
        else:
            print(f"BLOCKED order ({len(trials)} trials).\n")

        n_rows = 0
        rep_of = defaultdict(int)   # per-gesture sample counter
        with open(outpath, 'w') as f:
            f.write("gesture,sample_id,t_rel,rssi,amps\n")
            oled(s, "AIR GUITAR|press enter")
            input("Press ENTER to begin...")
            for k, g in enumerate(trials):
                sid = rep_of[g]; rep_of[g] += 1
                disp = g.upper().replace('_', ' ')
                countdown(f"[{k+1}/{len(trials)}]  >>> {g.upper()} <<<  perform on GO:",
                          s=s, disp=disp)
                rows = record_window(s, args.window)
                oled(s, f"REST|{k+1}/{len(trials)} done")
                for (t_rel, rssi, amps) in rows:
                    f.write(f"{g},{sid},{t_rel},{rssi},{amps}\n")
                    n_rows += 1
                f.flush()
                print(f"    captured {len(rows)} CSI packets")
        oled(s, "DONE!|thank you")
        s.close()
        print(f"\nDone. {n_rows} CSI packets saved to {outpath}")
    finally:
        stop_pings(pings)

if __name__ == '__main__':
    main()
