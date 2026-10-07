# Module 4 Part 1: High-Current Path (for instructor inspection)

Source: the Module 3 wiring record in `joshuaaferiat/Lab-Module-3`,
`docs/module_notes/module_03_tec_gui.md` (Part 1). **Before asking for approval,
re-check each item on the physical apparatus.** The actual wiring counts, not
this drawing.

## Diagram

![Complete high-current path](../figures/module_04/high_current_path.png)

Vector source: `docs/figures/module_04/high_current_path.svg`. Text version:

Solid lines (`│ ─`) carry high current: 18 AWG stranded copper.
Dotted lines (`┊ ┈`) are low-current logic wiring and are not part of the high-current path.

```
        ┌──────────────────────────────────────────┐
        │            POWER SUPPLY                  │
        │   Voltage: 12 V    Current limit: 10 A   │
        │        V+ (+)              V− (−)        │
        └─────────┬───────────────────┬────────────┘
                  │ 18 AWG            │ 18 AWG
                  │                   │
                  ├───────────────────┼──────────► Heat exchanger (pump + fans)
                  │                   │            powered directly from 12 V
                  │                   │            (NOT through H-bridge)
                  ▼                   ▼
        ┌─────── B+ ───────────────── B− ─────────┐
        │                                         │
        │        H-BRIDGE  (BTS7960)              │◄┈┈┈ Arduino pin 9  (PWM/LOW)
        │                                         │◄┈┈┈ Arduino pin 10 (PWM/LOW)
        │                                         │◄┈┈┈ Arduino GND (shared logic ground)
        └─────── M+ ───────────────── M− ─────────┘
                  │ 18 AWG            │ 18 AWG
                  │                   │
            ┌─────┴──────┐            │
            │  [spade]   │            │
            │  THERMAL   │  normally closed,
            │  SWITCH    │  in SERIES with TEC,
            │  (NC)      │  opens at ≈ 65 °C (Module 3 record)
            │  [spade]   │            │
            └─────┬──────┘            │
                  │ 18 AWG            │
                  ▼                   │
        ┌──────── TEC+ ─────────── TEC− ──────────┐
        │                  TEC                    │
        │      (thermistor plate / heat sink)     │
        └─────────────────────────────────────────┘

Current loop:
  PSU V+ → B+ → [H-bridge] → M+ → thermal switch → TEC+ → TEC → TEC− → M− → [H-bridge] → B− → PSU V−
  (In the other direction, current flows M− → TEC− → TEC → TEC+ → switch → M+.)
```

Opening the thermal switch breaks the M+ → TEC+ leg, so TEC current stops no
matter what the Arduino commands.

## Checklist for the instructor

| Item | Value / what to show | Verified today? |
| --- | --- | --- |
| Wire gauge | 18 AWG stranded Cu on all 5 high-current wires: V+→B+, V−→B−, M+→switch, switch→TEC+, TEC−→M− (the two switch wires end in the spade crimps) | ☐ |
| Supply polarity | V+ → B+, V− → B− | ☐ |
| TEC polarity | M+ → (switch) → TEC+; TEC− → M− | ☐ |
| Spade crimps | Both female spades on the thermal switch are secure (tug test) | ☐ |
| Thermal-switch continuity | Multimeter beeps / reads ≈ 0 Ω across the closed switch | ☐ |
| Thermal-switch placement | In series in the M+ → TEC+ leg, nothing bypasses it; mounted at: ________ | ☐ |
| Supply settings | 12 V, current limit 10 A (check the label on the side of the supply) | ☐ |
| H-bridge outputs checked with TEC power off (Module 3) | Pins 9/10 checked with the scope, TEC power off | ☐ |
| Logic ground | Arduino GND shared with H-bridge logic ground | ☐ |
| Direction mapping | Heating = PWM on pin 9 ; Cooling = PWM on pin 10 (confirmed in the TEC start-up test) | ☑ |

## Module 4 changes from Module 3

| Item | Module 3 | Module 4 |
| --- | --- | --- |
| Thermistor divider external resistor (5 V to A0; thermistor from A0 to GND) | 100 kΩ | **100 kΩ** (unchanged; `SERIES_RESISTOR = 100000.0`) |
| Raw readings averaged per temperature | 200 | 1000 (`ADC_SAMPLES`) |
| Serial update interval | 0.2 s | about 1 s (one line per 1000-reading average) |
| Software temperature limit | none | 60 °C (`TEMP_LIMIT_C`): above it, both H-bridge PWM outputs are set to 0 |
| Measurement line | ends at `Heat/Cool` | adds `, Safety shutdown: 0/1` |

## Files and settings for the module notes

| Item | Value |
| --- | --- |
| Arduino sketch | `arduino/module4_tec_control/module4_tec_control.ino` (9600 baud) |
| Python GUI | `python/module4_control_gui.py` |
| Serial port | ____ (the GUI is set to `COM5`; Module 3 used `COM4` / `/dev/cu.usbmodem1101`) |
| Power-supply voltage | ____ V (Module 3 record: 12 V) |
| Power-supply current limit | ____ A (Module 3 record: 10 A) |

## Verifying the software temperature limit (TEC power still OFF)

1. In the sketch, set `TEMP_LIMIT_C = 30.0` and upload. The GUI terminal shows
   `SAFETY: software temperature limit (C): 30.00`.
2. Set a nonzero PWM (for example 100) in the GUI so there is an output to shut off.
3. Warm the thermistor with your fingers until the averaged temperature passes 30 °C.
4. Confirm that the terminal prints `SAFETY SHUTDOWN ACTIVE ...`, the lines show `PWM: 0`
   and `Safety shutdown: 1`, the GUI banner turns red, and the PWM trace drops to 0.
   Optionally check that pins 9 and 10 both read 0 V.
5. Move the PWM slider: the Arduino keeps `PWM: 0` while the shutdown is active.
6. Let the thermistor cool below 30 °C: the terminal prints `SAFETY SHUTDOWN CLEARED ...`
   and PWM stays 0 until you send a new command.
7. Set `TEMP_LIMIT_C = 60.0`, upload again, and show the instructor the `60.00` start-up line.

## TEC start-up test (low PWM)

Room temperature 22.58 °C. Before the TEC was powered, the apparatus read 25.07 °C and was
slowly falling toward room temperature.

| Direction | PWM | Steady temperature | PWM trace colour | Target, with allowed error |
| --- | --- | --- | --- | --- |
| COOL | 80 | 9.8–9.9 °C | blue | 10 °C ± 1 °C: OK |
| HEAT | 47 | 45.2 °C | red | 45 °C ± 2 °C: OK |

## Part 4: Steady-state temperature vs PWM

Data: `data/module_04/part4_steady_state.csv`. Script: `python/part4_temp_vs_pwm.py`.
Signed PWM: positive = HEAT, negative = COOL.

![Temperature vs signed PWM](../figures/module_04/part4_temp_vs_signed_pwm.png)

| Direction | Signed PWM | Steady temperature (°C) |
| --- | --- | --- |
| COOL | −80 / −60 / −40 / −20 | 9.83 / 13.25 / 16.82 / 20.30 |
| Off | 0 | 23.48 |
| HEAT | 12 / 24 / 35 / 47 | 28.90 / 35.35 / 40.40 / 46.10 |

Linear fits: m_h = 0.485 °C/count (heating), m_c = 0.172 °C/count (cooling), r = m_h / m_c ≈ 2.8.
Both directions are close to linear. Heating is stronger because Joule heating (∝ I²) adds to
the Peltier heat when heating and opposes it when cooling.

These runs were on a different day from the start-up test (9/30: room 22.58 °C; COOL PWM 80 →
9.93 °C, HEAT PWM 47 → 45.24 °C), so the end points differ slightly because of the different
room temperature and thermal drift.

### Wiring fault found during the measurements

During the cooling measurements, the temperature reading became unstable and drifted, and the PWM
drive to the TEC was intermittent. We first suspected a short circuit. Because the problem was most
obvious in the cooling direction, we checked the logic wiring on the H-bridge's left side. Wiggling
the wires one at a time while running at low PWM showed that both the L_EN wire and the LPWM wire
(Arduino pin 10) were loose. A loose L_EN intermittently disables the left half-bridge, which
interrupts TEC current in both directions. A loose LPWM interrupts only the cooling PWM, because
LPWM is held LOW during heating anyway. Together they explain why the cooling direction was affected
most. After both wires were reseated, the cooling response was stable and the measurements were
repeated. The fault was located with this wiggle test, not confirmed with an oscilloscope.

## Things to resolve before sign-off

1. **Thermal-switch rating mismatch.** The Module 3 notes say the switch cuts off at
   **65 °C**. The Module 4 handout says it opens near **70 °C**. Read the rating
   stamped on the switch and write down the real value. Either way it is above the
   60 °C software limit, so the order of protection still holds: software limit
   (60 °C), then thermal switch.
2. **Direction mapping: resolved.** The Module 3 notes say HEAT = PWM on pin 10, but the
   sketch uses `HEAT_ACTIVE_PIN = 9` and `COOL_ACTIVE_PIN = 10`. The Module 4 start-up test
   confirmed the sketch: the PWM trace is red while heating and blue while cooling. The
   Module 3 notes were wrong; no constants were changed.
3. **Baud rate.** The Module 3 README says 115200, but the sketch calls
   `Serial.begin(9600)`. The GUI uses 9600, so they match. The README is just out of date.
4. **Serial port.** Module 3 recorded `/dev/cu.usbmodem1101` (macOS) and `COM4`
   (Windows). The GUI is set to `COM5`. Use whichever port your computer shows today.
