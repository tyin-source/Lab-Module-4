# Phys 39 Lab: TEC Temperature Control (Modules 4 and 5)

## Project purpose

A thermoelectric cooler (TEC) driven through an H-bridge heats or cools a block
whose temperature is measured with a thermistor. Module 4 characterised the
open-loop response (steady temperature vs PWM). Module 5 closes the loop with
P-only control computed in Python.

## Current working configuration (Module 5)

| Role | Path |
| --- | --- |
| Arduino sketch | `arduino/module5_p_control/module5_p_control.ino` |
| Python controller GUI | `python/module5_p_control_gui.py` |
| Module note | `docs/module_notes/module_05_p_control.md` |

## Hardware and pin assignments

| Function | Arduino pin or connection | Notes |
| --- | --- | --- |
| Thermistor divider | `A0` | 100 kΩ from 5 V to A0, thermistor from A0 to GND; 1000-reading average |
| H-bridge heat PWM | `9` | PWM while heating, LOW while cooling |
| H-bridge cool PWM | `10` | PWM while cooling, LOW while heating |
| Thermal switch | in series with TEC+ | hardware cut-off (rating to confirm: 65 or 70 °C) |
| Software limit | sketch `TEMP_LIMIT_C = 60.0` | both PWM outputs forced to 0 above 60 °C |

## How to run the instrument

1. Upload `arduino/module5_p_control/module5_p_control.ino` (9600 baud). The
   start-up banner must show `SAFETY: software temperature limit (C): 60.00`.
2. Install Python packages: `pip install -r requirements.txt`.
3. Set `SERIAL_PORT` at the top of `python/module5_p_control_gui.py`.
4. From the repository root run `python python/module5_p_control_gui.py`.
5. Serial format, one line per second:
   `Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Direction input: 1, Active PWM pin: 9, Heat/Cool: 1, Safety shutdown: 0`.
   Commands: `SET PWM <0-255> DIR HEAT|COOL`.
6. Enter Tset and Kp, press **Start P control**; **Stop P control (PWM 0)** ends the
   run. Each run is saved to `data/module_05/`.
7. Safety: PWM starts at 0; check the sign at low gain first; the GUI stops P
   control when the Arduino reports a safety shutdown; the Arduino stops the TEC
   if no command arrives for 3 s. Stop if the temperature moves the wrong way or
   oscillations grow.

Analysis (from the repository root):

```bash
python python/module5_gain_plan.py --t-set 30 --t-amb 23
python python/module5_run_summary.py data/module_05/p_<run>.csv --part droop --t-amb 23
python python/module5_droop_plot.py
```

## Repository map

- `arduino/`: `module4_tec_control/` (Module 4), `module5_p_control/` (Module 5).
- `python/`: `module4_control_gui.py`, `part4_temp_vs_pwm.py` (Module 4);
  `module5_*.py` (Module 5 controller and analysis).
- `docs/module_notes/`: `module_04_high_current_path.md`, `module_05_p_control.md`.
- `docs/figures/module_04/`, `docs/figures/module_05/`: figures.
- `data/module_04/`, `data/module_05/`: measured data.

## Current results

- Module 4 open-loop susceptibility: χ_h = 0.485 °C/count (heat),
  |χ_c| = 0.172 °C/count (cool) — `docs/module_notes/module_04_high_current_path.md`.
- Module 5: P-only runs pending (S10–S11).

## AI use note

Claude Code helped write the Module 5 P-control GUI (from the Module 4 GUI) and the
analysis scripts; they were tested against a simulated thermal model, not yet on the
hardware. See the AI use note in `docs/module_notes/module_05_p_control.md`.

## Known problems and next steps

- Confirm the thermal-switch rating (Module 3 notes: 65 °C; handout: 70 °C).
- Run the Module 5 sign test, get the gain range approved, and measure droop vs Kp.
