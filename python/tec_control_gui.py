#!/usr/bin/env python3
"""Module 4: open-loop TEC control and calibration GUI.

Pairs with arduino/tec_open_loop_calibration/tec_open_loop_calibration.ino.

Features:
- PWM slider/text entry, HEAT/COOL selector, and STOP (PWM 0) button
- temperature and PWM strip charts; the PWM trace is red for HEAT, blue for COOL
- software safety status from the Arduino (OK / SHUTDOWN)
- drift readout (C/min over the last STEADY_WINDOW_S) to help judge steady state
- "Record steady point" appends a row to the steady-state table CSV
- full time series logged to data/module_04/run_<timestamp>.csv
"""

import csv
import math
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
import serial
from PySide6 import QtCore, QtWidgets

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
SERIAL_PORT = "/dev/cu.usbmodem1101"  # macOS example. Windows: COM3. Linux: /dev/ttyACM0
BAUD_RATE = 115200

WINDOW_SECONDS = 300.0      # visible strip-chart window
PLOT_UPDATE_MS = 200
STEADY_WINDOW_S = 60.0      # window for drift estimate and steady-state average

TEMP_WARN_LOW_C = 10.0      # Module 4 operating range
TEMP_WARN_HIGH_C = 45.0

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "module_04"
STEADY_STATE_CSV = DATA_DIR / "steady_state.csv"
# ------------------------------------------------------------------

HEAT_COLOR = (220, 40, 40)
COOL_COLOR = (40, 90, 220)

MEAS_RE = re.compile(
    r"Temperature \(C\):\s*(?P<temp>-?\d+(?:\.\d+)?|nan)\s*,\s*"
    r"Time \(s\):\s*(?P<time>-?\d+(?:\.\d+)?)\s*,\s*"
    r"PWM:\s*(?P<pwm>\d+)\s*,\s*"
    r"Heat/Cool:\s*(?P<hc>[01])"
    r"(?:\s*,\s*Safety:\s*(?P<safety>OK|SHUTDOWN))?"
)

STEADY_FIELDS = [
    "direction", "pwm", "start_temperature_C", "steady_temperature_C",
    "time_waited_s", "drift_C_per_min", "notes",
]


def parse_measurement(line: str):
    """Return a dict of fields, or None if the line is not a measurement."""
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


def drift_c_per_min(times, temps):
    """Least-squares slope of temperature vs time, in C/min."""
    n = len(times)
    if n < 3:
        return math.nan
    t_mean = sum(times) / n
    y_mean = sum(temps) / n
    sxx = sum((t - t_mean) ** 2 for t in times)
    if sxx == 0:
        return math.nan
    sxy = sum((t - t_mean) * (y - y_mean) for t, y in zip(times, temps))
    return 60.0 * sxy / sxx


class SerialReader(QtCore.QThread):
    line_received = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, ser: serial.Serial):
        super().__init__()
        self.ser = ser
        self._stop = False

    def run(self):
        try:
            while not self._stop:
                raw = self.ser.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self.line_received.emit(line)
        except Exception as e:  # serial unplugged, etc.
            self.error.emit(str(e))

    def stop(self):
        self._stop = True
        self.wait(1000)


class ControlWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Module 4 - TEC Open-Loop Calibration")
        self.resize(1200, 750)

        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.2)
        self.data = deque()  # (time_s, temperature_C, pwm, heat_cool)
        self.latest = None
        self.setpoint_start = None  # (time_s, temperature_C) when PWM/dir last changed

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_path = DATA_DIR / f"run_{stamp}.csv"
        self.csv_file = open(self.run_path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["time_s", "temperature_C", "pwm", "heat_cool", "safety"])

        self._build_ui()

        self.reader = SerialReader(self.ser)
        self.reader.line_received.connect(self.on_line)
        self.reader.error.connect(lambda msg: self.status.showMessage(f"Serial error: {msg}"))
        self.reader.start()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(PLOT_UPDATE_MS)

        # Safety: begin at PWM 0 once the board has had time to reset.
        QtCore.QTimer.singleShot(2000, self.send_command)

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        controls = QtWidgets.QHBoxLayout()
        self.heat_radio = QtWidgets.QRadioButton("HEAT")
        self.cool_radio = QtWidgets.QRadioButton("COOL")
        self.heat_radio.setChecked(True)
        self.heat_radio.toggled.connect(self.on_direction_changed)

        self.pwm_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm_slider.setRange(0, 255)
        self.pwm_slider.setTracking(False)  # send only when released
        self.pwm_slider.valueChanged.connect(self.on_slider_changed)

        self.pwm_edit = QtWidgets.QLineEdit("0")
        self.pwm_edit.setFixedWidth(60)
        self.pwm_edit.returnPressed.connect(self.on_text_entry)

        stop_button = QtWidgets.QPushButton("STOP (PWM 0)")
        stop_button.setStyleSheet("font-weight: bold;")
        stop_button.clicked.connect(self.on_stop)

        controls.addWidget(self.heat_radio)
        controls.addWidget(self.cool_radio)
        controls.addWidget(QtWidgets.QLabel("PWM"))
        controls.addWidget(self.pwm_slider, stretch=1)
        controls.addWidget(self.pwm_edit)
        controls.addWidget(stop_button)
        root.addLayout(controls)

        readouts = QtWidgets.QHBoxLayout()
        self.temp_label = QtWidgets.QLabel("T: -- C")
        self.pwm_label = QtWidgets.QLabel("Applied PWM: --")
        self.dir_label = QtWidgets.QLabel("Dir: --")
        self.drift_label = QtWidgets.QLabel("Drift: -- C/min")
        self.wait_label = QtWidgets.QLabel("Since change: -- s")
        self.safety_label = QtWidgets.QLabel("Safety: --")
        for w in (self.temp_label, self.pwm_label, self.dir_label,
                  self.drift_label, self.wait_label, self.safety_label):
            w.setStyleSheet("font-size: 15px; padding: 2px 8px;")
            readouts.addWidget(w)

        self.notes_edit = QtWidgets.QLineEdit()
        self.notes_edit.setPlaceholderText("notes for steady point")
        record_button = QtWidgets.QPushButton("Record steady point")
        record_button.clicked.connect(self.on_record_steady)
        readouts.addWidget(self.notes_edit, stretch=1)
        readouts.addWidget(record_button)
        root.addLayout(readouts)

        self.temp_plot = pg.PlotWidget(title="Temperature vs Time")
        self.temp_plot.setLabel("bottom", "Time (s)")
        self.temp_plot.setLabel("left", "Temperature (C)")
        self.temp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen("k", width=2))

        self.pwm_plot = pg.PlotWidget(title="PWM vs Time (red = HEAT, blue = COOL)")
        self.pwm_plot.setLabel("bottom", "Time (s)")
        self.pwm_plot.setLabel("left", "PWM (counts)")
        self.pwm_plot.setYRange(0, 255)
        self.pwm_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pwm_plot.setXLink(self.temp_plot)
        self.heat_curve = self.pwm_plot.plot(pen=pg.mkPen(HEAT_COLOR, width=2), connect="finite")
        self.cool_curve = self.pwm_plot.plot(pen=pg.mkPen(COOL_COLOR, width=2), connect="finite")

        for p in (self.temp_plot, self.pwm_plot):
            p.setBackground("w")
        root.addWidget(self.temp_plot, stretch=2)
        root.addWidget(self.pwm_plot, stretch=1)

        self.status = self.statusBar()
        self.status.showMessage(f"Logging to {self.run_path}")

    # ---------------- commands ----------------
    def direction(self):
        return "HEAT" if self.heat_radio.isChecked() else "COOL"

    def send_command(self):
        pwm = self.pwm_slider.value()
        cmd = f"SET PWM {pwm} DIR {self.direction()}\n"
        self.ser.write(cmd.encode("utf-8"))
        if self.latest is not None:
            self.setpoint_start = (self.latest["time_s"], self.latest["temperature_C"])
        self.status.showMessage(f"Sent: {cmd.strip()}")

    def on_slider_changed(self, value):
        self.pwm_edit.setText(str(value))
        self.send_command()

    def on_text_entry(self):
        try:
            value = max(0, min(255, int(self.pwm_edit.text())))
        except ValueError:
            value = 0
        self.pwm_edit.setText(str(value))
        if value == self.pwm_slider.value():
            self.send_command()
        else:
            self.pwm_slider.setValue(value)  # triggers send_command

    def on_direction_changed(self, _checked):
        # Change direction only from PWM 0 so the current never reverses abruptly.
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(0)
        self.pwm_slider.blockSignals(False)
        self.pwm_edit.setText("0")
        self.send_command()

    def on_stop(self):
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(0)
        self.pwm_slider.blockSignals(False)
        self.pwm_edit.setText("0")
        self.send_command()

    # ---------------- data ----------------
    @QtCore.Slot(str)
    def on_line(self, line: str):
        parsed = parse_measurement(line)
        if parsed is None:
            # Arduino status messages (e.g. SAFETY SHUTDOWN) go to the terminal.
            print(line)
            return

        self.latest = parsed
        if self.setpoint_start is None:
            self.setpoint_start = (parsed["time_s"], parsed["temperature_C"])
        self.data.append((parsed["time_s"], parsed["temperature_C"],
                          parsed["pwm"], parsed["heat_cool"]))
        while self.data and self.data[0][0] < parsed["time_s"] - WINDOW_SECONDS:
            self.data.popleft()

        self.csv_writer.writerow([parsed["time_s"], parsed["temperature_C"],
                                  parsed["pwm"], parsed["heat_cool"], parsed["safety"]])
        self.csv_file.flush()
        self.update_readouts()

    def recent_window(self):
        if not self.data:
            return [], []
        t_end = self.data[-1][0]
        t_start = max(t_end - STEADY_WINDOW_S, self.setpoint_start[0] if self.setpoint_start else 0)
        pts = [(t, T) for t, T, _, _ in self.data if t >= t_start and not math.isnan(T)]
        return [p[0] for p in pts], [p[1] for p in pts]

    def update_readouts(self):
        p = self.latest
        T = p["temperature_C"]
        self.temp_label.setText("T: nan C" if math.isnan(T) else f"T: {T:.2f} C")
        in_range = not math.isnan(T) and TEMP_WARN_LOW_C <= T <= TEMP_WARN_HIGH_C
        self.temp_label.setStyleSheet(
            "font-size: 15px; padding: 2px 8px;" + ("" if in_range else "background: orange;"))
        self.pwm_label.setText(f"Applied PWM: {p['pwm']}")
        self.dir_label.setText("Dir: HEAT" if p["heat_cool"] == 1 else "Dir: COOL")

        times, temps = self.recent_window()
        drift = drift_c_per_min(times, temps)
        self.drift_label.setText("Drift: -- C/min" if math.isnan(drift) else f"Drift: {drift:+.3f} C/min")
        if self.setpoint_start:
            self.wait_label.setText(f"Since change: {p['time_s'] - self.setpoint_start[0]:.0f} s")

        if p["safety"] == "SHUTDOWN":
            self.safety_label.setText("Safety: SHUTDOWN")
            self.safety_label.setStyleSheet(
                "font-size: 15px; padding: 2px 8px; background: red; color: white; font-weight: bold;")
        else:
            self.safety_label.setText("Safety: OK")
            self.safety_label.setStyleSheet("font-size: 15px; padding: 2px 8px; color: green;")

    def on_record_steady(self):
        if self.latest is None or self.setpoint_start is None:
            return
        times, temps = self.recent_window()
        if len(temps) < 3:
            self.status.showMessage("Not enough data since the last change to record a steady point.")
            return
        row = {
            "direction": "Heat" if self.latest["heat_cool"] == 1 else "Cool",
            "pwm": self.latest["pwm"],
            "start_temperature_C": f"{self.setpoint_start[1]:.2f}",
            "steady_temperature_C": f"{sum(temps) / len(temps):.2f}",
            "time_waited_s": f"{self.latest['time_s'] - self.setpoint_start[0]:.0f}",
            "drift_C_per_min": f"{drift_c_per_min(times, temps):+.4f}",
            "notes": self.notes_edit.text(),
        }
        new_file = not STEADY_STATE_CSV.exists()
        with open(STEADY_STATE_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=STEADY_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
        self.notes_edit.clear()
        self.status.showMessage(f"Recorded steady point: {row}")

    def update_plots(self):
        if not self.data:
            return
        ts = [d[0] for d in self.data]
        self.temp_curve.setData(ts, [d[1] for d in self.data])
        heat = [d[2] if d[3] == 1 else math.nan for d in self.data]
        cool = [d[2] if d[3] == 0 else math.nan for d in self.data]
        self.heat_curve.setData(ts, heat)
        self.cool_curve.setData(ts, cool)
        self.temp_plot.setXRange(max(0.0, ts[-1] - WINDOW_SECONDS), ts[-1], padding=0)

    def closeEvent(self, event):
        # Leave the TEC off when the GUI closes.
        try:
            self.ser.write(b"SET PWM 0 DIR HEAT\n")
            self.ser.flush()
        except Exception:
            pass
        self.timer.stop()
        self.reader.stop()
        self.ser.close()
        self.csv_file.close()
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = ControlWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
