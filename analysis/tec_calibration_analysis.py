#!/usr/bin/env python3
"""Module 4 Parts 4-5: steady-state temperature vs signed PWM, slopes, and ratios.

Reads data/module_04/steady_state.csv (written by the GUI's "Record steady
point" button, or filled in by hand from the notebook table) and:

1. plots steady temperature vs signed PWM (heat > 0 red, cool < 0 blue),
2. fits a line to each direction over the chosen PWM range -> chi_heat, chi_cool,
3. reports the measured ratio |chi_heat / chi_cool| and the implied J/P, and
4. computes the Laird data-sheet maximum-current prediction of the ratio.

Usage:
    python analysis/tec_calibration_analysis.py [path/to/steady_state.csv]
"""

import csv
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "module_04" / "steady_state.csv"
FIGURE_PATH = ROOT / "docs" / "figures" / "module_04" / "temperature_vs_signed_pwm.png"

# ------------------------------------------------------------------
# FIT RANGES (PWM magnitude, inclusive). Adjust to the approximately
# linear region of your graph and report these ranges in A2.
# ------------------------------------------------------------------
HEAT_FIT_RANGE = (0, 255)
COOL_FIT_RANGE = (0, 255)

# ------------------------------------------------------------------
# LAIRD CP14-127-045 DATA-SHEET VALUES (hot side at the tabulated Th).
# Fill these in yourself from the data sheet; leave as None until then.
# ------------------------------------------------------------------
LAIRD_R_OHM = None       # module resistance R
LAIRD_IMAX_A = None      # maximum current I_max
LAIRD_QMAX_W = None      # max cold-side heat pumping Q_max at dT = 0
LAIRD_DTMAX_C = None     # max temperature difference dT_max (recorded, not used below)


def load_points(path: Path):
    heat, cool = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            direction = row["direction"].strip().lower()
            pwm = int(row["pwm"])
            T = float(row["steady_temperature_C"])
            if direction.startswith("h"):
                heat.append((pwm, T))
            elif direction.startswith("c"):
                cool.append((pwm, T))
    return sorted(heat), sorted(cool)


def fit_slope(points, pwm_range):
    """Linear fit T = a + chi * PWM over the given magnitude range."""
    lo, hi = pwm_range
    sel = [(p, T) for p, T in points if lo <= p <= hi]
    if len(sel) < 2:
        raise ValueError(f"need >= 2 points in PWM range {pwm_range}, got {len(sel)}")
    x = np.array([p for p, _ in sel], dtype=float)
    y = np.array([T for _, T in sel], dtype=float)
    if len(sel) > 3:
        (chi, intercept), cov = np.polyfit(x, y, 1, cov=True)
        chi_err = math.sqrt(cov[0][0])
    else:
        chi, intercept = np.polyfit(x, y, 1)
        chi_err = math.nan  # too few points for a standard error
    return chi, intercept, chi_err, x, y


def datasheet_ratio(R, I_max, Q_max):
    """Predicted |chi_heat/chi_cool| from Laird max-current data at dT = 0.

    Q_J,obj = I_max^2 R / 2,  Q_max = Q_P - Q_J,obj  ->  Q_P = Q_max + Q_J,obj
    ratio = (Q_P + Q_J,obj) / (Q_P - Q_J,obj)
    """
    q_j = 0.5 * I_max**2 * R
    q_p = Q_max + q_j
    return q_j, q_p, (q_p + q_j) / (q_p - q_j)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    heat, cool = load_points(path)

    chi_h, b_h, err_h, xh, yh = fit_slope(heat, HEAT_FIT_RANGE)
    chi_c, b_c, err_c, xc, yc = fit_slope(cool, COOL_FIT_RANGE)
    # chi_c is dT/d|PWM| while cooling (negative). Against signed PWM
    # (cooling plotted at -PWM) the cooling slope is -chi_c > 0.

    ratio = abs(chi_h / chi_c)
    j_over_p = (ratio - 1) / (ratio + 1)

    print(f"Data: {path}")
    print(f"chi_heat = {chi_h:+.5f} C/count (fit PWM {HEAT_FIT_RANGE[0]}-{HEAT_FIT_RANGE[1]}, "
          f"+/- {err_h:.5f})")
    print(f"chi_cool = {chi_c:+.5f} C/count (fit PWM {COOL_FIT_RANGE[0]}-{COOL_FIT_RANGE[1]}, "
          f"+/- {err_c:.5f})")
    print(f"|chi_heat / chi_cool| = {ratio:.3f}")
    print(f"Implied J/P = (ratio - 1)/(ratio + 1) = {j_over_p:.3f}")

    if None not in (LAIRD_R_OHM, LAIRD_IMAX_A, LAIRD_QMAX_W):
        q_j, q_p, pred = datasheet_ratio(LAIRD_R_OHM, LAIRD_IMAX_A, LAIRD_QMAX_W)
        print(f"Laird: Q_J,obj = {q_j:.2f} W, Q_P = {q_p:.2f} W, predicted ratio = {pred:.3f}")
    else:
        print("Laird values not filled in yet; skipping data-sheet prediction.")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(xh, yh, "o", color="tab:red", label="Heating")
    ax.plot(-xc, yc, "s", color="tab:blue", label="Cooling")
    xs = np.linspace(xh.min(), xh.max(), 50)
    ax.plot(xs, b_h + chi_h * xs, "-", color="tab:red", alpha=0.7,
            label=f"fit: {chi_h:+.4f} °C/count")
    xs = np.linspace(xc.min(), xc.max(), 50)
    ax.plot(-xs, b_c + chi_c * xs, "-", color="tab:blue", alpha=0.7,
            label=f"fit: {chi_c:+.4f} °C/count")
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_xlabel("Signed PWM (counts; negative = cooling, positive = heating)")
    ax.set_ylabel("Steady-state temperature (°C)")
    ax.set_title("TEC open-loop calibration")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=200)
    print(f"Saved figure: {FIGURE_PATH}")


if __name__ == "__main__":
    main()
