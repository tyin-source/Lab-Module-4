# Module 4 Notes

## Setup Record

| Item | Value |
| --- | --- |
| Arduino sketch | `arduino/tec_module4_safety/tec_module4_safety.ino` |
| Python program | `python/tec_control_gui.py` |
| Serial port | |
| Power-supply voltage | |
| Power-supply current limit | |
| High-current path drawn and inspected by instructor? | |
| Thermal switch continuity (closed) checked? | |

## Software Limit Verification

| Step | Observation |
| --- | --- |
| Limit temporarily set to 30 °C and uploaded | |
| Temperature at which `SAFETY SHUTDOWN` printed | |
| GUI showed `Safety: SHUTDOWN`, applied PWM 0? | |
| Pins 9/10 at 0 (scope or serial) | |
| Limit restored to 60 °C, re-uploaded, shown to instructor | |

## Direction Check (Low PWM)

| Command | Observed temperature change | PWM trace color |
| --- | --- | --- |
| `SET PWM __ DIR HEAT` | | red |
| `SET PWM __ DIR COOL` | | blue |

## Endpoint PWM

| Direction | Maximum useful PWM | Steady temperature (°C) |
| --- | --- | --- |
| Heat (target 45 ± 2 °C) | | |
| Cool (target 10 ± 1 °C) | | |

Estimated time constant from a PWM step: ____ s, so waited about 3τ = ____ s plus 1 min per point.

Steady-state data: `data/module_04/steady_state.csv`. Saved traces: `data/module_04/tec_run_*.csv`.
