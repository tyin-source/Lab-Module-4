#!/usr/bin/env python3
"""Phys 39 Module 4, Parts 4-5: steady-state temperature vs signed PWM.

Reads the Part 3 steady-state table (data/module_04/steady_state.csv), plots
steady-state temperature against signed PWM (heating positive, red; cooling
negative, blue), fits a straight line to each branch, and reports:

  h_heat, h_cool      susceptibilities dT_ss/du in degC per PWM count (both positive)
  r = h_heat/h_cool   measured slope ratio
  J/P = (r-1)/(r+1)   object-face Joule-to-Peltier ratio from the energy balance

If the Laird data-sheet values below are filled in, it also computes
  J_max = I_max^2 R / 2,  P_max = Q_max + J_max,
  r_ds  = (P_max + J_max)/(P_max - J_max) = 1 + I_max^2 R / Q_max.

Usage:
  python analysis/tec_calibration_analysis.py
  python analysis/tec_calibration_analysis.py --heat-range 0 180 --cool-range 0 200

The ranges are PWM magnitudes (inclusive) used for each branch's fit.
"""

import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "module_04" / "steady_state.csv"
DEFAULT_FIG = ROOT / "docs" / "figures" / "module_04" / "steady_state_vs_signed_pwm.png"

HEAT_COLOR = "#d01c1c"
COOL_COLOR = "#1f4fd8"

# ------------------------------------------------------------------
# LAIRD CP14-127-045 DATA-SHEET VALUES (Part 5.3)
# ------------------------------------------------------------------
# Find these yourself in the data sheet, for the class model at the stated
# hot-side temperature, and record the page/table you used. Leave as None
# until you have them; the script skips the data-sheet comparison.
DATASHEET = {
    "R_ohm": None,        # module resistance R (ohm)
    "I_max_A": None,      # maximum current I_max (A)
    "Q_max_W": None,      # maximum cold-side heat pumping at dT = 0, Q_max (W)
    "dT_max_K": None,     # maximum temperature difference dT_max (K) -- recorded, not used below
}
# ------------------------------------------------------------------


def load_table(path: Path):
    """Return (signed_pwm, steady_T, direction) arrays from the Part 3 table."""
    signed, temps, dirs = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            direction = row["direction"].strip().lower()
            pwm_text = row["pwm"].strip()
            temp_text = row["steady_temperature_C"].strip()
            if not pwm_text or not temp_text:
                continue  # not yet measured
            pwm = int(pwm_text)
            if direction not in ("heat", "cool"):
                raise ValueError(f"direction must be heat or cool, got {row['direction']!r}")
            signed.append(pwm if direction == "heat" else -pwm)
            temps.append(float(temp_text))
            dirs.append(direction)
    return np.array(signed, dtype=float), np.array(temps, dtype=float), np.array(dirs)


def fit_branch(u, T, lo, hi):
    """Least-squares line T = a + h u over |u| in [lo, hi]; returns (h, sigma_h, a, mask)."""
    mask = (np.abs(u) >= lo) & (np.abs(u) <= hi)
    n = int(mask.sum())
    if n < 2:
        return None
    x, y = u[mask], T[mask]
    if n >= 3:
        (h, a), cov = np.polyfit(x, y, 1, cov=True)
        sigma_h = float(np.sqrt(cov[0, 0]))
    else:
        h, a = np.polyfit(x, y, 1)
        sigma_h = float("nan")
    return float(h), sigma_h, float(a), mask


def curvature_note(u, T, fit):
    """Largest residual from the straight-line fit, in degC."""
    h, _, a, mask = fit
    resid = T[mask] - (a + h * u[mask])
    return float(np.max(np.abs(resid)))


def main():
    parser = argparse.ArgumentParser(description="Module 4 steady-state calibration analysis")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--fig", type=Path, default=DEFAULT_FIG)
    parser.add_argument("--heat-range", type=float, nargs=2, default=(0, 255), metavar=("LO", "HI"))
    parser.add_argument("--cool-range", type=float, nargs=2, default=(0, 255), metavar=("LO", "HI"))
    args = parser.parse_args()

    u, T, dirs = load_table(args.csv)
    heat = dirs == "heat"
    cool = dirs == "cool"
    if heat.sum() < 2 or cool.sum() < 2:
        sys.exit(f"Need at least two measured heating and two measured cooling rows in {args.csv}")

    # Both branches share the PWM = 0 point, so each fit includes it if in range.
    heat_fit = fit_branch(u[heat], T[heat], *args.heat_range)
    cool_fit = fit_branch(u[cool], T[cool], *args.cool_range)
    if heat_fit is None or cool_fit is None:
        sys.exit("Each fitting range must contain at least two points")

    h_heat, s_heat, a_heat, _ = heat_fit
    h_cool, s_cool, a_cool, _ = cool_fit
    r = h_heat / h_cool
    s_r = abs(r) * np.hypot(s_heat / h_heat, s_cool / h_cool)
    j_over_p = (r - 1) / (r + 1)

    print("Part 5.1  Measured susceptibilities (dT_ss / d u, u = signed PWM)")
    print(f"  heating: h_heat = {h_heat:.4f} +/- {s_heat:.4f} degC/count, "
          f"fit |PWM| in [{args.heat_range[0]:g}, {args.heat_range[1]:g}], "
          f"max residual {curvature_note(u[heat], T[heat], heat_fit):.2f} degC")
    print(f"  cooling: h_cool = {h_cool:.4f} +/- {s_cool:.4f} degC/count, "
          f"fit |PWM| in [{args.cool_range[0]:g}, {args.cool_range[1]:g}], "
          f"max residual {curvature_note(u[cool], T[cool], cool_fit):.2f} degC")
    print(f"  ratio r = h_heat/h_cool = {r:.3f} +/- {s_r:.3f}")
    print("Part 5.2  Energy balance: r = (P + J)/(P - J)  =>  J/P = (r - 1)/(r + 1)")
    print(f"  J/P = {j_over_p:.3f}")

    ds = DATASHEET
    if all(ds[k] is not None for k in ("R_ohm", "I_max_A", "Q_max_W")):
        j_max = 0.5 * ds["I_max_A"] ** 2 * ds["R_ohm"]
        p_max = ds["Q_max_W"] + j_max
        r_ds = (p_max + j_max) / (p_max - j_max)
        print("Part 5.3  Laird data-sheet prediction at I_max, dT = 0")
        print(f"  J_obj = I_max^2 R / 2 = {j_max:.2f} W")
        print(f"  P_max = Q_max + J_obj = {p_max:.2f} W")
        print(f"  (J/P)_ds = {j_max / p_max:.3f}")
        print(f"  r_ds = (P_max + J_obj)/(P_max - J_obj) = {r_ds:.3f}")
        print(f"Part 5.4  measured r / r_ds = {r / r_ds:.3f}")
    else:
        print("Part 5.3  Fill in DATASHEET at the top of this script to compute r_ds.")

    # ---------------- Part 4 graph ----------------
    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=150)
    ax.axhline(T[u == 0].mean() if np.any(u == 0) else np.nan, color="0.8", lw=0.8, zorder=0)
    ax.axvline(0, color="0.8", lw=0.8, zorder=0)

    ax.plot(u[heat], T[heat], "o", color=HEAT_COLOR, label="Heating (measured)")
    ax.plot(u[cool], T[cool], "s", color=COOL_COLOR, label="Cooling (measured)")

    xh = np.linspace(args.heat_range[0], min(args.heat_range[1], u[heat].max()), 50)
    xc = -np.linspace(args.cool_range[0], min(args.cool_range[1], -u[cool].min()), 50)
    ax.plot(xh, a_heat + h_heat * xh, "-", color=HEAT_COLOR, lw=1.5,
            label=f"Heating fit: {h_heat:.3f} °C/count")
    ax.plot(xc, a_cool + h_cool * xc, "-", color=COOL_COLOR, lw=1.5,
            label=f"Cooling fit: {h_cool:.3f} °C/count")

    ax.set_xlabel("Signed PWM (counts; + heat, − cool)")
    ax.set_ylabel("Steady-state temperature (°C)")
    ax.set_title(f"TEC open-loop calibration  (h_heat / h_cool = {r:.2f})", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.text(0.01, 0.01,
             "Steady state: waited ~3 time constants after each PWM step, then required the "
             "net drift over 1 min\nto be no larger than the short-term noise.",
             fontsize=7, va="bottom")
    fig.tight_layout(rect=(0, 0.06, 1, 1))

    args.fig.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.fig)
    print(f"Saved graph to {args.fig}")


if __name__ == "__main__":
    main()
