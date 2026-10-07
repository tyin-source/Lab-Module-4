# Phys 39 Module 5 - Parts 3, 4, 6: measured vs predicted droop
#
# Reads data/module_05/p_runs_summary.csv (written by module5_run_summary.py)
# and, for the droop and high-gain runs, plots
#   1. droop vs Kp: measured points with the Module 4 prediction
#        droop = (Tset - Tamb) / (1 + chi_T Kp)
#      (one predicted curve per setpoint, using that setpoint's mean Tamb),
#   2. fractional droop (Tset - Tss) / (Tset - Tamb) vs L = Kp |chi_T|,
#      with the model 1 / (1 + L).
#
# Usage (from the repository root):
#   python python/module5_droop_plot.py
#   python python/module5_droop_plot.py --parts droop        # leave out high-gain runs
#
# Figures:
#   docs/figures/module_05/droop_vs_kp.png
#   docs/figures/module_05/fractional_droop_vs_L.png

import argparse
import csv

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from module5_common import MODULE5_DATA_DIR, MODULE5_FIG_DIR

SUMMARY_PATH = MODULE5_DATA_DIR / "p_runs_summary.csv"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts", nargs="+", default=["droop", "highgain"],
                    help="which run groups from the summary to include")
    args = ap.parse_args()

    with open(SUMMARY_PATH, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["part"] in args.parts]
    if not rows:
        raise SystemExit(f"No runs with part in {args.parts} in {SUMMARY_PATH}")

    def col(name, subset):
        return np.array([float(r[name]) for r in subset])

    setpoints = sorted({float(r["setpoint_C"]) for r in rows})
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    # ---------------- 1. droop vs Kp ----------------
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, sp in enumerate(setpoints):
        sub = [r for r in rows if float(r["setpoint_C"]) == sp]
        kp = col("Kp", sub)
        order = np.argsort(kp)
        c = colors[i % len(colors)]
        t_amb = float(np.mean(col("t_amb_C", sub)))
        chi = float(sub[0]["chi_T"])
        direction = sub[0]["direction"]

        ax.plot(kp[order], col("droop_C", sub)[order], "o", color=c, ms=7,
                label=f"Measured, Tset = {sp:.1f} °C")
        ax.plot(kp[order], col("predicted_droop_C", sub)[order], "s", color=c,
                mfc="none", ms=8, label="Predicted (each run's Tamb)")
        kp_fine = np.geomspace(max(kp.min() / 2, 1e-3), kp.max() * 1.5, 200)
        ax.plot(kp_fine, (sp - t_amb) / (1 + chi * kp_fine), "--", color=c,
                label=f"Model: Tamb = {t_amb:.2f} °C, |chi| = {chi:.3f} °C/count ({direction})")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("Kp (PWM counts / °C)")
    ax.set_ylabel("Droop  Tset − Tss  (°C)")
    ax.set_title("P-only control: measured and predicted droop vs gain")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    MODULE5_FIG_DIR.mkdir(parents=True, exist_ok=True)
    path1 = MODULE5_FIG_DIR / "droop_vs_kp.png"
    fig.savefig(path1, dpi=120)
    plt.close(fig)

    # ---------------- 2. fractional droop vs L ----------------
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, sp in enumerate(setpoints):
        sub = [r for r in rows if float(r["setpoint_C"]) == sp]
        ax.plot(col("L", sub), col("frac_droop", sub), "o", color=colors[i % len(colors)],
                ms=7, label=f"Measured, Tset = {sp:.1f} °C")
    L_all = col("L", rows)
    L_fine = np.geomspace(min(L_all.min() / 2, 0.05), max(L_all.max() * 2, 20), 200)
    ax.plot(L_fine, 1 / (1 + L_fine), "k--", label="Model 1 / (1 + L)")
    ax.set_xscale("log")
    ax.set_xlabel("Loop gain  L = Kp |chi_T|  (dimensionless)")
    ax.set_ylabel("(Tset − Tss) / (Tset − Tamb)")
    ax.set_title("Fractional droop vs dimensionless loop gain")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path2 = MODULE5_FIG_DIR / "fractional_droop_vs_L.png"
    fig.savefig(path2, dpi=120)
    plt.close(fig)

    print("| Kp (PWM/°C) | Tset (°C) | Tamb (°C) | L | Measured droop (°C) "
          "| Predicted droop (°C) | Measured fraction | 1/(1+L) |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in sorted(rows, key=lambda r: (float(r["setpoint_C"]), float(r["Kp"]))):
        print(f"| {float(r['Kp']):g} | {float(r['setpoint_C']):.1f} | {float(r['t_amb_C']):.2f} "
              f"| {float(r['L']):.2f} | {float(r['droop_C']):+.2f} "
              f"| {float(r['predicted_droop_C']):+.2f} | {float(r['frac_droop']):.3f} "
              f"| {float(r['predicted_frac_droop']):.3f} |")
    print(f"\nSaved {path1}\nSaved {path2}")


if __name__ == "__main__":
    main()
