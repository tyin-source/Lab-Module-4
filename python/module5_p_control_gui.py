# Phys 39 Module 5 - P-only temperature control GUI
# (based on the Module 4 manual-control GUI, module4_control_gui.py)
#
# Use with arduino/module5_p_control/module5_p_control.ino (9600 baud).
#
# Arduino emits lines like (one per 1000-reading average, about 1 s):
#   Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Direction input: 1, Active PWM pin: 9, Heat/Cool: 1, Safety shutdown: 0
#
# Two modes:
#   MANUAL     - same as Module 4: direction drop-down + PWM slider.
#   P CONTROL  - on every new averaged temperature T, Python calculates
#                    e = Tset - T          (C)
#                    u = Kp * e            (signed PWM counts)
#                sends  SET PWM <P> DIR HEAT  if u >= 0
#                       SET PWM <P> DIR COOL  if u <  0
#                with P = |u| rounded to an integer and clamped to 0-255.
#
# The ONLY control calculation is in p_control() below. Kp is a single
# fixed value for the whole run (the Kp box is locked while P control runs).
# No feed-forward, gain scheduling, adaptive gain, integral, or derivative
# terms. The 0-255 clamp and the stop-on-Arduino-safety-shutdown rule are
# safety constraints, not part of the control law.
#
# Each P-control run is saved to its own CSV in data/module_05/:
#   p_<YYYYmmdd-HHMMSS>_Tset<setpoint>_Kp<gain>.csv
# columns:
#   time_s, temperature_C, setpoint_C, Kp, error_C, u, pwm_cmd, dir_cmd,
#   saturated, pwm_arduino, heat_cool, safety_shutdown, control_on
# pwm_cmd/dir_cmd are what Python sent after this temperature;
# pwm_arduino/heat_cool are what the Arduino reported it was applying when it
# printed this line (the previous command), so they lag by one line.
#
# To keep the whole transient (overshoot, undershoot, damping), each run file
# starts with the last BASELINE_SECONDS of readings from BEFORE P control was
# switched on (control_on = 0, u = 0, nothing sent), then every reading while
# P control is on (control_on = 1) until it is stopped. Let each run go until
# the temperature has clearly settled before pressing Stop.
#
# The Module 5 sketch stops the TEC if no command arrives for 3 s, so the GUI
# sends a command after every reading in both modes (manual mode re-sends the
# slider value).

import sys
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

import serial
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg

from module5_common import MODULE5_DATA_DIR, module4_susceptibility


# ------------------------------------------------------------------
# USER CONFIGURATION  (edit these near the top)
# ------------------------------------------------------------------
SERIAL_PORT = "COM5"          # Windows example. macOS: /dev/cu.usbmodemXXXX
BAUD_RATE = 9600

WINDOW_SECONDS = 300.0        # rolling window duration on the x-axis (s)
PLOT_UPDATE_MS = 100          # how often the plots redraw (ms)
SEND_DEBOUNCE_MS = 80         # manual mode: wait after last change before sending

TEMP_Y_MIN = 5.0              # temperature y-axis lower limit (C)
TEMP_Y_MAX = 50.0             # temperature y-axis upper limit (C)

PWM_Y_MIN = 0.0               # PWM y-axis lower limit
PWM_Y_MAX = 255.0             # PWM y-axis upper limit

PWM_MAX = 255                 # 8-bit PWM magnitude limit

# Allowed setpoint range in the GUI. The handout says start between 30 and
# 35 C unless the instructor approves a different range; the sign test also
# needs a setpoint slightly below room temperature.
SETPOINT_MIN_C = 10.0
SETPOINT_MAX_C = 50.0
SETPOINT_DEFAULT_C = 30.0

KP_MAX = 100.0                # largest Kp the GUI accepts (PWM counts per C)
KP_DEFAULT = 0.5              # start small (see the gain plan in the module note)

DATA_DIR = MODULE5_DATA_DIR
BASELINE_SECONDS = 30         # readings before Start written to each run file
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# P-ONLY CONTROL LAW
# ------------------------------------------------------------------
def p_control(t_set: float, temperature: float, kp: float):
    """Return (e, u, direction, pwm, saturated) for one averaged temperature."""
    e = t_set - temperature              # error e = Tset - T            [C]
    u = kp * e                           # signed PWM u = Kp e           [PWM counts]

    # Convert u to the Arduino command: the sign selects the direction,
    # the magnitude P = |u| becomes the integer PWM value.
    direction = "HEAT" if u >= 0 else "COOL"
    pwm = int(abs(u) + 0.5)              # round |u| to the nearest integer
    saturated = pwm > PWM_MAX
    pwm = min(pwm, PWM_MAX)              # clamp P to 0-255 (safety constraint)
    return e, u, direction, pwm, saturated


# ------------------------------------------------------------------
# SERIAL LINK
# ------------------------------------------------------------------
# The reader thread and the GUI both need the serial port.
# A SerialLink wraps the port with a lock so read and write do not
# happen at the same time.
class SerialLink:
    def __init__(self, port: str, baud: int):
        self.ser = serial.Serial(port, baud, timeout=0.5)
        self.lock = threading.Lock()

    def readline(self) -> bytes:
        with self.lock:
            return self.ser.readline()

    def write_line(self, text: str):
        with self.lock:
            self.ser.write((text + "\n").encode("ascii"))
            self.ser.flush()

    def close(self):
        with self.lock:
            try:
                self.ser.close()
            except Exception:
                pass


# ------------------------------------------------------------------
# READ SERIAL DATA: parser for one measurement line
# ------------------------------------------------------------------
MEAS_RE = re.compile(
    r"Temperature \(C\):\s*(?P<temp>-?\d+(?:\.\d+)?|nan)\s*,\s*"
    r"Time \(s\):\s*(?P<time>-?\d+(?:\.\d+)?)\s*,\s*"
    r"PWM:\s*(?P<pwm>\d+)\s*,\s*"
    r"Direction input:\s*(?P<dir>[01])\s*,\s*"
    r"Active PWM pin:\s*(?P<pin>\d+)\s*,\s*"
    r"Heat/Cool:\s*(?P<hc>[01])"
    r"(?:\s*,\s*Safety shutdown:\s*(?P<safety>[01]))?"
)


def parse_measurement(line: str):
    """Return dict of the extracted fields, or None if malformed."""
    m = MEAS_RE.search(line)
    if not m:
        return None
    if m.group("temp").lower() == "nan":
        return None
    return {
        "time_s": float(m.group("time")),
        "temperature_C": float(m.group("temp")),
        "pwm": int(m.group("pwm")),
        "heat_cool": int(m.group("hc")),
        "safety_shutdown": int(m.group("safety") or 0),
    }


# ------------------------------------------------------------------
# READ SERIAL DATA: background reader thread
# ------------------------------------------------------------------
class SerialReader(QtCore.QThread):
    line_received = QtCore.Signal(str)
    error = QtCore.Signal(str)

    def __init__(self, link: SerialLink):
        super().__init__()
        self.link = link
        self._stop = False

    def run(self):
        try:
            while not self._stop:
                raw = self.link.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.line_received.emit(line)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._stop = True
        self.wait(1000)


# ------------------------------------------------------------------
# GUI + PLOTS
# ------------------------------------------------------------------
class ControlGUI(QtWidgets.QMainWindow):
    def __init__(self, link=None):
        super().__init__()
        self.setWindowTitle("Module 5 - P-Only TEC Temperature Control")

        # ------- Module 4 susceptibilities (for the loop-gain display) -------
        try:
            self.chi_h, self.abs_chi_c = module4_susceptibility()
        except Exception as e:
            print(f"[warning] could not load Module 4 susceptibility: {e}")
            self.chi_h = self.abs_chi_c = None

        # ------- P-control state -------
        self.control_on = False
        self.run_setpoint = None
        self.run_kp = None
        self.csv_file = None
        self.csv_path = None
        # Recent readings while P control is off (about one per second), so
        # each run file starts with a baseline before the step.
        self.baseline = deque(maxlen=BASELINE_SECONDS)

        # ------- in-memory data for the plots -------
        self.ts = deque()            # time (s)
        self.temps = deque()         # temperature (C)
        self.setpoints = deque()     # setpoint (C), NaN when P control is off
        self.errors = deque()        # error (C), NaN when P control is off
        self.pwm_heat_ys = deque()   # Arduino PWM when heating (NaN when cooling)
        self.pwm_cool_ys = deque()   # Arduino PWM when cooling (NaN when heating)

        # ------- open serial link -------
        self.link = link if link is not None else SerialLink(SERIAL_PORT, BAUD_RATE)

        # ------- build the UI -------
        self._build_ui()

        # ------- start serial reader thread -------
        self.reader = SerialReader(self.link)
        self.reader.line_received.connect(self.on_line)
        self.reader.error.connect(self.on_serial_error)
        self.reader.start()

        # ------- plot update timer -------
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(PLOT_UPDATE_MS)

        # ------- manual command send debounce (as in Module 4) -------
        self.send_timer = QtCore.QTimer(self)
        self.send_timer.setSingleShot(True)
        self.send_timer.setInterval(SEND_DEBOUNCE_MS)
        self.send_timer.timeout.connect(self.send_manual_command)

        # Safety: PWM starts at zero (SET PWM 0 DIR HEAT at startup).
        self.schedule_send()

    # ---------------- build the GUI ----------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- row 1: manual controls (Module 4) ---
        manual_box = QtWidgets.QGroupBox("Manual (open loop)")
        row1 = QtWidgets.QHBoxLayout(manual_box)

        row1.addWidget(QtWidgets.QLabel("Direction:"))
        self.dir_combo = QtWidgets.QComboBox()
        self.dir_combo.addItems(["HEAT", "COOL"])
        self.dir_combo.currentIndexChanged.connect(self.schedule_send)
        row1.addWidget(self.dir_combo)

        row1.addSpacing(20)
        row1.addWidget(QtWidgets.QLabel("PWM:"))
        self.pwm_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm_slider.setMinimum(0)
        self.pwm_slider.setMaximum(PWM_MAX)
        self.pwm_slider.setValue(0)
        self.pwm_slider.valueChanged.connect(self.on_slider_changed)
        row1.addWidget(self.pwm_slider, stretch=1)

        self.pwm_edit = QtWidgets.QLineEdit("0")
        self.pwm_edit.setFixedWidth(60)
        self.pwm_edit.editingFinished.connect(self.on_text_edited)
        row1.addWidget(self.pwm_edit)

        layout.addWidget(manual_box)

        # --- row 2: P-only control ---
        p_box = QtWidgets.QGroupBox("P-only control:  u = Kp (Tset - T)")
        row2 = QtWidgets.QHBoxLayout(p_box)

        row2.addWidget(QtWidgets.QLabel("Tset (C):"))
        self.setpoint_spin = QtWidgets.QDoubleSpinBox()
        self.setpoint_spin.setRange(SETPOINT_MIN_C, SETPOINT_MAX_C)
        self.setpoint_spin.setDecimals(1)
        self.setpoint_spin.setSingleStep(0.5)
        self.setpoint_spin.setValue(SETPOINT_DEFAULT_C)
        row2.addWidget(self.setpoint_spin)

        row2.addSpacing(20)
        row2.addWidget(QtWidgets.QLabel("Kp (PWM/C):"))
        self.kp_spin = QtWidgets.QDoubleSpinBox()
        self.kp_spin.setRange(0.0, KP_MAX)
        self.kp_spin.setDecimals(3)
        self.kp_spin.setSingleStep(0.1)
        self.kp_spin.setValue(KP_DEFAULT)
        self.kp_spin.valueChanged.connect(self.update_loop_gain_label)
        row2.addWidget(self.kp_spin)

        row2.addSpacing(20)
        self.lbl_loop_gain = QtWidgets.QLabel()
        row2.addWidget(self.lbl_loop_gain)
        self.update_loop_gain_label()

        row2.addStretch(1)
        self.control_button = QtWidgets.QPushButton("Start P control")
        self.control_button.clicked.connect(self.on_control_button)
        row2.addWidget(self.control_button)

        layout.addWidget(p_box)

        # --- row 3: live value labels ---
        row3 = QtWidgets.QHBoxLayout()
        self.lbl_temp = QtWidgets.QLabel("T: --- C")
        self.lbl_error = QtWidgets.QLabel("e: --- C")
        self.lbl_u = QtWidgets.QLabel("u: ---")
        self.lbl_pwm = QtWidgets.QLabel("Arduino PWM: ---")
        self.lbl_dir = QtWidgets.QLabel("Direction: ---")
        self.lbl_time = QtWidgets.QLabel("Time: --- s")
        self.lbl_safety = QtWidgets.QLabel("Safety: ---")
        for lbl in (self.lbl_temp, self.lbl_error, self.lbl_u, self.lbl_pwm,
                    self.lbl_dir, self.lbl_time, self.lbl_safety):
            row3.addWidget(lbl)
        row3.addStretch(1)
        layout.addLayout(row3)

        # --- temperature plot with setpoint ---
        self.temp_plot = pg.PlotWidget()
        self.temp_plot.setLabel("left", "Temperature (C)")
        self.temp_plot.setYRange(TEMP_Y_MIN, TEMP_Y_MAX)
        self.temp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.temp_plot.addLegend(offset=(10, 10))
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen(width=2), name="T")
        self.setpoint_curve = self.temp_plot.plot(
            pen=pg.mkPen("g", width=2, style=QtCore.Qt.DashLine),
            connect="finite", name="Tset",
        )
        layout.addWidget(self.temp_plot, stretch=2)

        # --- PWM plot: red for HEAT, blue for COOL (Arduino-reported) ---
        self.pwm_plot = pg.PlotWidget()
        self.pwm_plot.setLabel("left", "PWM (red heat, blue cool)")
        self.pwm_plot.setYRange(PWM_Y_MIN, PWM_Y_MAX)
        self.pwm_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pwm_heat_curve = self.pwm_plot.plot(
            pen=pg.mkPen("r", width=2), connect="finite"
        )
        self.pwm_cool_curve = self.pwm_plot.plot(
            pen=pg.mkPen("b", width=2), connect="finite"
        )
        self.pwm_plot.setXLink(self.temp_plot)
        layout.addWidget(self.pwm_plot, stretch=1)

        # --- error plot ---
        self.error_plot = pg.PlotWidget()
        self.error_plot.setLabel("bottom", "Time (s)")
        self.error_plot.setLabel("left", "Error e = Tset - T (C)")
        self.error_plot.showGrid(x=True, y=True, alpha=0.3)
        self.error_plot.addLine(y=0, pen=pg.mkPen("k", width=1))
        self.error_curve = self.error_plot.plot(
            pen=pg.mkPen("m", width=2), connect="finite"
        )
        self.error_plot.setXLink(self.temp_plot)
        layout.addWidget(self.error_plot, stretch=1)

        self.resize(1100, 850)

    def update_loop_gain_label(self):
        kp = self.kp_spin.value()
        if self.chi_h is None:
            self.lbl_loop_gain.setText("L: Module 4 data not found")
            return
        self.lbl_loop_gain.setText(
            f"L_heat = Kp*chi_h = {kp * self.chi_h:.2f}   "
            f"L_cool = Kp*|chi_c| = {kp * self.abs_chi_c:.2f}"
        )

    # ---------------- manual control callbacks ----------------
    def on_slider_changed(self, value: int):
        if self.pwm_edit.text() != str(value):
            self.pwm_edit.setText(str(value))
        self.schedule_send()

    def on_text_edited(self):
        text = self.pwm_edit.text().strip()
        try:
            value = int(text)
        except ValueError:
            value = self.pwm_slider.value()
        value = max(0, min(PWM_MAX, value))
        self.pwm_edit.setText(str(value))
        if self.pwm_slider.value() != value:
            self.pwm_slider.setValue(value)   # triggers on_slider_changed
        else:
            self.schedule_send()

    def schedule_send(self):
        self.send_timer.start()

    def send_manual_command(self, echo: bool = True):
        # Manual commands are ignored while P control owns the output.
        if self.control_on:
            return
        pwm = self.pwm_slider.value()
        direction = self.dir_combo.currentText()
        self.send_line(f"SET PWM {pwm} DIR {direction}", echo)

    def send_line(self, cmd: str, echo: bool = True):
        try:
            self.link.write_line(cmd)
            if echo:
                print(f"[sent] {cmd}")
        except Exception as e:
            print(f"[send error] {e}")

    # ---------------- P control start / stop ----------------
    def on_control_button(self):
        if self.control_on:
            self.stop_control("stopped by user")
        else:
            self.start_control()

    def start_control(self):
        self.run_setpoint = self.setpoint_spin.value()
        self.run_kp = self.kp_spin.value()

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.csv_path = DATA_DIR / (
            f"p_{stamp}_Tset{self.run_setpoint:.1f}_Kp{self.run_kp:g}.csv"
        )
        self.csv_file = open(self.csv_path, "w", newline="")
        self.csv_file.write(
            "time_s,temperature_C,setpoint_C,Kp,error_C,u,pwm_cmd,dir_cmd,"
            "saturated,pwm_arduino,heat_cool,safety_shutdown,control_on\n"
        )
        for t, T, pwm_ard, hc, safety in self.baseline:
            self.write_row(t, T, self.run_setpoint - T, 0.0, 0,
                           "HEAT", False, pwm_ard, hc, safety, control_on=0)
        self.baseline.clear()
        self.csv_file.flush()

        self.control_on = True
        self.send_timer.stop()
        self.setpoint_spin.setEnabled(False)   # Kp and Tset stay fixed for the run
        self.kp_spin.setEnabled(False)
        self.dir_combo.setEnabled(False)
        self.pwm_slider.setEnabled(False)
        self.pwm_edit.setEnabled(False)
        self.control_button.setText("Stop P control (PWM 0)")
        print(
            f"[P control] START  Tset = {self.run_setpoint:.2f} C, "
            f"Kp = {self.run_kp:g} PWM/C, logging to {self.csv_path}"
        )

    def stop_control(self, reason: str):
        if not self.control_on:
            return
        self.control_on = False
        self.send_line("SET PWM 0 DIR HEAT")

        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
        print(f"[P control] STOP ({reason}). Saved {self.csv_path}")

        # Back to manual mode at PWM 0.
        self.pwm_slider.blockSignals(True)
        self.pwm_slider.setValue(0)
        self.pwm_slider.blockSignals(False)
        self.pwm_edit.setText("0")
        self.dir_combo.blockSignals(True)
        self.dir_combo.setCurrentText("HEAT")
        self.dir_combo.blockSignals(False)
        for w in (self.setpoint_spin, self.kp_spin, self.dir_combo,
                  self.pwm_slider, self.pwm_edit):
            w.setEnabled(True)
        self.control_button.setText("Start P control")
        self.lbl_u.setText("u: ---")
        self.lbl_error.setText("e: --- C")

    def write_row(self, t, T, e, u, pwm_cmd, direction, saturated,
                  pwm_ard, hc, safety, control_on):
        self.csv_file.write(
            f"{t:.2f},{T:.3f},{self.run_setpoint:.2f},{self.run_kp:g},"
            f"{e:.3f},{u:.3f},{pwm_cmd},{direction},{int(saturated)},"
            f"{pwm_ard},{hc},{safety},{control_on}\n"
        )

    # ---------------- one line received ----------------
    @QtCore.Slot(str)
    def on_line(self, line: str):
        parsed = parse_measurement(line)
        if parsed is None:
            # Show every non-measurement line (start-up banner, SAFETY messages).
            print(f"[arduino] {line}")
            return

        t = parsed["time_s"]
        T = parsed["temperature_C"]
        pwm_ard = parsed["pwm"]
        hc = parsed["heat_cool"]
        safety = parsed["safety_shutdown"]

        setpoint = float("nan")
        error = float("nan")

        if self.control_on:
            setpoint = self.run_setpoint
            e, u, direction, pwm_cmd, saturated = p_control(
                self.run_setpoint, T, self.run_kp
            )
            error = e

            if safety:
                # The Arduino has already forced PWM to 0. Do not keep
                # commanding the TEC: leave P control and require a restart.
                pwm_cmd, direction = 0, "HEAT"
            else:
                self.send_line(f"SET PWM {pwm_cmd} DIR {direction}")

            self.write_row(t, T, e, u, pwm_cmd, direction, saturated,
                           pwm_ard, hc, safety, control_on=1)
            self.csv_file.flush()

            self.lbl_error.setText(f"e: {e:+.2f} C")
            self.lbl_u.setText(
                f"u: {u:+.1f}" + ("  (SATURATED)" if saturated else "")
            )
            print(
                f"T = {T:.2f} C, Tset = {self.run_setpoint:.2f} C, "
                f"e = {e:+.2f} C, u = {u:+.2f}, sent PWM {pwm_cmd} {direction}"
                + ("  SATURATED" if saturated else "")
                + (f", Arduino PWM {pwm_ard} {'HEAT' if hc else 'COOL'}")
            )

            if safety:
                self.stop_control("Arduino safety shutdown")
        else:
            self.baseline.append((t, T, pwm_ard, hc, safety))
            if safety and self.pwm_slider.value() != 0:
                # Keep the Module 4 behaviour: after a safety shutdown the
                # TEC stays off until the user sets a new PWM.
                self.pwm_slider.blockSignals(True)
                self.pwm_slider.setValue(0)
                self.pwm_slider.blockSignals(False)
                self.pwm_edit.setText("0")
            # Re-send the manual command once per reading so the Arduino's
            # command timeout does not stop an open-loop run.
            self.send_manual_command(echo=False)
            print(
                f"Temperature (C): {T:.2f}, Time (s): {t:.2f}, PWM: {pwm_ard}, "
                f"Heat/Cool: {hc}, Safety shutdown: {safety}"
            )

        # Store for the plots
        self.ts.append(t)
        self.temps.append(T)
        self.setpoints.append(setpoint)
        self.errors.append(error)
        if hc == 1:
            self.pwm_heat_ys.append(pwm_ard)
            self.pwm_cool_ys.append(float("nan"))
        else:
            self.pwm_heat_ys.append(float("nan"))
            self.pwm_cool_ys.append(pwm_ard)

        # Update the live labels
        self.lbl_temp.setText(f"T: {T:.2f} C")
        self.lbl_pwm.setText(f"Arduino PWM: {pwm_ard}")
        self.lbl_dir.setText(f"Direction: {'HEAT' if hc == 1 else 'COOL'}")
        self.lbl_time.setText(f"Time: {t:.2f} s")
        if safety:
            self.lbl_safety.setText("SAFETY SHUTDOWN ACTIVE - PWM forced to 0")
            self.lbl_safety.setStyleSheet(
                "color: white; background-color: red; font-weight: bold; padding: 2px;"
            )
        else:
            self.lbl_safety.setText("Safety: OK")
            self.lbl_safety.setStyleSheet("")

    @QtCore.Slot(str)
    def on_serial_error(self, msg: str):
        print(f"[serial error] {msg}")
        if self.control_on:
            # Closes the run file; the zero command may not reach the Arduino.
            self.stop_control("serial error")

    # ---------------- plot updates ----------------
    def update_plots(self):
        if not self.ts:
            return
        xs = list(self.ts)
        self.temp_curve.setData(xs, list(self.temps))
        self.setpoint_curve.setData(xs, list(self.setpoints))
        self.pwm_heat_curve.setData(xs, list(self.pwm_heat_ys))
        self.pwm_cool_curve.setData(xs, list(self.pwm_cool_ys))
        self.error_curve.setData(xs, list(self.errors))

        t_latest = xs[-1]
        x_min = max(0.0, t_latest - WINDOW_SECONDS)
        self.temp_plot.setXRange(x_min, t_latest, padding=0)

    # ---------------- clean shutdown ----------------
    def closeEvent(self, event):
        self.stop_control("GUI closed")
        self.timer.stop()
        self.send_timer.stop()
        self.reader.stop()
        self.link.close()
        super().closeEvent(event)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    window = ControlGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
