# Module 4: Open-Loop TEC Calibration and Software Safety

Phys 39 Module 4. Starts from the Module 3 serial-command setup
([joshuaaferiat/Lab-Module-3](https://github.com/joshuaaferiat/Lab-Module-3)), adds a software
temperature limit, and measures the TEC's steady-state temperature against signed PWM.

## Files

| File | Purpose |
| --- | --- |
| `arduino/tec_module4_safety/tec_module4_safety.ino` | Module 3 Part 6 sketch plus the 60 °C software interlock. 1000-sample thermistor average, one line per second, 115200 baud. |
| `python/tec_control_gui.py` | Control GUI: PWM slider/entry, HEAT/COOL selector, STOP, safety readout, autoscaled temperature chart, PWM chart red for heat and blue for cool. Logs each run to `data/module_04/tec_run_<timestamp>.csv`. |
| `analysis/tec_calibration_analysis.py` | Part 4/5: plots steady-state T against signed PWM, fits both branches, and reports the slopes, their ratio, J/P, and the Laird data-sheet ratio. |
| `data/module_04/steady_state.csv` | Part 3 steady-state table. Fill it in during class. |
| `docs/module_notes/module_04_notes.md` | Setup record, safety-test record, and steady-state notes. |

## Serial Interface

Commands (newline-terminated): `SET PWM <0-255> DIR HEAT|COOL`.

Measurement line, about once per second:

```text
Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Safety: OK
```

`PWM` is the value actually applied to the H-bridge, so it reads 0 during a shutdown. `Safety` is `OK` or `SHUTDOWN`.

## Software Temperature Limit

- `SOFTWARE_TEMP_LIMIT_C` (60.0 °C) is a named constant near the top of the sketch.
- Every `loop()` averages 1000 ADC readings and calls `checkSafety()`.
- If the temperature is above the limit, or the thermistor reading is invalid (open or shorted divider), both H-bridge inputs (pins 9 and 10) are set to 0. The sketch prints `SAFETY SHUTDOWN: ...` once, and each measurement line shows `Safety: SHUTDOWN`.
- While the shutdown is active, commands can change direction but PWM stays at 0.
- The shutdown clears once the temperature drops 2 °C below the limit. PWM stays at 0 until Python sends a new command, so the TEC never restarts by itself.
- The hardware thermal switch (opens near 70 °C) stays in series with the TEC. It is the independent final protection.

**In-class verification:** set `SOFTWARE_TEMP_LIMIT_C = 30.0`, then upload. Warm the block past 30 °C at low heating PWM and confirm the GUI shows `Safety: SHUTDOWN` with `Applied PWM: 0`. Optionally check that pins 9 and 10 read 0 on the scope. Restore 60.0, re-upload, and show the instructor.

## Direction Mapping

HEAT = PWM on pin 10, pin 9 LOW. COOL = PWM on pin 9, pin 10 LOW. This comes from the Module 3 Part 2 direction test recorded in that repo's notes. The checked-in Module 3 Part 6 sketch had the opposite constants (`HEAT_ACTIVE_PIN = 9`). **Confirm the direction at low PWM from the temperature response.** If it is reversed, swap `HEAT_ACTIVE_PIN` and `COOL_ACTIVE_PIN`.

## Run

```sh
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python python/tec_control_gui.py --port /dev/cu.usbmodem1101     # Windows: --port COM4
```

Close the Arduino Serial Monitor first. Changing HEAT/COOL in the GUI resets PWM to 0. Closing the GUI sends PWM 0.

After filling in `data/module_04/steady_state.csv` (and the `DATASHEET` values at the top of the analysis script):

```sh
python analysis/tec_calibration_analysis.py --heat-range 0 255 --cool-range 0 255
```

Narrow the ranges to fit only the approximately linear region. The graph is saved to `docs/figures/module_04/`.

## Verification Status

The sketch has **not** been compiled with the AVR toolchain or run on hardware. Its safety logic was compiled on a host PC against a minimal Arduino mock and tested for: startup at PWM 0, heat/cool pin mapping, the trip above the limit, commands ignored while tripped, the 2 °C hysteresis, the invalid-sensor trip, malformed commands, and PWM clamping. The GUI was run headless against a simulated serial stream. Build the sketch with **Arduino: Build active sketch (Uno)** before uploading.
