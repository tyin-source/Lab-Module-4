#!/usr/bin/env python3
"""Phys 39 Module 4: TEC control GUI for open-loop calibration.

Pairs with arduino/tec_module4_safety/tec_module4_safety.ino at 115200 baud.

Features:
- PWM slider and text box, HEAT/COOL selector, and STOP button
- temperature, time, applied PWM, direction, and software-safety readouts
- temperature strip chart with an automatically scaled y-axis so small
  steady-state drifts are visible
- PWM strip chart drawn red while heating and blue while cooling
- CSV logging of every measurement line (a new file for each run)

Measurement line read from the Arduino:
    Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Safety: OK
Command sent to the Arduino:
    SET PWM 120 DIR HEAT
"""

import argparse
import csv
import math
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
import serial
from PySide6 import QtCore, QtGui, QtWidgets

# ------------------------------------------------------------------
# CONFIGURATION  (edit these near the top, or pass --port)
# ------------------------------------------------------------------
SERIAL_PORT = "/dev/cu.usbmodem1101"   # macOS example. Windows: COM4. Linux: /dev/ttyACM0
BAUD_RATE = 115200

WINDOW_SECONDS = 300.0      # visible strip-chart window; long enough to judge steady state
PLOT_UPDATE_MS = 200        # plot refresh interval (ms)
TEMP_MIN_SPAN_C = 0.5       # smallest temperature-axis span, so noise is not over-magnified
TEMP_PAD_FRACTION = 0.1     # headroom above and below the visible data

HEAT_COLOR = (220, 30, 30)
COOL_COLOR = (30, 80, 220)

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "module_04"
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# READ SERIAL DATA: parse one measurement line
# ------------------------------------------------------------------
MEAS_RE = re.compile(
    r"Temperature \(C\):\s*(?P<temp>[-+]?\d+(?:\.\d+)?|nan)\s*,\s*"
    r"Time \(s\):\s*(?P<time>[-+]?\d+(?:\.\d+)?)\s*,\s*"
    r"PWM:\s*(?P<pwm>\d+)\s*,\s*"
    r"Heat/Cool:\s*(?P<hc>[01])"
    r"(?:\s*,\s*Safety:\s*(?P<safety>OK|SHUTDOWN))?"
)


def parse_measurement(line: str):
    """Return a dict of fields, or None if the line is not a measurement line."""
    m = MEAS_RE.search(line)
    if not m:
        return None
    temp = m.group("temp")
    return {
        "time_s": float(m.group("time")),
        "temperature_C": math.nan if temp == "nan" else float(temp),
        "pwm": int(m.group("pwm")),
        "heat_cool": int(m.group("hc")),
        "safety": m.group("safety") or "OK",
    }


def autoscale_range(values, min_span=TEMP_MIN_SPAN_C, pad_fraction=TEMP_PAD_FRACTION):
    """Return (low, high) that covers the finite values with padding and a minimum span."""
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return None
    lo, hi = min(finite), max(finite)
    span = max(hi - lo, min_span)
    center = 0.5 * (lo + hi)
    half = 0.5 * span * (1.0 + 2.0 * pad_fraction)
    return center - half, center + half


def split_by_direction(times, pwms, heat_cool):
    """Split the PWM trace into heat and cool arrays, using NaN to break the line.

    The sample where the direction changes is included in both traces so the
    colored segments join without a gap.
    """
    t = np.asarray(times, dtype=float)
    p = np.asarray(pwms, dtype=float)
    hc = np.asarray(heat_cool, dtype=int)
    heat_mask = hc == 1
    cool_mask = hc == 0
    # extend each mask forward one sample so the joining segment is drawn
    heat_draw = heat_mask.copy()
    cool_draw = cool_mask.copy()
    heat_draw[1:] |= heat_mask[:-1]
    cool_draw[1:] |= cool_mask[:-1]
    heat = np.where(heat_draw, p, np.nan)
    cool = np.where(cool_draw, p, np.nan)
    return t, heat, cool


# ------------------------------------------------------------------
# READ SERIAL DATA: background thread
# ------------------------------------------------------------------
class SerialWorker(QtCore.QThread):
    line_received = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, ser):
        super().__init__()
        self.ser = ser
        self._stop = False

    def run(self):
        try:
            while not self._stop:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.line_received.emit(line)
        except Exception as e:  # serial unplugged, etc.
            if not self._stop:
                self.error.emit(str(e))

    def stop(self):
        self._stop = True
        self.wait(1500)


# ------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------
class ControlWindow(QtWidgets.QMainWindow):
    def __init__(self, ser, csv_path: Path):
        super().__init__()
        self.setWindowTitle("Module 4 - TEC Open-Loop Control")
        self.resize(1200, 750)

        self.ser = ser
        self.requested_pwm = 0
        self.requested_direction = "HEAT"

        # STORE RECENT DATA
        self.times = deque()
        self.temps = deque()
        self.pwms = deque()
        self.hcs = deque()

        # SAVE THE CSV FILE
        self.csv_path = csv_path
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_file = open(self.csv_path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["time_s", "temperature_C", "pwm", "heat_cool", "safety"])
        self.csv_file.flush()

        self._build_ui()

        # READ SERIAL DATA
        self.worker = SerialWorker(self.ser)
        self.worker.line_received.connect(self.on_line)
        self.worker.error.connect(self.on_serial_error)
        self.worker.start()

        # UPDATE THE PLOTS
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(PLOT_UPDATE_MS)

        # Safety: start at PWM 0.
        self.send_command()

    # -------------- layout --------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        controls = QtWidgets.QHBoxLayout()

        self.heat_button = QtWidgets.QRadioButton("HEAT")
        self.cool_button = QtWidgets.QRadioButton("COOL")
        self.heat_button.setChecked(True)
        self.heat_button.setStyleSheet(f"color: rgb{HEAT_COLOR}; font-weight: bold;")
        self.cool_button.setStyleSheet(f"color: rgb{COOL_COLOR}; font-weight: bold;")
        self.direction_group = QtWidgets.QButtonGroup(self)
        self.direction_group.addButton(self.heat_button)
        self.direction_group.addButton(self.cool_button)
        self.heat_button.toggled.connect(self.on_direction_changed)

        self.pwm_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm_slider.setRange(0, 255)
        self.pwm_slider.setTracking(False)   # send one command on release, not a sweep
        self.pwm_slider.valueChanged.connect(self.on_slider_changed)
        self.pwm_slider.sliderMoved.connect(lambda v: self.pwm_edit.setText(str(v)))

        self.pwm_edit = QtWidgets.QLineEdit("0")
        self.pwm_edit.setFixedWidth(60)
        self.pwm_edit.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"\d{1,3}")))
        self.pwm_edit.returnPressed.connect(self.on_text_entry)

        self.stop_button = QtWidgets.QPushButton("STOP (PWM 0)")
        self.stop_button.setStyleSheet("font-weight: bold;")
        self.stop_button.clicked.connect(self.on_stop)

        controls.addWidget(self.heat_button)
        controls.addWidget(self.cool_button)
        controls.addWidget(QtWidgets.QLabel("PWM"))
        controls.addWidget(self.pwm_slider, stretch=1)
        controls.addWidget(self.pwm_edit)
        controls.addWidget(self.stop_button)
        root.addLayout(controls)

        readouts = QtWidgets.QHBoxLayout()
        self.temperature_label = QtWidgets.QLabel("Temperature (C): --")
        self.time_label = QtWidgets.QLabel("Time (s): --")
        self.pwm_label = QtWidgets.QLabel("Applied PWM: --")
        self.direction_label = QtWidgets.QLabel("Direction: --")
        self.safety_label = QtWidgets.QLabel("Safety: --")
        for w in (self.temperature_label, self.time_label, self.pwm_label,
                  self.direction_label, self.safety_label):
            w.setStyleSheet("font-size: 14pt;")
            readouts.addWidget(w)
        root.addLayout(readouts)

        pg.setConfigOptions(antialias=True, background="w", foreground="k")
        self.temp_plot = pg.PlotWidget(title="Temperature vs Time")
        self.temp_plot.setLabel("bottom", "Time (s)")
        self.temp_plot.setLabel("left", "Temperature (°C)")
        self.temp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen((40, 40, 40), width=2))

        self.pwm_plot = pg.PlotWidget(title="PWM vs Time (red = heat, blue = cool)")
        self.pwm_plot.setLabel("bottom", "Time (s)")
        self.pwm_plot.setLabel("left", "PWM (counts)")
        self.pwm_plot.setYRange(-5, 260)
        self.pwm_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pwm_plot.setXLink(self.temp_plot)
        self.heat_curve = self.pwm_plot.plot(pen=pg.mkPen(HEAT_COLOR, width=2), connect="finite")
        self.cool_curve = self.pwm_plot.plot(pen=pg.mkPen(COOL_COLOR, width=2), connect="finite")

        root.addWidget(self.temp_plot, stretch=3)
        root.addWidget(self.pwm_plot, stretch=2)

        self.statusBar().showMessage(f"Logging to {self.csv_path}")

    # -------------- controls --------------
    def on_direction_changed(self, _checked):
        direction = "HEAT" if self.heat_button.isChecked() else "COOL"
        if direction == self.requested_direction:
            return
        # Safety: changing direction returns PWM to 0 so current never reverses at high duty.
        self.requested_direction = direction
        self.set_pwm_widgets(0)
        self.requested_pwm = 0
        self.send_command()

    def on_slider_changed(self, value):
        self.requested_pwm = max(0, min(255, int(value)))
        self.pwm_edit.setText(str(self.requested_pwm))
        self.send_command()

    def on_text_entry(self):
        text = self.pwm_edit.text().strip()
        value = max(0, min(255, int(text))) if text else 0
        self.requested_pwm = value
        self.set_pwm_widgets(value)
        self.send_command()

    def on_stop(self):
        self.requested_pwm = 0
        self.set_pwm_widgets(0)
        self.send_command()

    def set_pwm_widgets(self, value):
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(value)
        self.pwm_slider.blockSignals(False)
        self.pwm_edit.setText(str(value))

    def send_command(self):
        command = f"SET PWM {self.requested_pwm} DIR {self.requested_direction}\n"
        try:
            self.ser.write(command.encode("utf-8"))
            print(f">> {command.strip()}")
        except Exception as e:
            self.on_serial_error(str(e))

    # -------------- incoming data --------------
    @QtCore.Slot(str)
    def on_line(self, line: str):
        parsed = parse_measurement(line)
        if parsed is None:
            # Status and safety messages from the Arduino
            print(f"[arduino] {line}")
            if "SAFETY" in line:
                self.statusBar().showMessage(line)
            return

        t = parsed["time_s"]
        T = parsed["temperature_C"]
        pwm = parsed["pwm"]
        hc = parsed["heat_cool"]
        safety = parsed["safety"]
        direction = "HEAT" if hc == 1 else "COOL"

        print(f"t={t:8.2f} s  T={T:6.2f} C  PWM={pwm:3d}  {direction}  Safety={safety}")

        self.temperature_label.setText(f"Temperature (C): {T:.2f}")
        self.time_label.setText(f"Time (s): {t:.1f}")
        self.pwm_label.setText(f"Applied PWM: {pwm}")
        color = HEAT_COLOR if hc == 1 else COOL_COLOR
        self.direction_label.setText(f"Direction: {direction}")
        self.direction_label.setStyleSheet(f"font-size: 14pt; color: rgb{color};")
        if safety == "SHUTDOWN":
            self.safety_label.setText("Safety: SHUTDOWN")
            self.safety_label.setStyleSheet(
                "font-size: 14pt; font-weight: bold; color: white; background: rgb(200, 0, 0);")
            if self.requested_pwm != 0:
                # Mirror the Arduino: the TEC stays off until the user sends a new command.
                self.requested_pwm = 0
                self.set_pwm_widgets(0)
        else:
            self.safety_label.setText("Safety: OK")
            self.safety_label.setStyleSheet("font-size: 14pt; color: rgb(0, 130, 0);")

        self.times.append(t)
        self.temps.append(T)
        self.pwms.append(pwm)
        self.hcs.append(hc)
        while self.times and self.times[0] < t - WINDOW_SECONDS:
            self.times.popleft()
            self.temps.popleft()
            self.pwms.popleft()
            self.hcs.popleft()

        self.csv_writer.writerow([f"{t:.2f}", f"{T:.3f}", pwm, hc, safety])
        self.csv_file.flush()

    @QtCore.Slot(str)
    def on_serial_error(self, msg: str):
        print(f"[serial error] {msg}")
        self.statusBar().showMessage(f"Serial error: {msg}")

    # -------------- plots --------------
    def update_plots(self):
        if not self.times:
            return
        times = list(self.times)
        temps = np.array(self.temps, dtype=float)
        self.temp_curve.setData(times, temps, connect="finite")

        t, heat, cool = split_by_direction(times, self.pwms, self.hcs)
        self.heat_curve.setData(t, heat, connect="finite")
        self.cool_curve.setData(t, cool, connect="finite")

        t_latest = times[-1]
        self.temp_plot.setXRange(max(0.0, t_latest - WINDOW_SECONDS), t_latest, padding=0)
        y_range = autoscale_range(temps)
        if y_range is not None:
            self.temp_plot.setYRange(*y_range, padding=0)

    # -------------- clean shutdown --------------
    def closeEvent(self, event):
        self.timer.stop()
        # Safety: leave the TEC off when the GUI closes.
        self.requested_pwm = 0
        self.send_command()
        self.worker.stop()
        try:
            self.ser.close()
        except Exception:
            pass
        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
        super().closeEvent(event)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", default=SERIAL_PORT, help=f"serial port (default {SERIAL_PORT})")
    parser.add_argument("--baud", type=int, default=BAUD_RATE)
    parser.add_argument("--csv", type=Path, default=None,
                        help="CSV output path (default data/module_04/tec_run_<timestamp>.csv)")
    args = parser.parse_args()

    csv_path = args.csv or DATA_DIR / f"tec_run_{datetime.now():%Y%m%d_%H%M%S}.csv"
    ser = serial.serial_for_url(args.port, args.baud, timeout=0.5)

    app = QtWidgets.QApplication(sys.argv)
    window = ControlWindow(ser, csv_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
