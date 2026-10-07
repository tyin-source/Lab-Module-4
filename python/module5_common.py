# Phys 39 Module 5 - shared helpers
#
# Used by the Module 5 GUI and analysis scripts:
#   - Module 4 open-loop susceptibilities (from data/module_04/part4_steady_state.csv)
#   - reading one P-control run file written by module5_p_control_gui.py
#
# Susceptibility convention (Module 5 handout):
#   chi_h = dT/dP while HEATING  (> 0)
#   chi_c = dT/dP while COOLING  (< 0); |chi_c| is used in L and the droop model
#   The Module 4 fit used signed PWM (cooling PWM negative), so its cooling
#   slope m_c is already the positive magnitude |chi_c|.

import csv
from pathlib import Path

import numpy as np

# In the repository the scripts live in <repo>/python/, so data/ and docs/ are
# one level up. If the scripts were copied into a single folder, use that
# folder instead (data/ and docs/figures/ are then created next to them).
_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent if _HERE.name == "python" else _HERE
MODULE4_DATA = REPO_ROOT / "data" / "module_04" / "part4_steady_state.csv"

# Copy of data/module_04/part4_steady_state.csv (signed PWM, steady T in C),
# used only if that file is not found next to the scripts.
MODULE4_FALLBACK = [
    (-80, 9.83), (-60, 13.25), (-40, 16.82), (-20, 20.30), (0, 23.48),
    (12, 28.90), (24, 35.35), (35, 40.40), (47, 46.10),
]
MODULE5_DATA_DIR = REPO_ROOT / "data" / "module_05"
MODULE5_FIG_DIR = REPO_ROOT / "docs" / "figures" / "module_05"


def module4_susceptibility(path: Path = MODULE4_DATA):
    """Return (chi_h, abs_chi_c) in C per PWM count from the Module 4 Part 4 data.

    Same straight-line fits as python/part4_temp_vs_pwm.py: heating uses the
    PWM 0 point and the HEAT points; cooling uses the COOL points and PWM 0.
    """
    signed_pwm = []
    temp = []
    if Path(path).exists():
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                signed_pwm.append(float(row["signed_pwm"]))
                temp.append(float(row["steady_temperature_C"]))
    else:
        for pwm, t in MODULE4_FALLBACK:
            signed_pwm.append(float(pwm))
            temp.append(t)
    signed_pwm = np.array(signed_pwm)
    temp = np.array(temp)

    heat = signed_pwm >= 0
    cool = signed_pwm <= 0
    chi_h, _ = np.polyfit(signed_pwm[heat], temp[heat], 1)
    abs_chi_c, _ = np.polyfit(signed_pwm[cool], temp[cool], 1)
    return float(chi_h), float(abs_chi_c)


def directional_susceptibility(t_set: float, t_amb: float):
    """Pick the Module 4 susceptibility magnitude for the direction the
    controller must drive to reach t_set from t_amb.

    Returns (direction, chi) with direction "HEAT" or "COOL".
    """
    chi_h, abs_chi_c = module4_susceptibility()
    if t_set >= t_amb:
        return "HEAT", chi_h
    return "COOL", abs_chi_c


def read_run(path: Path):
    """Read one run CSV from module5_p_control_gui.py into numpy arrays."""
    cols = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for name in reader.fieldnames:
            cols[name] = []
        for row in reader:
            for name in reader.fieldnames:
                cols[name].append(row[name])

    text_cols = {"dir_cmd"}
    out = {}
    for name, values in cols.items():
        if name in text_cols:
            out[name] = np.array(values)
        else:
            out[name] = np.array([float(v) for v in values])
    return out
