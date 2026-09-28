# Module 4: Open-Loop TEC Calibration and Software Safety

Phys 39 Module 4. Starts from the Module 3 Python-commanded TEC setup, adds a software temperature limit (60 °C) alongside the independent hardware thermal switch (~70 °C), and measures steady-state temperature against signed PWM to find the heating and cooling susceptibilities for A2.

## Project Files

| File | Purpose |
| --- | --- |
| `arduino/tec_open_loop_calibration/tec_open_loop_calibration.ino` | Module 3 Part 6 serial-command sketch plus the software temperature limit. 115200 baud. |
| `python/tec_control_gui.py` | Control GUI: PWM slider/entry, HEAT/COOL selector, STOP, temperature and PWM strip charts (PWM red = HEAT, blue = COOL), safety status, drift readout, steady-point recording, CSV logging. |
| `analysis/tec_calibration_analysis.py` | Parts 4–5: plots steady T vs signed PWM, fits each direction, prints χ_heat, χ_cool, their ratio, implied J/P, and the Laird max-current prediction. |
| `docs/module_notes/module_04_notes.md` | In-class checklist, safety-test record, run record, and data tables. |
| `data/module_04/` | `run_<timestamp>.csv` time series and `steady_state.csv` (written by the GUI). |
| `docs/figures/module_04/` | Calibration graph output. |

## Serial Interface

Commands (newline-terminated, case-insensitive):

```text
SET PWM 120 DIR HEAT
SET PWM 45 DIR COOL
```

Measurement line, every 200 ms:

```text
Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Safety: OK
```

- `PWM` is the value actually applied (0 while shut down).
- `Heat/Cool` is 1 for HEAT, 0 for COOL.
- `Safety` is `OK` or `SHUTDOWN`. A one-time `SAFETY SHUTDOWN: ...` message is also printed when the limit trips.

Temperature is the average of 200 raw ADC readings (Module 2 sequence: 100–1000), used for the display, the logged data, and the safety check.

## Software Temperature Limit

- `SOFTWARE_TEMP_LIMIT_C = 60.0` is a named constant near the top of the sketch.
- `loop()` measures the averaged temperature and calls `checkSafety()` on every pass.
- If the temperature exceeds the limit, or the reading is invalid (`nan`), both H-bridge pins are set to 0 and the shutdown latches.
- Serial printing continues, so the GUI shows `Safety: SHUTDOWN` in red.
- The latch clears only when the temperature is back at or below the limit **and** a new `SET` command arrives. Commands sent while it is too hot are ignored.
- The hardware thermal switch remains in series with the TEC as the independent final protection.

**Verification test (TEC power OFF):** set `SOFTWARE_TEMP_LIMIT_C` just below room temperature, upload, and confirm `Safety: SHUTDOWN`, applied PWM 0, and both pins 9 and 10 at 0. Restore `60.0`, re-upload, and show the instructor. Do not heat the apparatus to 60 °C.

## Direction Mapping

The sketch uses HEAT = pin 10 PWM / pin 9 LOW and COOL = pin 9 PWM / pin 10 LOW, which is the mapping recorded in the Module 3 README. (The Module 3 sketch itself had the opposite constants.) **Confirm this at low PWM before calibrating.** If HEAT cools the block, swap `HEAT_ACTIVE_PIN` and `COOL_ACTIVE_PIN`.

## Build and Run

1. Install the Python dependencies:

	```sh
	python3 -m venv .venv
	source .venv/bin/activate
	python -m pip install -r requirements.txt
	```

2. Set `SERIAL_PORT` at the top of `python/tec_control_gui.py`.
3. Upload the sketch with TEC power off. Close Serial Monitor before starting Python.
4. Run `python python/tec_control_gui.py`. PWM starts at 0. Changing HEAT/COOL resets PWM to 0 first.
5. At each PWM setting, wait until the **Drift** readout (least-squares slope over the last 60 s since the last change) is small enough to call steady. Then add a note if needed and click **Record steady point**. This records the 60 s mean temperature, the start temperature, and the time waited.
6. After class, adjust `HEAT_FIT_RANGE` / `COOL_FIT_RANGE` and the Laird values at the top of the analysis script, then run:

	```sh
	python analysis/tec_calibration_analysis.py
	```

## Analysis Relations (Part 5)

With cycle-averaged Peltier and object-face Joule rates `P·D` and `J·D` and effective conductance `K`:

- χ_heat ∝ (P + J)/K
- |χ_cool| ∝ (P − J)/K
- |χ_heat/χ_cool| = (P + J)/(P − J), so J/P = (ratio − 1)/(ratio + 1)
- Data-sheet prediction at ΔT = 0: Q_J,obj = ½·I_max²·R, Q_P = Q_max + Q_J,obj, ratio = (Q_P + Q_J,obj)/(Q_P − Q_J,obj)
