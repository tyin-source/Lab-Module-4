# Module 5 data: P-only control runs

- `p_<YYYYmmdd-HHMMSS>_Tset<setpoint>_Kp<gain>.csv`: one file per P-control run,
  written by `python/module5_p_control_gui.py`. Columns:
  `time_s, temperature_C, setpoint_C, Kp, error_C, u, pwm_cmd, dir_cmd, saturated,
  pwm_arduino, heat_cool, safety_shutdown, control_on`. `time_s` is Arduino time;
  `pwm_arduino`/`heat_cool` are what the Arduino reported applying (one line behind
  `pwm_cmd`/`dir_cmd`).
- `p_runs_summary.csv`: one row per analysed run, written by
  `python/module5_run_summary.py` (settled temperature, droop, predicted droop,
  loop gain, oscillation amplitude/period, saturation). `part` is `sign`, `droop`,
  or `highgain`.

Record today's room temperature and which run belongs to which part of the
assignment in `docs/module_notes/module_05_p_control.md`.

Each run file starts with up to 30 s of baseline readings from before P control
was switched on (`control_on = 0`), so the whole transient is recorded.
