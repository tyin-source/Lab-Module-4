# Phys 39 Module 5 - summarize P-control runs: steady state, transient, strip charts
#
# For each run CSV written by module5_p_control_gui.py this script measures
#
# STEADY STATE (last --settle-seconds of the run, the "settled window"):
#   Tss = mean temperature, droop = Tset - Tss, mean final PWM, drift,
#   oscillation amplitude = half the peak-to-peak temperature in the window,
#   period = mean time between upward crossings of the window mean
#            (hysteresis --hysteresis), frequency = 1 / period.
#
# TRANSIENT (from the moment P control is switched on, t = 0):
#   T0           start temperature (mean of the baseline rows before t = 0)
#   step         Tss - T0; the response is normalised as y = (T - T0) / (Tss - T0),
#                so y = 0 at the start and y = 1 at the final (drooped) value
#   rise time    10 % -> 90 % of the step;  tau63 = time to reach 63.2 %
#   overshoot    how far the first peak goes past Tss, in C and in % of the step
#                (counted only if larger than the noise band); also whether the
#                peak went past the setpoint itself
#   undershoot   after an overshoot, how far the next dip falls back below Tss (%)
#   damping      zeta from the first overshoot, zeta = -ln(M)/sqrt(pi^2 + ln^2 M),
#                and from the decay of successive half-cycle extrema; the damped
#                period is twice the mean time between successive extrema
#   settling     last time T is outside Tss +/- band, band = max(5 % of step, 3 sd noise)
#   response     "overshoot (underdamped)", "no overshoot (monotonic)", or
#                "sustained oscillation"
#
# A low-gain run normally rises monotonically and stops short of Tset (droop);
# a high-gain run may overshoot Tss (and even Tset), dip back, and ring down.
#
# Outputs
#   docs/figures/module_05/<run name>.png              strip chart with the transient marked
#   docs/figures/module_05/transient_overlay_<part>.png all runs of this call overlaid
#   data/module_05/p_runs_summary.csv                  one row per run (added or replaced)
#
# Room temperature: --t-amb, or else the mean of the baseline rows before
# P control started (the GUI writes up to 30 s of them), or else the first reading.
#
# Usage (from the repository root):
#   python python/module5_run_summary.py data/module_05/p_*_Kp4.csv --part droop --t-amb 23.0
#   python python/module5_run_summary.py data/module_05/p_A.csv data/module_05/p_B.csv --part highgain

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
    "response", "T0_C", "step_C", "rise_time_s", "tau63_s",
    "overshoot_C", "overshoot_pct", "peak_time_s", "peak_past_setpoint",
    "undershoot_pct", "n_extrema", "zeta_overshoot", "zeta_decay",
    "damped_period_s", "settling_time_s", "settle_band_C",
]
SMOOTH_POINTS = 5     # moving-average length (readings) used to find peaks


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


def smooth(y, n=SMOOTH_POINTS):
    if len(y) < n:
        return y.copy()
    kernel = np.ones(n) / n
    padded = np.concatenate([np.full(n // 2, y[0]), y, np.full(n - 1 - n // 2, y[-1])])
    return np.convolve(padded, kernel, mode="valid")


def first_time(t, mask):
    idx = np.flatnonzero(mask)
    return float(t[idx[0]]) if len(idx) else float("nan")


def zeta_from_ratio(r):
    """Damping ratio from a half-cycle amplitude ratio r = a_(k+1) / a_k (0 < r < 1)."""
    if not (0 < r < 1):
        return float("nan")
    ln_r = np.log(r)
    return float(-ln_r / np.sqrt(np.pi ** 2 + ln_r ** 2))


def transient_metrics(t, T, T0, T_ss, t_set, noise_sd):
    """Transient measures for one run; t starts at 0 when P control is switched on."""
    nan = float("nan")
    step = T_ss - T0
    band = max(0.05 * abs(step), 3 * noise_sd)
    out = dict(T0_C=T0, step_C=step, settle_band_C=band, rise_time_s=nan, tau63_s=nan,
               overshoot_C=0.0, overshoot_pct=0.0, peak_time_s=nan,
               peak_past_setpoint="no", undershoot_pct=nan, n_extrema=0,
               zeta_overshoot=nan, zeta_decay=nan, damped_period_s=nan,
               settling_time_s=nan, response="step too small to analyse",
               extrema=[])
    if abs(step) < 3 * band or len(T) < 10:
        return out

    s = np.sign(step)
    y = (T - T0) / step                    # normalised: 0 at start, 1 at Tss
    ys = smooth(y)
    band_y = band / abs(step)

    t10 = first_time(t, ys >= 0.1)
    t90 = first_time(t, ys >= 0.9)
    out["rise_time_s"] = t90 - t10
    out["tau63_s"] = first_time(t, ys >= 1 - np.exp(-1))

    # Alternating extrema of (y - 1): split the trace into excursions outside
    # 1 +/- band_y and take the largest deviation in each. The first excursion
    # is the initial rise from y = 0, so it is not an extremum, and the last
    # one only counts if the trace came back inside the band afterwards.
    excursions = []                        # list of index lists, one per excursion
    side = 0
    for i in range(len(ys)):
        d = ys[i] - 1
        cur = 1 if d > band_y else (-1 if d < -band_y else 0)
        if cur != 0 and cur != side:
            excursions.append([])
            side = cur
        if cur != 0 and cur == side:
            excursions[-1].append(i)
    if excursions and abs(ys[-1] - 1) > band_y:
        excursions = excursions[:-1]
    extrema = []                           # (time, deviation in units of step)
    for seg in excursions[1:]:
        k = max(seg, key=lambda j: abs(ys[j] - 1))
        extrema.append((float(t[k]), float(ys[k] - 1)))
    out["extrema"] = extrema
    out["n_extrema"] = len(extrema)

    if extrema and extrema[0][1] > 0:
        t_pk, d_pk = extrema[0]
        out["overshoot_C"] = d_pk * abs(step)
        out["overshoot_pct"] = 100 * d_pk
        out["peak_time_s"] = t_pk
        T_peak = T0 + (1 + d_pk) * step
        out["peak_past_setpoint"] = "yes" if s * (T_peak - t_set) > 0 else "no"
        out["zeta_overshoot"] = zeta_from_ratio(d_pk)
        if len(extrema) >= 2:
            out["undershoot_pct"] = 100 * abs(extrema[1][1])
            amps = np.array([abs(d) for _, d in extrema])
            r = (amps[-1] / amps[0]) ** (1 / (len(amps) - 1))
            out["zeta_decay"] = zeta_from_ratio(r)
            out["damped_period_s"] = 2 * float(np.mean(np.diff([tt for tt, _ in extrema])))
        out["response"] = "overshoot (underdamped)"
    else:
        out["response"] = "no overshoot (monotonic)"

    outside = np.abs(T - T_ss) > band
    if outside.any():
        last = np.flatnonzero(outside)[-1]
        out["settling_time_s"] = float(t[last + 1]) if last + 1 < len(t) else nan
    else:
        out["settling_time_s"] = 0.0
    return out


def summarize(path: Path, part: str, settle_s: float, t_amb, hysteresis: float):
    run = read_run(path)
    on = run["control_on"].astype(bool) if "control_on" in run else np.ones(len(run["time_s"]), bool)
    if not on.any():
        raise SystemExit(f"{path}: no rows with P control on")
    t_all = run["time_s"] - run["time_s"][on][0]       # t = 0 when P control starts
    T_all = run["temperature_C"]
    base = ~on & (t_all < 0)

    t, T = t_all[on], T_all[on]
    t_set = float(run["setpoint_C"][on][0])
    kp = float(run["Kp"][on][0])
    pwm_cmd = run["pwm_cmd"][on]
    signed_cmd = np.where(run["dir_cmd"][on] == "COOL", -pwm_cmd, pwm_cmd)

    T0 = float(np.mean(T_all[base])) if base.any() else float(T[0])
    if t_amb is None:
        t_amb = T0
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

    if base.sum() >= 5:
        noise_sd = float(np.std(T_all[base]))
    else:
        resid = Tw - np.polyval(np.polyfit(tw, Tw, 1), tw) if len(tw) > 2 else Tw - T_ss
        noise_sd = float(np.std(resid))
    tr = transient_metrics(t, T, T0, T_ss, t_set, noise_sd)
    if len(crossings) >= 3 and p2p / 2 > tr["settle_band_C"]:
        tr["response"] = "sustained oscillation"

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
        "final_pwm_mean": float(np.mean(pwm_cmd[win])),
        "saturated_frac": float(np.mean(run["saturated"][on])),
        "window_s": float(tw[-1] - tw[0]),
        "drift_C_per_min": drift,
        "p2p_C": p2p,
        "amplitude_C": p2p / 2,
        "period_s": period,
        "frequency_Hz": 1 / period if np.isfinite(period) else float("nan"),
    }
    row.update({k: v for k, v in tr.items() if k != "extrema"})

    # ---------------- strip chart ----------------
    fig, axes = plt.subplots(3, 1, figsize=(9, 8.5), sharex=True,
                             gridspec_kw={"height_ratios": [2.2, 1, 1]})
    ax = axes[0]
    if base.any():
        ax.axvspan(t_all[base][0], 0, color="gray", alpha=0.12, label="Baseline (P control off)")
        ax.plot(t_all[base], T_all[base], color="gray", lw=1.2)
    ax.plot(t, T, color="black", lw=1.5, label="T (measured)")
    ax.axvline(0, color="gray", lw=1)
    ax.axhline(t_set, color="green", ls="--", lw=1.5, label=f"Tset = {t_set:.1f} °C")
    ax.axhline(t_amb, color="gray", ls=":", lw=1.2, label=f"Tamb = {t_amb:.2f} °C")
    ax.axhline(t_set - predicted_droop, color="orange", ls="-.", lw=1.2,
               label=f"Predicted Tss = {t_set - predicted_droop:.2f} °C")
    band = tr["settle_band_C"]
    ax.axhspan(T_ss - band, T_ss + band, color="tab:blue", alpha=0.10,
               label=f"Measured Tss = {T_ss:.2f} ± {band:.2f} °C")
    for k, (tt, d) in enumerate(tr["extrema"]):
        T_ext = T0 + (1 + d) * tr["step_C"]
        ax.plot(tt, T_ext, "v" if d * np.sign(tr["step_C"]) > 0 else "^",
                color="crimson", ms=8, label="Overshoot / undershoot" if k == 0 else None)
    if tr["overshoot_pct"] > 0:
        ax.annotate(f"overshoot {tr['overshoot_C']:.2f} °C ({tr['overshoot_pct']:.0f} %)",
                    (tr["peak_time_s"], T0 + (1 + tr["overshoot_pct"] / 100) * tr["step_C"]),
                    textcoords="offset points", xytext=(10, -4), fontsize=8, color="crimson")
        ax.margins(y=0.08)
    if np.isfinite(tr["settling_time_s"]):
        ax.axvline(tr["settling_time_s"], color="tab:blue", ls=":", lw=1.2,
                   label=f"Settled at {tr['settling_time_s']:.0f} s")
    ax.set_ylabel("Temperature (°C)")
    zeta = tr["zeta_overshoot"]
    ax.set_title(
        f"P-only control: Kp = {kp:g} PWM/°C, L = {L:.2f} ({direction}) — {tr['response']}"
        + (f", ζ ≈ {zeta:.2f}" if np.isfinite(zeta) else "")
        + f"\n{path.name}", fontsize=10)
    ax.legend(fontsize=7, loc="best")
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
    ax.axvline(0, color="gray", lw=1)
    ax.set_ylabel("Signed PWM sent")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.3)

    ax = axes[2]
    ax.plot(t, run["error_C"][on], color="purple", lw=1.2)
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(0, color="gray", lw=1)
    ax.set_ylabel("e = Tset − T (°C)")
    ax.set_xlabel("Time since P control started (s)")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    MODULE5_FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = MODULE5_FIG_DIR / f"{path.stem}.png"
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)

    trace = (t_all, T_all, T0, tr["step_C"], t_set, kp, L)
    return row, fig_path, trace


def overlay_plot(traces, part):
    """All runs of one call: raw temperature and normalised response vs time."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    kps = [tr[5] for tr in traces]
    norm = matplotlib.colors.LogNorm(vmin=min(kps), vmax=max(kps)) if min(kps) > 0 and len(set(kps)) > 1 else None
    cmap = plt.get_cmap("viridis")
    for i, (t_all, T_all, T0, step, t_set, kp, L) in enumerate(sorted(traces, key=lambda r: r[5])):
        c = cmap(norm(kp)) if norm else f"C{i}"
        lbl = f"Kp = {kp:g} (L = {L:.2f})"
        ax1.plot(t_all, T_all, color=c, lw=1.4, label=lbl)
        ax1.axhline(t_set, color=c, ls="--", lw=0.8)
        if abs(step) > 0:
            ax2.plot(t_all, (T_all - T0) / step, color=c, lw=1.4, label=lbl)
    ax1.axvline(0, color="gray", lw=1)
    ax1.set_xlabel("Time since P control started (s)")
    ax1.set_ylabel("Temperature (°C)  (dashed: Tset)")
    ax1.set_title("Measured temperature")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)
    ax2.axhline(1, color="black", ls="--", lw=1, label="Final value Tss")
    ax2.axhline(0, color="gray", lw=0.6)
    ax2.axvline(0, color="gray", lw=1)
    ax2.set_xlabel("Time since P control started (s)")
    ax2.set_ylabel("(T − T0) / (Tss − T0)")
    ax2.set_title("Normalised step response (> 1 = overshoot)")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    path = MODULE5_FIG_DIR / f"transient_overlay_{part}.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


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
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, restval="")
        w.writeheader()
        for r in merged:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v)
                        for k, v in r.items() if k in SUMMARY_FIELDS})


def fmt(x, spec):
    return "—" if not np.isfinite(x) else format(x, spec)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path, nargs="+", help="run CSV files")
    ap.add_argument("--part", choices=["sign", "droop", "highgain"], required=True,
                    help="which part of the assignment these runs belong to")
    ap.add_argument("--settle-seconds", type=float, default=120.0,
                    help="length of the settled window at the end of each run (s)")
    ap.add_argument("--t-amb", type=float, default=None,
                    help="room temperature (C); default: baseline mean before the run")
    ap.add_argument("--hysteresis", type=float, default=0.1,
                    help="crossing hysteresis for the period measurement (C)")
    args = ap.parse_args()

    rows, traces = [], []
    for path in args.runs:
        row, fig_path, trace = summarize(path, args.part, args.settle_seconds,
                                         args.t_amb, args.hysteresis)
        rows.append(row)
        traces.append(trace)
        print(f"{path.name}: Tset {row['setpoint_C']:.1f} C, Kp {row['Kp']:g}, L {row['L']:.2f}, "
              f"Tss {row['T_ss_C']:.2f} C, droop {row['droop_C']:+.2f} C "
              f"(predicted {row['predicted_droop_C']:+.2f}), final PWM {row['final_pwm_mean']:.1f}, "
              f"drift {row['drift_C_per_min']:+.3f} C/min, saturated {100 * row['saturated_frac']:.0f}% of run")
        print(f"   transient: {row['response']}; rise {fmt(row['rise_time_s'], '.0f')} s, "
              f"tau63 {fmt(row['tau63_s'], '.0f')} s, overshoot {row['overshoot_C']:.2f} C "
              f"({row['overshoot_pct']:.0f} %, past Tset: {row['peak_past_setpoint']}), "
              f"undershoot {fmt(row['undershoot_pct'], '.0f')} %, zeta {fmt(row['zeta_overshoot'], '.2f')} "
              f"(decay {fmt(row['zeta_decay'], '.2f')}), settled at {fmt(row['settling_time_s'], '.0f')} s")
        print(f"   strip chart: {fig_path}")
    update_summary(rows)
    print(f"Updated {SUMMARY_PATH}")
    print(f"Overlay: {overlay_plot(traces, args.part)}")

    print()
    print("Part 3 rows:")
    print("| Kp (PWM/°C) | Predicted P0 | Setpoint (°C) | Final Temperature (°C) | Droop (°C) | Final PWM | Notes |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        print(f"| {r['Kp']:g} | {r['P0']:.1f} | {r['setpoint_C']:.1f} | {r['T_ss_C']:.2f} "
              f"| {r['droop_C']:+.2f} | {r['final_pwm_mean']:.1f} | {r['file']} |")
    print()
    print("Transient rows:")
    print("| Kp (PWM/°C) | L | Response | Rise 10–90 % (s) | Overshoot (°C / %) | Past Tset? "
          "| Undershoot (%) | ζ (overshoot / decay) | Damped period (s) | Settling time (s) | Run file |")
    print("| ---: | ---: | --- | ---: | ---: | --- | ---: | --- | ---: | ---: | --- |")
    for r in rows:
        print(f"| {r['Kp']:g} | {r['L']:.2f} | {r['response']} | {fmt(r['rise_time_s'], '.0f')} "
              f"| {r['overshoot_C']:.2f} / {r['overshoot_pct']:.0f} | {r['peak_past_setpoint']} "
              f"| {fmt(r['undershoot_pct'], '.0f')} | {fmt(r['zeta_overshoot'], '.2f')} / "
              f"{fmt(r['zeta_decay'], '.2f')} | {fmt(r['damped_period_s'], '.0f')} "
              f"| {fmt(r['settling_time_s'], '.0f')} | {r['file']} |")
    print()
    print("Part 5 rows (confirm 'Settles?' on the strip chart):")
    print("| Kp (PWM/°C) | Settles? | Mean Temperature (°C) | Amplitude (°C) | Period (s) | Frequency (Hz) | Saturation? |")
    print("| ---: | --- | ---: | ---: | ---: | ---: | --- |")
    for r in rows:
        sat = f"yes ({100 * r['saturated_frac']:.0f}% of run)" if r["saturated_frac"] > 0 else "no"
        settles = "no (sustained oscillation)" if r["response"] == "sustained oscillation" else (
            "yes" if np.isfinite(r["settling_time_s"]) else "not within run")
        print(f"| {r['Kp']:g} | {settles} | {r['T_ss_C']:.2f} | {r['amplitude_C']:.2f} "
              f"| {fmt(r['period_s'], '.1f')} | {fmt(r['frequency_Hz'], '.4f')} | {sat} |")


if __name__ == "__main__":
    main()
