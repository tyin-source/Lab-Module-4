# A2 item 1: steady-state temperature vs signed PWM with a straight-line fit
# for each direction. Reads the Part 3 data and writes figures/temp_vs_signed_pwm.pdf.
# Run from the repository root:  python a2/make_figure.py

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = Path("data/module_04/part4_steady_state.csv")
OUT = Path("a2/figures/temp_vs_signed_pwm.pdf")

u, T, hc = [], [], []
with open(DATA, newline="") as f:
    for row in csv.DictReader(f):
        u.append(int(row["signed_pwm"]))
        T.append(float(row["steady_temperature_C"]))
        hc.append(row["direction"])
u, T, hc = np.array(u), np.array(T), np.array(hc)

# Each branch includes the shared PWM 0 point.
heat = u >= 0
cool = u <= 0
m_h, b_h = np.polyfit(u[heat], T[heat], 1)
m_c, b_c = np.polyfit(u[cool], T[cool], 1)
print(f"m_h = {m_h:.3f} C/count, m_c = {m_c:.3f} C/count, r = {m_h / m_c:.2f}")

# Sized for one column of a two-column REVTeX page.
fig, ax = plt.subplots(figsize=(3.4, 2.6))
ax.scatter(u[heat], T[heat], color="red", zorder=3, label="Heating data")
ax.scatter(u[cool], T[cool], color="blue", zorder=3, label="Cooling data")
xh = np.linspace(0, u[heat].max(), 50)
xc = np.linspace(u[cool].min(), 0, 50)
ax.plot(xh, m_h * xh + b_h, "r--",
        label=f"Heat fit ($u$ = 0 to {u[heat].max()}): {m_h:.3f} °C/count")
ax.plot(xc, m_c * xc + b_c, "b--",
        label=f"Cool fit ($u$ = {u[cool].min()} to 0): {m_c:.3f} °C/count")
ax.axvline(0, color="black", linewidth=0.5)
ax.set_xlabel("Signed PWM $u$ (counts)", fontsize=8)
ax.set_ylabel("Steady-state $T$ (°C)", fontsize=8)
ax.tick_params(labelsize=7)
ax.grid(True, alpha=0.4)
ax.legend(fontsize=6, loc="upper left")
fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT)
