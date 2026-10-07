# Phys 39 Module 5 - summarize P-control runs and draw strip charts (Parts 2, 3, 5)
#
# For each run CSV written by module5_p_control_gui.py this script:
#   - averages the last --settle-seconds of the run (the "settled window"),
#   - calculates steady temperature Tss, droop = Tset - Tss, mean final PWM,
#     PWM saturation, and the drift over the window,
#   - measures oscillation in the window:
#       amplitude = half of the peak-to-peak temperature in the window,
#       period    = mean time between upward crossings of the window mean
#                   (a crossing counts only after T has gone below
#                   mean - hysteresis and then above mean + hysteresis),
#       frequency = 1 / period,
#   - compares with the Module 4 model: L = Kp |chi_T|, droop = e0 / (1 + L),
#   - saves a strip chart to docs/figures/module_05/<run name>.png,
#   - adds or replaces the run's row in data/module_05/p_runs_summary.csv.
#
# Room temperature: pass --t-amb. If omitted, the first temperature in the
# run file is used, which is correct only if the run started from rest at
# room temperature with PWM 0.
#
# Usage (from the repository root):
#   python python/module5_run_summary.py data/module_05/p_*_Kp4.csv --part droop --t-amb 23.0
#   python python/module5_run_summary.py data/module_05/p_*.csv --part sign --settle-seconds 30

import argparse
import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from module5_common import (MODULE5_DATA_DIR, MODULE5_FIG_DIR,
                            directional_susceptibility, read_run)

SUMMARY_PATH = MODULE5_DATA_DIR / "p_runs_summary.csv"
SUMMARY_FIELDS = [
    "file", "part", "setpoint_C", "Kp", "t_amb_C", "direction", "chi_T",
    "L", "P0", "T_ss_C", "droop_C", "predicted_droop_C", "frac_droop",
    "predicted_frac_droop", "final_pwm_mean", "saturated_frac",
    "window_s", "drift_C_per_min", "p2p_C", "amplitude_C", "period_s",
    "frequency_Hz",
]


def upward_crossing_times(t, y, level, hysteresis):
    """Times where y goes from below level - hysteresis to above level + hysteresis."""
    times = []
    armed = False
    for i in range(len(y)):
        if y[i] < level - hysteresis:
            armed = True
        elif armed and y[i] > level + hysteresis:
            # interpolate the crossing of `level` between i-1 and i
            j = i
            while j > 0 and y[j - 1] > level:
                j -= 1
            if j > 0:
                frac = (level - y[j - 1]) / (y[j] - y[j - 1])
                times.append(t[j - 1] + frac * (t[j] - t[j - 1]))
            else:
                times.append(t[i])
            armed = False
    return np.array(times)


def summarize(path: Path, part: str, settle_s: float, t_amb, hysteresis: float):
    run = read_run(path)
    t = run["time_s"] - run["time_s"][0]
    T = run["temperature_C"]
    t_set = float(run["setpoint_C"][0])
    kp = float(run["Kp"][0])
    signed_cmd = np.where(run["dir_cmd"] == "COOL", -run["pwm_cmd"], run["pwm_cmd"])

    if t_amb is None:
        t_amb = float(T[0])
    e0 = t_set - t_amb
    direction, chi = directional_susceptibility(t_set, t_amb)
    L = kp * chi

    win = t >= t[-1] - settle_s
    tw, Tw = t[win], T[win]
    T_ss = float(np.mean(Tw))
    droop = t_set - T_ss
    predicted_droop = e0 / (1 + L)
    drift = float(np.polyfit(tw, Tw, 1)[0] * 60) if len(tw) > 1 else float("nan")
    p2p = float(np.ptp(Tw))

    crossings = upward_crossing_times(tw, Tw, T_ss, hysteresis)
    period = float(np.mean(np.diff(crossings))) if len(crossings) >= 2 else float("nan")

    row = {
        "file": path.name,
        "part": part,
        "setpoint_C": t_set,
        "Kp": kp,
        "t_amb_C": t_amb,
        "direction": direction,
        "chi_T": chi,
        "L": L,
        "P0": kp * abs(e0),
        "T_ss_C": T_ss,
        "droop_C": droop,
        "predicted_droop_C": predicted_droop,
        "frac_droop": droop / e0 if e0 != 0 else float("nan"),
        "predicted_frac_droop": 1 / (1 + L),
        "final_pwm_mean": float(np.mean(run["pwm_cmd"][win])),
        "saturated_frac": float(np.mean(run["saturated"])),
        "window_s": float(tw[-1] - tw[0]),
        "drift_C_per_min": drift,
        "p2p_C": p2p,
        "amplitude_C": p2p / 2,
        "period_s": period,
        "frequency_Hz": 1 / period if np.isfinite(period) else float("nan"),
    }

    # ---------------- strip chart ----------------
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1, 1]})
    ax = axes[0]
    ax.plot(t, T, color="black", lw=1.5, label="T (measured)")
    ax.axhline(t_set, color="green", ls="--", lw=1.5, label=f"Tset = {t_set:.1f} °C")
    ax.axhline(t_amb, color="gray", ls=":", lw=1.2, label=f"Tamb = {t_amb:.2f} °C")
    ax.axhline(t_set - predicted_droop, color="orange", ls="-.", lw=1.2,
               label=f"Predicted Tss = {t_set - predicted_droop:.2f} °C")
    ax.axvspan(tw[0], tw[-1], color="tab:blue", alpha=0.08,
               label=f"Settled window: Tss = {T_ss:.2f} °C")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(f"P-only control: Kp = {kp:g} PWM/°C, L = {L:.2f} ({direction})\n{path.name}")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.3)

    ax = axes[1]
    heat = np.where(signed_cmd >= 0, signed_cmd, np.nan)
    cool = np.where(signed_cmd < 0, signed_cmd, np.nan)
    ax.step(t, heat, where="post", color="red", lw=1.2, label="HEAT")
    ax.step(t, cool, where="post", color="blue", lw=1.2, label="COOL")
    if np.any(np.abs(signed_cmd) > 0.8 * 255):
        for lim in (255, -255):
            ax.axhline(lim, color="gray", ls=":", lw=1)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("Signed PWM sent")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.3)

    ax = axes[2]
    ax.plot(t, run["error_C"], color="purple", lw=1.2)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("e = Tset − T (°C)")
    ax.set_xlabel("Time since P control started (s)")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    MODULE5_FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = MODULE5_FIG_DIR / f"{path.stem}.png"
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    return row, fig_path


def update_summary(rows):
    existing = []
    if SUMMARY_PATH.exists():
        with open(SUMMARY_PATH, newline="") as f:
            existing = list(csv.DictReader(f))
    new_files = {r["file"] for r in rows}
    merged = [r for r in existing if r["file"] not in new_files] + rows
    merged.sort(key=lambda r: r["file"])
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        for r in merged:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path, nargs="+", help="run CSV files")
    ap.add_argument("--part", choices=["sign", "droop", "highgain"], required=True,
                    help="which part of the assignment these runs belong to")
    ap.add_argument("--settle-seconds", type=float, default=120.0,
                    help="length of the settled window at the end of each run (s)")
    ap.add_argument("--t-amb", type=float, default=None,
                    help="room temperature (C); default: first temperature in the run")
    ap.add_argument("--hysteresis", type=float, default=0.1,
                    help="crossing hysteresis for the period measurement (C)")
    args = ap.parse_args()

    rows = []
    for path in args.runs:
        row, fig_path = summarize(path, args.part, args.settle_seconds,
                                  args.t_amb, args.hysteresis)
        rows.append(row)
        print(f"{path.name}: Tset {row['setpoint_C']:.1f} C, Kp {row['Kp']:g}, "
              f"L {row['L']:.2f}, Tss {row['T_ss_C']:.2f} C, droop {row['droop_C']:+.2f} C "
              f"(predicted {row['predicted_droop_C']:+.2f}), final PWM {row['final_pwm_mean']:.1f}, "
              f"drift {row['drift_C_per_min']:+.3f} C/min, amplitude {row['amplitude_C']:.2f} C, "
              f"period {row['period_s']:.1f} s, saturated {100 * row['saturated_frac']:.0f}% of run")
        print(f"   strip chart: {fig_path}")
    update_summary(rows)
    print(f"Updated {SUMMARY_PATH}")

    print()
    print("Part 3 rows:")
    print("| Kp (PWM/°C) | Predicted P0 | Setpoint (°C) | Final Temperature (°C) | Droop (°C) | Final PWM | Notes |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        print(f"| {r['Kp']:g} | {r['P0']:.1f} | {r['setpoint_C']:.1f} | {r['T_ss_C']:.2f} "
              f"| {r['droop_C']:+.2f} | {r['final_pwm_mean']:.1f} | {r['file']} |")
    print()
    print("Part 5 rows (decide 'Settles?' from the strip chart and drift):")
    print("| Kp (PWM/°C) | Settles? | Mean Temperature (°C) | Amplitude (°C) | Period (s) | Frequency (Hz) | Saturation? |")
    print("| ---: | --- | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        sat = f"yes ({100 * r['saturated_frac']:.0f}% of run)" if r["saturated_frac"] > 0 else "no"
        print(f"| {r['Kp']:g} | ? | {r['T_ss_C']:.2f} | {r['amplitude_C']:.2f} "
              f"| {r['period_s']:.1f} | {r['frequency_Hz']:.4f} | {sat} |")


if __name__ == "__main__":
    main()
