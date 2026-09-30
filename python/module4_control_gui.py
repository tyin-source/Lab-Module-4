# Phys 39 Module 4 - Part 1
# Manual-control GUI (display + manual commands) with safety-shutdown display
# (based on the Module 3 Part 5 GUI)
#
# Arduino emits lines like:
#   Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Direction input: 1, Active PWM pin: 9, Heat/Cool: 1, Safety shutdown: 0
#
# The trailing "Safety shutdown" field is optional, so Module 3 sketches that
# do not print it still work (it is treated as 0).
#
# This program:
#   - reads serial data and parses five fields
#     (time, temperature, PWM, heat/cool, safety shutdown)
#   - prints those fields to the terminal
#   - plots temperature vs Arduino time
#   - plots PWM vs Arduino time: RED for HEAT, BLUE for COOL
#   - shows live Temperature / PWM / Direction / Time / Safety status
#   - sends manual commands:  SET PWM <n> DIR HEAT
#                             SET PWM <n> DIR COOL
#   - saves CSV with columns: time_s, temperature_C, pwm, heat_cool, safety_shutdown
#   - does NOT do feedback control

import sys
import re
import threading
from collections import deque
from pathlib import Path

import serial
from PySide6 import QtCore, QtWidgets
import pyqtgraph as pg


# ------------------------------------------------------------------
# USER CONFIGURATION  (edit these near the top)
# ------------------------------------------------------------------
SERIAL_PORT = "COM5"          # Windows example. macOS: /dev/cu.usbmodemXXXX
BAUD_RATE = 9600

WINDOW_SECONDS = 60.0         # rolling window duration on the x-axis (s)
PLOT_UPDATE_MS = 100          # how often the plots redraw (ms)
SEND_DEBOUNCE_MS = 80         # wait after last change before sending a command

TEMP_Y_MIN = 15.0             # temperature y-axis lower limit (C)
TEMP_Y_MAX = 45.0             # temperature y-axis upper limit (C)

PWM_Y_MIN = 0.0               # PWM y-axis lower limit
PWM_Y_MAX = 255.0             # PWM y-axis upper limit

CSV_PATH = Path("data/module_04/part1_control_gui.csv")
# ------------------------------------------------------------------


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
# This regex matches the Arduino measurement line.
# It extracts Temperature, Time, PWM, Heat/Cool, and (optionally) Safety shutdown.
# Direction input and Active PWM pin are matched but not used.
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Module 4 Part 1 - Manual TEC Control GUI")

        # ------- in-memory data -------
        self.data = deque()          # (time_s, temperature_C, pwm, heat_cool)
        self.pwm_xs = []             # x values for the PWM chart
        self.pwm_heat_ys = []        # PWM values when heating (NaN when cooling)
        self.pwm_cool_ys = []        # PWM values when cooling (NaN when heating)

        # ------- open serial link -------
        self.link = SerialLink(SERIAL_PORT, BAUD_RATE)

        # ------- CSV -------
        self.csv_path = CSV_PATH
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_file = open(self.csv_path, "w", newline="")
        self.csv_file.write("time_s,temperature_C,pwm,heat_cool,safety_shutdown\n")
        self.csv_file.flush()

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

        # ------- command send debounce -------
        # While the user drags the slider, we do not want to send a command
        # every time the value changes. We wait SEND_DEBOUNCE_MS after the
        # last change, then send once.
        self.send_timer = QtCore.QTimer(self)
        self.send_timer.setSingleShot(True)
        self.send_timer.setInterval(SEND_DEBOUNCE_MS)
        self.send_timer.timeout.connect(self.send_command)

        # Send initial state (SET PWM 0 DIR HEAT) at startup.
        self.schedule_send()

    # ---------------- build the GUI ----------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- row 1: direction combo, PWM slider, PWM text box ---
        row1 = QtWidgets.QHBoxLayout()

        row1.addWidget(QtWidgets.QLabel("Direction:"))

        # Heat/cool switch (drop-down)
        self.dir_combo = QtWidgets.QComboBox()
        self.dir_combo.addItems(["HEAT", "COOL"])
        self.dir_combo.currentIndexChanged.connect(self.on_controls_changed)
        row1.addWidget(self.dir_combo)

        row1.addSpacing(20)
        row1.addWidget(QtWidgets.QLabel("PWM:"))

        # PWM slider 0-255
        self.pwm_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm_slider.setMinimum(0)
        self.pwm_slider.setMaximum(255)
        self.pwm_slider.setValue(0)
        self.pwm_slider.valueChanged.connect(self.on_slider_changed)
        row1.addWidget(self.pwm_slider, stretch=1)

        # PWM editable text box
        self.pwm_edit = QtWidgets.QLineEdit("0")
        self.pwm_edit.setFixedWidth(60)
        self.pwm_edit.editingFinished.connect(self.on_text_edited)
        row1.addWidget(self.pwm_edit)

        layout.addLayout(row1)

        # --- row 2: live value labels ---
        row2 = QtWidgets.QHBoxLayout()
        self.lbl_temp = QtWidgets.QLabel("Temperature: --- C")
        self.lbl_pwm = QtWidgets.QLabel("PWM: ---")
        self.lbl_dir = QtWidgets.QLabel("Direction: ---")
        self.lbl_time = QtWidgets.QLabel("Time: --- s")
        self.lbl_safety = QtWidgets.QLabel("Safety: ---")
        for lbl in (self.lbl_temp, self.lbl_pwm, self.lbl_dir, self.lbl_time,
                    self.lbl_safety):
            row2.addWidget(lbl)
        row2.addStretch(1)
        layout.addLayout(row2)

        # --- temperature plot (same as Part 4) ---
        self.temp_plot = pg.PlotWidget()
        self.temp_plot.setLabel("bottom", "Time (s)")
        self.temp_plot.setLabel("left", "Temperature (C)")
        self.temp_plot.setYRange(TEMP_Y_MIN, TEMP_Y_MAX)
        self.temp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen(width=2))
        layout.addWidget(self.temp_plot, stretch=1)

        # --- PWM plot: red for HEAT, blue for COOL ---
        self.pwm_plot = pg.PlotWidget()
        self.pwm_plot.setLabel("bottom", "Time (s)")
        self.pwm_plot.setLabel("left", "PWM")
        self.pwm_plot.setYRange(PWM_Y_MIN, PWM_Y_MAX)
        self.pwm_plot.showGrid(x=True, y=True, alpha=0.3)

        # connect="finite" tells pyqtgraph to break the line at NaN gaps,
        # so the red and blue segments do not join across a direction change.
        self.pwm_heat_curve = self.pwm_plot.plot(
            pen=pg.mkPen("r", width=2), connect="finite"
        )
        self.pwm_cool_curve = self.pwm_plot.plot(
            pen=pg.mkPen("b", width=2), connect="finite"
        )
        layout.addWidget(self.pwm_plot, stretch=1)

        self.resize(1000, 720)

    # ---------------- control callbacks ----------------
    def on_slider_changed(self, value: int):
        # Slider moved: mirror the new value into the text box,
        # then schedule a serial command.
        if self.pwm_edit.text() != str(value):
            self.pwm_edit.setText(str(value))
        self.schedule_send()

    def on_text_edited(self):
        # Text box edited: parse it, clamp to 0-255, mirror into the slider.
        text = self.pwm_edit.text().strip()
        try:
            value = int(text)
        except ValueError:
            # Not an integer: revert to the current slider value.
            value = self.pwm_slider.value()

        # Clamp typed PWM values to 0-255.
        value = max(0, min(255, value))

        self.pwm_edit.setText(str(value))
        if self.pwm_slider.value() != value:
            self.pwm_slider.setValue(value)   # triggers on_slider_changed
        else:
            self.schedule_send()

    def on_controls_changed(self):
        # Direction changed.
        self.schedule_send()

    # ---------------- serial command sending ----------------
    def schedule_send(self):
        # Restart the debounce timer. The command is sent when it fires.
        self.send_timer.start()

    def send_command(self):
        # Read the current PWM and direction from the GUI,
        # and write one command line to the Arduino.
        pwm = self.pwm_slider.value()
        direction = self.dir_combo.currentText()      # "HEAT" or "COOL"
        cmd = f"SET PWM {pwm} DIR {direction}"
        try:
            self.link.write_line(cmd)
            print(f"[sent] {cmd}")
        except Exception as e:
            print(f"[send error] {e}")

    # ---------------- one line received ----------------
    @QtCore.Slot(str)
    def on_line(self, line: str):
        parsed = parse_measurement(line)
        if parsed is None:
            # Pass through any safety message from the Arduino; ignore other
            # malformed lines.
            if "SAFETY" in line.upper():
                print(f"[arduino] {line}")
            return

        t = parsed["time_s"]
        T = parsed["temperature_C"]
        pwm = parsed["pwm"]
        hc = parsed["heat_cool"]
        safety = parsed["safety_shutdown"]

        # Terminal output: only the extracted fields
        print(
            f"Temperature (C): {T:.2f}, "
            f"Time (s): {t:.2f}, "
            f"PWM: {pwm}, "
            f"Heat/Cool: {hc}, "
            f"Safety shutdown: {safety}"
            + ("   <-- SAFETY SHUTDOWN ACTIVE" if safety else "")
        )

        # Store for the temperature plot and CSV
        self.data.append((t, T, pwm, hc))

        # Store for the PWM plot
        self.pwm_xs.append(t)
        if hc == 1:
            self.pwm_heat_ys.append(pwm)
            self.pwm_cool_ys.append(float("nan"))
        else:
            self.pwm_heat_ys.append(float("nan"))
            self.pwm_cool_ys.append(pwm)

        # Save one CSV row
        self.csv_file.write(f"{t:.2f},{T:.3f},{pwm},{hc},{safety}\n")
        self.csv_file.flush()

        # Update the live labels
        self.lbl_temp.setText(f"Temperature: {T:.2f} C")
        self.lbl_pwm.setText(f"PWM: {pwm}")
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

    # ---------------- plot updates ----------------
    def update_plots(self):
        if not self.data:
            return

        # Temperature curve
        xs = [row[0] for row in self.data]
        ys = [row[1] for row in self.data]
        self.temp_curve.setData(xs, ys)

        # PWM curves (red for HEAT, blue for COOL)
        self.pwm_heat_curve.setData(self.pwm_xs, self.pwm_heat_ys)
        self.pwm_cool_curve.setData(self.pwm_xs, self.pwm_cool_ys)

        # Roll both x-axes so the newest sample is at the right edge
        t_latest = xs[-1]
        x_min = max(0.0, t_latest - WINDOW_SECONDS)
        self.temp_plot.setXRange(x_min, t_latest, padding=0)
        self.pwm_plot.setXRange(x_min, t_latest, padding=0)

    # ---------------- clean shutdown ----------------
    def closeEvent(self, event):
        self.timer.stop()
        self.send_timer.stop()
        self.reader.stop()
        self.link.close()
        if self.csv_file is not None:
            self.csv_file.close()
            self.csv_file = None
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
