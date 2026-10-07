# Phys 39 Module 4 - Part 3
# Time constant and steady-state check from a GUI run CSV.
#
# Usage:
#   python python/steady_state_analysis.py data/module_04/module4_run_YYYYMMDD_HHMMSS.csv
#
# The CSV is the one module4_control_gui.py writes
# (time_s, temperature_C, pwm, heat_cool, safety_shutdown).
#
# For every PWM step in the run (a change of PWM or heat/cool), this script:
#   1. fits  T(t) = T_ss + (T_start - T_ss) * exp(-(t - t_step) / tau)
#      to the data after the step, giving the time constant tau;
#   2. applies the lab's steady-state rule to the last 60 s of that step:
#      fit a straight line, net drift = |slope| * 60 s, noise = standard
#      deviation of the points about that line. The step is steady when
#      the time waited is at least 3 tau AND net drift <= 2 * noise
#      (the drift is no larger than the ordinary up-and-down wiggles).
#
# It prints one row per step, in the format of the Part 3 table.

import sys
import csv

import numpy as np

WATCH_SECONDS = 60.0     # final observation window for the drift check (s)
NOISE_FACTOR = 2.0       # drift must be <= NOISE_FACTOR * noise (2 sigma ~ wiggle size)


def load_run(path):
    t, T, pwm, hc = [], [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t.append(float(row["time_s"]))
            T.append(float(row["temperature_C"]))
            pwm.append(int(row["pwm"]))
            hc.append(int(row["heat_cool"]))
    return np.array(t), np.array(T), np.array(pwm), np.array(hc)


def split_steps(pwm, hc):
    """Return (start, end) index ranges where PWM and direction stay constant."""
    edges = [0] + [i for i in range(1, len(pwm))
                   if pwm[i] != pwm[i - 1] or hc[i] != hc[i - 1]] + [len(pwm)]
    return [(edges[k], edges[k + 1]) for k in range(len(edges) - 1)]


def fit_time_constant(t, T, t_step, T_start):
    """Least-squares exponential fit; tau found by a scan, T_ss solved linearly."""
    best = None
    for tau in np.geomspace(5.0, 3000.0, 400):
        x = 1.0 - np.exp(-(t - t_step) / tau)          # T = T_start + (T_ss - T_start) * x
        amp = np.dot(x, T - T_start) / np.dot(x, x)
        sse = np.sum((T - T_start - amp * x) ** 2)
        if best is None or sse < best[0]:
            best = (sse, tau, T_start + amp)
    return best[1], best[2]


def drift_and_noise(t, T):
    """Net drift over the window and the noise about a straight-line fit."""
    slope, intercept = np.polyfit(t, T, 1)
    resid = T - (slope * t + intercept)
    return abs(slope) * (t[-1] - t[0]), np.std(resid)


def main(path):
    t, T, pwm, hc = load_run(path)
    print(f"{'Dir':<5}{'PWM':>5}{'Start (C)':>11}{'Steady (C)':>12}{'Waited (s)':>12}"
          f"{'tau (s)':>9}{'3 tau (s)':>11}{'Drift (C)':>11}{'Noise (C)':>11}  Steady?")
    for a, b in split_steps(pwm, hc):
        if b - a < 5:
            continue                                   # too short to analyse
        ts, Ts = t[a:b], T[a:b]
        t_step = t[a - 1] if a > 0 else ts[0]          # time of the PWM change
        T_start = T[a - 1] if a > 0 else Ts[0]         # temperature just before the change
        waited = ts[-1] - t_step

        tau, _ = fit_time_constant(ts, Ts, t_step, T_start)
        window = ts >= ts[-1] - WATCH_SECONDS
        drift, noise = drift_and_noise(ts[window], Ts[window])
        steady_T = Ts[window].mean()

        ok = waited >= 3 * tau and drift <= NOISE_FACTOR * noise
        direction = "Heat" if hc[a] == 1 else "Cool"
        print(f"{direction:<5}{pwm[a]:>5}{T_start:>11.2f}{steady_T:>12.2f}{waited:>12.0f}"
              f"{tau:>9.0f}{3 * tau:>11.0f}{drift:>11.3f}{noise:>11.3f}  "
              f"{'yes' if ok else 'NO - wait longer'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python steady_state_analysis.py <run.csv>")
    main(sys.argv[1])
