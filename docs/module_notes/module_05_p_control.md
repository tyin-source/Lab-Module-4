# Module 5: P-Only Temperature Control

Handout: <https://sethfraden.github.io/Phys39F26-course/labs/lab-05/>

Python closes the feedback loop. For every averaged temperature $T$ it calculates

$$
e = T_{\mathrm{set}} - T, \qquad u = K_p e ,
$$

sends HEAT when $u \ge 0$ and COOL when $u < 0$, and sends the PWM magnitude
$P = |u|$, rounded and clamped to 0–255. The Arduino applies the command and
keeps its independent 60 °C software limit.

> **Status:** code, gain plan, and analysis scripts are ready. Measurement tables,
> figures, and the run filenames are **blank until the S10–S11 runs are done**.
> Fill every `____` with your own measurements. No numbers in the measurement
> tables below come from a simulation.

## Files and settings

| Item | Value |
| --- | --- |
| Arduino sketch | `arduino/module5_p_control/module5_p_control.ino` (9600 baud). This is the Module 4 sketch (same pins, thermistor constants, 1000-reading average, latched 60 °C limit, and serial format). The only addition is a 3 s command timeout. |
| Python controller (GUI) | `python/module5_p_control_gui.py` (set `SERIAL_PORT` at the top) |
| Control law | `p_control()` in `python/module5_p_control_gui.py`: **line 95** `e = t_set - temperature`, **line 96** `u = kp * e`; lines 100–103 convert $u$ to direction and clamped PWM |
| Module 4 susceptibility | `data/module_04/part4_steady_state.csv`, fitted by `python/module5_common.py` (same fits as `python/part4_temp_vs_pwm.py`) |
| Gain plan | `python/module5_gain_plan.py` |
| Run summary, transient, strip charts | `python/module5_run_summary.py` → `data/module_05/p_runs_summary.csv`, `docs/figures/module_05/<run>.png`, `docs/figures/module_05/transient_overlay_<part>.png` |
| Droop plots | `python/module5_droop_plot.py` → `docs/figures/module_05/droop_vs_kp.png`, `fractional_droop_vs_L.png` |
| Raw data | one CSV per P-control run: `data/module_05/p_<date-time>_Tset<T>_Kp<Kp>.csv` |
| Serial port | ____ |
| Power-supply voltage / current limit | ____ V / ____ A (set by instructor) |

### How the controller works

1. The Arduino averages 1000 raw thermistor readings (about 1 s) and converts the
   average to temperature. It prints one line per average.
2. On each line, while P control is on, the GUI runs `p_control(Tset, T, Kp)`:
   $e = T_{\mathrm{set}} - T$, $u = K_p e$, direction from the sign of $u$,
   $P = \mathrm{round}(|u|)$, clamped to 0–255.
3. The GUI sends `SET PWM <P> DIR HEAT|COOL`.
4. The GUI plots temperature with the setpoint, PWM (red = heat, blue = cool), and error.
   It also writes the run CSV.

$K_p$ and $T_{\mathrm{set}}$ are locked while a run is on, so each run has one
fixed $K_p$. There is no feed-forward, gain scheduling, adaptive gain, integral term,
or derivative term. The safety constraints are not part of the control law:

- The PWM magnitude is clamped to 0–255.
- If the Arduino reports `Safety shutdown: 1`, the GUI stops P control, sends
  `SET PWM 0 DIR HEAT`, and waits for you to start a new run.
- **Stop P control (PWM 0)** and closing the window both send PWM 0.
- **Command timeout (Arduino):** if no command arrives for 3 s while PWM > 0,
  the Arduino sets both PWM outputs to 0 and prints `SAFETY: no command ...`.
  This covers a Python crash, a frozen GUI, or an unplugged cable. The GUI sends
  a command after every reading in both modes; manual mode re-sends the slider value.

Run CSV columns: `time_s, temperature_C, setpoint_C, Kp, error_C, u, pwm_cmd,
dir_cmd, saturated, pwm_arduino, heat_cool, safety_shutdown, control_on`.

- `pwm_cmd` and `dir_cmd` are what Python sent after that temperature.
- `pwm_arduino` and `heat_cool` are what the Arduino reported applying when it
  printed the line, so they lag one line behind.
- **Transient trace:** each file starts with up to 30 s of baseline readings from
  before *Start* (`control_on = 0`). Every reading while P control is on follows
  (`control_on = 1`). The file therefore holds the whole step response: start
  temperature, rise, any overshoot and ringing, and the settled value.

## Safety boundary (check before every session)

| Item | Checked? |
| --- | --- |
| Module 4 software temperature limit present: start-up line shows `SAFETY: software temperature limit (C): 60.00` | ☐ |
| Software limit re-tested (set 30 °C, warm thermistor, see `Safety shutdown: 1`, set back to 60 °C) | ☐ |
| Command timeout: start-up line shows `SAFETY: command timeout (s): 3.0`; with PWM > 0, closing the GUI stops the TEC within about 3 s | ☐ |
| PWM starts at zero | ☐ |
| GUI shows plausible temperature (close to room temperature) | ☐ |
| Heat and cool have the correct sign (Part 2 sign test) | ☐ |
| Power-supply current limit set by instructor | ☐ |
| First setpoint between 30 °C and 35 °C (or instructor-approved) | ☐ |

Stop immediately if temperature moves the wrong way, the GUI freezes, PWM
saturates unexpectedly, or oscillations grow.

## Before class

**Module 4 susceptibility.** From the steady-state data in `data/module_04/part4_steady_state.csv`:

| Direction | Slope $dT/dP$ | Magnitude used in $L$ |
| --- | --- | --- |
| Heating | $\chi_{T,h} = +0.485$ °C/count | 0.485 °C/count |
| Cooling | $\chi_{T,c} = -0.172$ °C/count | $\lvert\chi_{T,c}\rvert = 0.172$ °C/count |

Heating is about 2.8× stronger than cooling, so $L$ must use the slope for the
direction being driven.

**Convention.** Positive $u$ selects HEAT, negative $u$ selects COOL, and the
Arduino receives $P = |u|$.

**Preliminary setpoint.** $T_{\mathrm{set}} = 30$ °C. With $T_{\mathrm{amb}} \approx 23$ °C
(Module 4 PWM-0 steady temperature 23.48 °C; room 22.58 °C on 9/30),
$e_0 = T_{\mathrm{set}} - T_{\mathrm{amb}} \approx +7$ °C. Measure today's
$T_{\mathrm{amb}}$ = ____ °C before the first run.

## Pre-class questions

1. **If $T_{\mathrm{set}} = 30$ °C and $T = 25$ °C, should the TEC heat or cool?**

   **Heat.**

   $$
   e = T_{\mathrm{set}} - T = 30\ ^\circ\mathrm{C} - 25\ ^\circ\mathrm{C} = +5\ ^\circ\mathrm{C}
   $$

   Positive error means positive $u$. The convention is that positive $u$
   selects heating. The block is below the setpoint, so the TEC should heat.

2. **If $u$ is measured in PWM counts and $e$ is measured in °C, what are the units of $K_p$?**

   $$
   u = K_p e \quad\Rightarrow\quad K_p = \frac{u}{e}
   $$

   Since $u$ is in PWM counts and $e$ is in °C,
   $[K_p] = \text{PWM counts}/^\circ\mathrm{C}$, or simply **PWM/°C**.

3. **Why does proportional control require a nonzero error to produce a nonzero output?**

   Because the control output is proportional to the error, $u = K_p e$. If
   $e = 0$, then $u = 0$. But at a nonambient setpoint, the block still
   exchanges heat with the room, so the TEC must supply nonzero heating or
   cooling to hold temperature. That nonzero output requires a nonzero error,
   which appears as steady-state **droop**.

4. **What experimental symptoms might indicate that $K_p$ is too large?**

   - sustained oscillations or ringing
   - growing oscillation amplitude
   - overshoot and repeated cycling around the setpoint
   - PWM saturating frequently
   - failure to settle to a steady temperature
   - noisy or overly aggressive PWM changes

   In short: the system may become unstable or oscillatory instead of settling smoothly.

## Part 1: Controller check (TEC power supply OFF)

Before the TEC is driven, check that the sketch and GUI do what the handout
asks. Keep the **TEC power supply off**: the Arduino and H-bridge logic still
receive and apply every command, but no current flows through the TEC.

Programs: `arduino/module5_p_control/module5_p_control.ino` and
`python/module5_p_control_gui.py` (with `python/module5_common.py`).

**1. Start-up (record the lines the GUI terminal prints)**

| Check | Expected | Observed |
| --- | --- | --- |
| Banner | `Module 5 serial-command TEC control (P control runs in Python)` | ____ |
| Software limit line | `SAFETY: software temperature limit (C): 60.00` | ____ |
| Timeout line | `SAFETY: command timeout (s): 3.0` | ____ |
| First temperature | close to room temperature, about 1 line per second | ____ °C |
| Arduino PWM at start | 0 | ____ |

**2. Control-law calculation by hand.** Start P control. For two lines from the
terminal, check $e = T_{\mathrm{set}} - T$, $u = K_p e$, and the PWM and direction
that were sent. Each line looks like
`T = 23.50 C, Tset = 30.00 C, e = +6.50 C, u = +13.00, sent PWM 13 HEAT`.

| Case | $T_{\mathrm{set}}$ (°C) | $K_p$ (PWM/°C) | $T$ (°C) | $e$ by hand | $u$ by hand | Expected command | Printed command | OK? |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| Heat ($e > 0$) | 30 | 2 | ____ | ____ | ____ | PWM round(\|u\|), HEAT | ____ | ☐ |
| Cool ($e < 0$) | 18 | 2 | ____ | ____ | ____ | PWM round(\|u\|), COOL | ____ | ☐ |
| Clamp | 30 | 100 | ____ | ____ | ____ | PWM 255, HEAT, `SATURATED` | ____ | ☐ |

Also check:
- the PWM trace is red for HEAT and blue for COOL;
- the Arduino-reported PWM on the next line equals the PWM that was sent.

**3. Stop and safety behaviour**

| Test | How | Expected | Observed |
| --- | --- | --- | --- |
| Stop button | press **Stop P control (PWM 0)** | terminal `SET PWM 0 DIR HEAT`, Arduino PWM 0, run CSV saved | ____ |
| Kp and Tset locked | try to change Kp during a run | boxes greyed out | ____ |
| Command timeout | manual PWM 30 HEAT, then close the GUI (or unplug USB) | within about 3 s the Arduino sets PWM to 0 (reopen the serial monitor to see `SAFETY: no command for 3.0 s...`) | ____ |
| Software limit (Module 4 procedure) | set `TEMP_LIMIT_C = 30.0`, upload; start P control (Tset 35, Kp 20); warm the thermistor with your fingers | `SAFETY SHUTDOWN ACTIVE`, `Safety shutdown: 1`, PWM 0, GUI prints `P control STOP (Arduino safety shutdown)`; after it cools, PWM stays 0 | ____ |
| Restore the limit | set `TEMP_LIMIT_C = 60.0`, upload again | start-up line shows `60.00` | ____ |

**4. Saved file.** Open the run CSV in `data/module_05/` and check:
- the header has 13 columns, ending in `control_on`;
- the first rows have `control_on = 0` (baseline before Start);
- then the rows have `control_on = 1`.

Part 1 test files (not measurements): ____

Exact lines that calculate $e$ and $u$: `python/module5_p_control_gui.py`
lines 95–96 (see the Files table). Be ready to point to them.

## Part 2: Sign test at low gain

"Small" gain means small dimensionless loop gain $L = K_p\lvert\chi_T\rvert \ll 1$,
not a small number for $K_p$ itself. $K_p$ has units of PWM/°C, so it has to be
compared with $1/\lvert\chi_T\rvert$: 2.1 PWM/°C for heating and 5.8 PWM/°C for cooling.

Planned sign-test runs:

| Setpoint | $e_0$ (if $T_{\mathrm{amb}} = 23$ °C) | $K_p$ (PWM/°C) | $L$ | Predicted $P_0$ | Expected direction |
| --- | ---: | ---: | ---: | ---: | --- |
| 30 °C (above room) | +7 °C | 0.5 | 0.24 | 3.5 → PWM 4 | HEAT (red) |
| 18 °C (below room) | −5 °C | 1 | 0.17 | 5 | COOL (blue) |

Note on integer PWM: the Arduino accepts whole counts, so at very low gain
$P$ is rounded. For example, $K_p = 0.5$ near the end of a heating run gives
$u \approx 2.8$, which is sent as PWM 3. For $|u| < 0.5$ nothing is sent.

Results:

| Setpoint (°C) | $T_{\mathrm{amb}}$ (°C) | $K_p$ | Sign of $e$ | Direction sent | PWM trace colour | Temperature moved toward setpoint? | Run file |
| ---: | ---: | ---: | --- | --- | --- | --- | --- |
| ____ | ____ | ____ | + | ____ | ____ | ____ | ____ |
| ____ | ____ | ____ | − | ____ | ____ | ____ | ____ |

## Part 3: Gain range and measured droop

**Gain range reasoning (needs instructor approval before running).**
Output of `python python/module5_gain_plan.py --t-set 30 --t-amb 23`:

- $P_{\mathrm{required}} = |e_0|/\chi_{T,h} = 7/0.485 = 14.4$ PWM counts.
- $P_0/P_{\mathrm{required}} = K_p\chi_T = L$. "$P_0$ well below $P_{\mathrm{required}}$"
  therefore means the same thing as small loop gain.
- The largest $K_p$ that keeps $P_0 \le 255$ is $255/7 = 36$ PWM/°C.

| Kp (PWM/°C) | L = Kp χ_h | Predicted P0 | P0 / P_required | Predicted droop (°C) | Predicted Tss (°C) | Predicted final PWM |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 0.24 | 3.5 | 0.24 | +5.63 | 24.37 | 2.8 |
| 1 | 0.49 | 7.0 | 0.49 | +4.71 | 25.29 | 4.7 |
| 2 | 0.97 | 14.0 | 0.97 | +3.55 | 26.45 | 7.1 |
| 4 | 1.94 | 28.0 | 1.94 | +2.38 | 27.62 | 9.5 |
| 8 | 3.88 | 56.0 | 3.88 | +1.43 | 28.57 | 11.5 |
| 16 | 7.76 | 112.0 | 7.76 | +0.80 | 29.20 | 12.8 |
| 32 | 15.52 | 224.0 | 15.52 | +0.42 | 29.58 | 13.6 |

The plan doubles $K_p$ from 0.5 to 32 PWM/°C. That moves $P_0$ from well below
$P_{\mathrm{required}}$ ($L = 0.24$) to well above it ($L \approx 16$) without
starting outside 0–255. Rerun the script with today's $T_{\mathrm{amb}}$ before class.

Instructor approval of range: ____ (initials / date)

**Procedure for each gain:** start from PWM 0 at room temperature, press
*Start P control*, wait until the temperature settles or clearly fails to settle,
then press *Stop P control (PWM 0)*. Let the block return to room temperature
before the next gain. Then summarize the runs:

```bash
python python/module5_run_summary.py data/module_05/p_<run>.csv --part droop --t-amb <today's Tamb>
```

| $K_p$ (PWM/°C) | Predicted $P_0$ | Setpoint (°C) | Final Temperature (°C) | Droop (°C) | Final PWM | Notes (run file) |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |

Final temperature and final PWM are averages over the last 120 s of each run
(`--settle-seconds`).

Figure (after the runs): `docs/figures/module_05/droop_vs_kp.png`, made by
`python python/module5_droop_plot.py` from `data/module_05/p_runs_summary.csv`.
Once it exists, embed it here with
`![Droop vs Kp, measured and predicted](../figures/module_05/droop_vs_kp.png)`.

## Part 4: Predicted droop from Module 4

For a heating setpoint, combining $T = T_{\mathrm{amb}} + \chi_{T,h}P$ with
$P = K_p(T_{\mathrm{set}} - T)$ gives

$$
T_{\mathrm{set}} - T = \frac{T_{\mathrm{set}} - T_{\mathrm{amb}}}{1 + \chi_{T,h}K_p},
\qquad
\frac{T_{\mathrm{set}} - T_{\mathrm{ss}}}{T_{\mathrm{set}} - T_{\mathrm{amb}}} = \frac{1}{1 + L}.
$$

The run summary calculates the predicted droop for every tested gain. The droop
plot overlays it on the measured droop.

| $K_p$ | $L$ | Measured droop (°C) | Predicted droop (°C) | Measured fraction | $1/(1+L)$ |
| ---: | ---: | ---: | ---: | ---: | ---: |
|  |  |  |  |  |  |

Figure (after the runs): `docs/figures/module_05/fractional_droop_vs_L.png`
(measured fraction vs $L$ with $1/(1+L)$), made by the same script.

## Part 5: High-gain response

Amplitude is defined as **half the peak-to-peak temperature** in the last
120 s of the run. Period is the mean time between upward crossings of that
window's mean temperature, with 0.1 °C hysteresis. Frequency = 1/period.
(`python python/module5_run_summary.py <runs> --part highgain`)

| $K_p$ (PWM/°C) | Settles? | Mean Temperature (°C) | Amplitude (°C) | Period (s) | Frequency (Hz) | Saturation? |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |

Highest gain tested: ____ PWM/°C. How it differs from the low-gain response: ____

### Transient response: overshoot at high gain, no overshoot at low gain

The instructor wants to see the time dependence, not only the final values.
Record every run from rest and let it run until it has clearly settled. The run
file holds the 30 s baseline plus the whole response. The run summary measures,
from the moment P control is switched on ($t = 0$):

| Quantity | Definition |
| --- | --- |
| $T_0$ | mean of the baseline before $t = 0$ |
| Normalised response | $y = (T - T_0)/(T_{\mathrm{ss}} - T_0)$: 0 at the start, 1 at the final (drooped) value |
| Rise time | time from $y = 0.1$ to $y = 0.9$; $\tau_{63}$ = time to $y = 0.632$ |
| Overshoot | how far the first peak goes past $T_{\mathrm{ss}}$ (°C and % of the step), and whether it also went past $T_{\mathrm{set}}$ |
| Undershoot | after an overshoot, how far the next dip falls back below $T_{\mathrm{ss}}$ (%) |
| Damping ratio | from the first overshoot $M$: $\zeta = -\ln M/\sqrt{\pi^2 + \ln^2 M}$; also from the decay of successive peaks. The damped period is the time between successive maxima. |
| Settling time | last time $T$ is outside $T_{\mathrm{ss}} \pm$ band, band $= \max(5\,\%$ of the step, 3 × noise sd$)$ |

What to expect:

- **Low gain** ($L \lesssim 1$): $T$ rises monotonically, like the first-order
  $\theta(0)e^{-t/\tau_{\mathrm{cl}}}$, and stops short of $T_{\mathrm{set}}$ by the
  droop. There is no overshoot.
- **Higher gain:** the rise is faster ($\tau_{\mathrm{cl}} = C/(H + P_uK_p)$ shrinks).
  If there is thermal delay between the TEC and the thermistor, the temperature
  can overshoot $T_{\mathrm{ss}}$ (possibly even $T_{\mathrm{set}}$), dip back
  below it (undershoot), and ring down. Lower $\zeta$ means more ringing.

The one-lump model cannot overshoot, so any overshoot measures the physics it leaves out.

```bash
python python/module5_run_summary.py <low-gain runs> <high-gain runs> --part droop --t-amb <Tamb>
```

| $K_p$ (PWM/°C) | $L$ | Response | Rise 10–90 % (s) | Overshoot (°C / %) | Past $T_{\mathrm{set}}$? | Undershoot (%) | $\zeta$ (overshoot / decay) | Damped period (s) | Settling time (s) | Run file |
| ---: | ---: | --- | ---: | ---: | --- | ---: | --- | ---: | ---: | --- |
|  |  |  |  |  |  |  |  |  |  |  |

Representative strip charts (each one marks the baseline, $t = 0$, peaks and dips,
the $T_{\mathrm{ss}}$ band, and the settling time):

- Low gain (no overshoot): `docs/figures/module_05/____.png`
- High gain (overshoot / ringing): `docs/figures/module_05/____.png`
- All gains overlaid, raw and normalised: `docs/figures/module_05/transient_overlay_<part>.png`

## Part 6: Interpretation (for A3)

### One-lump model

$$
C\frac{dT}{dt} = P_uK_p(T_{\mathrm{set}} - T) - H(T - T_{\mathrm{amb}})
$$

Units: $C$ [J/K], $P_u$ [W/PWM count], $K_p$ [PWM count/K], $H$ [W/K]. Every
term is in watts.

### 1. Why the setpoint cannot be held, and the steady-state droop

Suppose the lump is exactly at a setpoint above room temperature. Then
$e = 0$, so $u = 0$ and the TEC heat flow is zero. The room still removes
$H(T_{\mathrm{set}} - T_{\mathrm{amb}}) > 0$, so $dT/dt < 0$ and the lump cools
below the setpoint. That makes $e > 0$, which turns the heating back on. The
temperature settles where the commanded TEC heat flow exactly balances the
passive loss. For a setpoint below ambient the signs reverse: the room heats the
lump, it warms above the setpoint, $e < 0$, and the TEC cools just enough to
balance the heat leaking in.

Set $dT/dt = 0$:

$$
P_uK_p(T_{\mathrm{set}} - T_{\mathrm{ss}}) = H(T_{\mathrm{ss}} - T_{\mathrm{amb}}).
$$

Write $T_{\mathrm{ss}} - T_{\mathrm{amb}} = (T_{\mathrm{set}} - T_{\mathrm{amb}}) - (T_{\mathrm{set}} - T_{\mathrm{ss}})$
and collect the droop terms:

$$
(T_{\mathrm{set}} - T_{\mathrm{ss}})\left(P_uK_p + H\right) = H(T_{\mathrm{set}} - T_{\mathrm{amb}})
\quad\Rightarrow\quad
T_{\mathrm{set}} - T_{\mathrm{ss}} = \frac{T_{\mathrm{set}} - T_{\mathrm{amb}}}{1 + K_pP_u/H}.
$$

This is the Part 4 result with $\chi_{T,h} = P_u/H$, so $L = K_pP_u/H$.

Assumptions needed for agreement:

- one uniform temperature
- linear heat loss with constant $H$
- constant $P_u$ over the PWM and temperature range used, which also means the
  same $P_u$ that produced the Module 4 open-loop slope
- no PWM saturation
- the same $T_{\mathrm{amb}}$ as when $\chi_T$ was measured
- the run is truly at steady state
- no other heat source or control bias

### 2. Susceptibility from the model

With the loop open ($u$ an independent input), the steady state gives
$0 = P_uu - H(T - T_{\mathrm{amb}})$, so

$$
\chi_{T,u} = \frac{dT}{du} = \frac{P_u}{H},
\qquad
\left[\frac{P_u}{H}\right] = \frac{\mathrm{W}/\text{PWM count}}{\mathrm{W}/\mathrm{K}} = \frac{\mathrm{K}}{\text{PWM count}} = \frac{^\circ\mathrm{C}}{\text{PWM count}}.
$$

For heating, $u = P$, so $\chi_{T,h} = dT/dP = P_u/H$. For cooling, $P = -u$, so
$dT/dP = -P_u/H$ and $|\chi_{T,c}| = P_u/H$.

- **$P_u$ doubles:** $\chi_T$ doubles. A stronger actuator moves the temperature
  further per count.
- **$H$ doubles:** $\chi_T$ halves. Stronger coupling to the room pulls the lump
  back toward ambient.
- **$C$ alone doubles:** $\chi_T$ is unchanged, so the steady-state droop is unchanged.

$C$ multiplies only $dT/dt$, and that term vanishes at steady state, so $C$ cannot
appear in the droop. It does set how fast the lump gets there:
$\tau_{\mathrm{cl}} = C/(H + P_uK_p)$, so doubling $C$ doubles the settling time.

### 3. Loop gain for the measured runs

*(Fill in after the runs. Use the Part 4 table.)*

- Runs that genuinely have small gain ($L \ll 1$): ____
- Agreement of the measured fraction with $1/(1+L)$: ____
- Direction: use $\chi_{T,h} = 0.485$ for heating setpoints and
  $|\chi_{T,c}| = 0.172$ for cooling setpoints. The one-lump model predicts the
  same $P_u/H$ in both directions. Module 4 measured a ratio of 2.8 because Joule
  heating ($\propto I^2$) adds to Peltier heating and opposes Peltier cooling.
  A single constant $P_u$ is therefore only an approximation, and it is direction dependent.
- Other possible discrepancies:
  - $T_{\mathrm{amb}}$ drift between Module 4 and today
  - nonlinearity of $T$ vs PWM
  - rounding of $|u|$ to integer PWM at low gain
  - runs stopped before reaching steady state
  - thermistor offset

### First-order expectation and oscillations

The one-lump P model gives $\theta(t) = \theta(0)e^{-t/\tau_{\mathrm{cl}}}$: an
exponential approach to $T_{\mathrm{ss}}$ that cannot oscillate. If the apparatus
oscillates at high gain, the model is missing physics. Possible causes:

- thermal delay between the TEC face and the thermistor (a second thermal mass)
- the about 1 s measurement and averaging delay
- discrete sampling and actuation once per second
- sensor noise amplified by large $K_p$
- PWM saturation

Observed: oscillations ____ (did / did not) appear up to $K_p$ = ____ PWM/°C, because ____

## Oral review questions: P control

1. *Setpoint above room temperature, why can't P control hold it?* At the setpoint
   $u = 0$, but the room still removes heat, so $T$ falls until the error
   commands enough heating to balance the loss. Below ambient, the room heats
   the lump and $T$ rises above the setpoint until the cooling balances the heat leak.
2. *Same TEC, different insulation.* The better-insulated apparatus has smaller
   $H$, so it has larger $\chi_T = P_u/H$, larger $L$ at the same $K_p$, and less
   droop. The actuator $P_u$ and the gain $K_p$ are held fixed.
3. *Is $K_p = 1$ small?* Not by itself, because $K_p$ has units (PWM/°C). You need
   the susceptibility $\chi_T$ for the direction being driven. Here
   $L = 1 \times 0.485 = 0.49$ for heating and $L = 1 \times 0.172 = 0.17$ for
   cooling, so it is small for cooling but not much smaller than 1 for heating.
4. *Double $C$ only.* Susceptibility is unchanged and steady-state droop is
   unchanged. The settling time $\tau_{\mathrm{cl}} = C/(H + P_uK_p)$ doubles.

## Evidence checklist (S10–S11)

| Evidence | Where | Done? |
| --- | --- | --- |
| Low-gain sign test (heat and cool) | Part 2 table + run files | ☐ |
| Chosen gain range and calculation | Part 3 gain plan | ☑ (plan), ☐ (approved) |
| Droop table and high-gain table | Parts 3 and 5 | ☐ |
| Measured and predicted droop on one graph | `docs/figures/module_05/droop_vs_kp.png` | ☐ |
| Derivation linking Part 4 and the one-lump model | Part 6 | ☑ |
| Low- and high-gain strip charts with the full transient (overshoot / no overshoot) | `docs/figures/module_05/` + transient table | ☐ |
| Exact controller, sketch, raw-data filenames | Files table + run tables | ☐ (run files) |
| Explanation of droop and of oscillations (or none) | Part 6 | ☐ (oscillation result) |

## AI use note

Claude Code helped write:

- the P-control mode of the GUI, based on the Module 4 GUI
- the gain-plan, run-summary, and droop-plot scripts
- the derivation text in Part 6

The control law was checked against the handout's restrictions: one fixed $K_p$,
only $u = K_p(T_{\mathrm{set}} - T)$, with the clamp and the safety stop as
constraints.

The GUI and scripts were tested only against a simulated thermal lump. In that
test the settled droop matched $e_0/(1+L)$. The hardware test is still to be
done: ____.
