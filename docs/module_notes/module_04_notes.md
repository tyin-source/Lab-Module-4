# Module 4 Notes: Open-Loop TEC Calibration and Software Safety

Fill this in during class. Record what you actually did and observed; code comments are not evidence.

## Run Record

| Item | Value |
| --- | --- |
| Date | |
| Team | |
| Arduino sketch | `arduino/tec_open_loop_calibration/tec_open_loop_calibration.ino` |
| Python program | `python/tec_control_gui.py` |
| Serial port | |
| Power-supply voltage (V) | |
| Power-supply current limit (A) | |
| Instructor wiring approval (initials/time) | |

## Part 1: Safety and Startup Checklist (power supply OFF and disconnected)

- [ ] 18 AWG stranded copper on every high-current connection: supply to H-bridge B+/B-, H-bridge M+/M- to TEC circuit, both thermal-switch wires
- [ ] Both female spade crimps secure; multimeter shows continuity through the closed thermal switch
- [ ] Thermal switch in series with the TEC current path
- [ ] H-bridge outputs were checked with TEC power off in Module 3
- [ ] Sketch uploaded, GUI running, PWM starts at 0
- [ ] Displayed temperature plausible (reading: ____ °C)
- [ ] High-current path drawn in notebook; instructor inspected gauge, polarity, spades, switch placement, current limit

Operating limits: keep 10 °C to 45 °C. Stop if temperature moves unexpectedly, display freezes, supply current rises unexpectedly, or TEC/H-bridge is hot to the touch.

## Software Temperature Limit Verification (TEC power OFF)

| Step | Result |
| --- | --- |
| Room temperature reading (°C) | |
| Temporary `SOFTWARE_TEMP_LIMIT_C` value (just below room T) | |
| Serial shows `SAFETY SHUTDOWN` message and `Safety: SHUTDOWN` | |
| Applied PWM reported as 0 | |
| Pins 9 and 10 both at 0 (how verified: scope / meter) | |
| Limit restored to 60.0 and re-uploaded; `Safety: OK` shown | |
| Instructor sign-off | |

Changed lines (for C4): the `SOFTWARE_TEMP_LIMIT_C` constant, `checkSafety()` called every `loop()` after averaging the temperature, `zeroOutput()` on both H-bridge pins, the latched `safetyShutdown` flag, and the `Safety:` field in every measurement line.

## Start the TEC

- [ ] PWM 0 and plausible temperature confirmed again
- [ ] Power enabled at approved voltage/current limit
- [ ] Low-PWM HEAT raises temperature; PWM trace is red
- [ ] Low-PWM COOL lowers temperature; PWM trace is blue
- [ ] If directions were reversed: swapped `HEAT_ACTIVE_PIN` / `COOL_ACTIVE_PIN` and re-uploaded

## Part 2: Exploratory Sweep

| Direction | Maximum useful PWM | Temperature reached (°C) | Supply current (A) | Notes |
| --- | --- | --- | --- | --- |
| Heat | | | | |
| Cool | | | | |

Planned PWM values (0, ~25%, 50%, 75%, 100% of each maximum):

- Heat: 0, ___, ___, ___, ___
- Cool: 0, ___, ___, ___, ___

## Part 3: Steady-State Measurements

Steady-state criterion used: drift below ____ °C/min over the last 60 s (GUI "Drift" readout).

The GUI's **Record steady point** button appends rows to `data/module_04/steady_state.csv`. Copy the final values here too.

| Direction | PWM | Start Temperature (°C) | Steady Temperature (°C) | Time Waited (s) | Notes |
| --- | --- | --- | --- | --- | --- |
| Heat | 0 | | | | |
| Heat | | | | | |
| Heat | | | | | |
| Heat | | | | | |
| Heat | | | | | |
| Cool | 0 | | | | |
| Cool | | | | | |
| Cool | | | | | |
| Cool | | | | | |
| Cool | | | | | |

Saved temperature-vs-time traces (from `data/module_04/run_*.csv`):

- Heating: 
- Cooling: 

Measurements to repeat at the next supervised session:

## Part 5: Laird CP14-127-045 Data Sheet (fill in yourselves)

Hot-side temperature of the table used: ____ °C

| Quantity | Value | Units | Meaning and operating condition |
| --- | --- | --- | --- |
| R | | Ω | |
| I_max | | A | |
| Q_max (ΔT = 0) | | W | |
| ΔT_max | | °C | |
