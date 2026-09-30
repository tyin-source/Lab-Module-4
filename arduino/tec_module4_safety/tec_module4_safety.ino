// Phys 39 Module 4 - Open-loop TEC calibration with a software temperature limit
//
// Based on the Module 3 Part 6 serial-command sketch (tec_python_control.ino).
//
// A0: thermistor divider (average of 1000 ADC readings per temperature)
// Pin 9 / Pin 10: H-bridge logic inputs
//
// Receives newline-terminated commands from the Python GUI at 115200 baud:
//   SET PWM 120 DIR HEAT
//   SET PWM 45 DIR COOL
//
// Prints one measurement line about once per second:
//   Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Safety: OK
//
// PWM is the value actually applied to the H-bridge (0 while the safety
// shutdown is active). Heat/Cool = 1 for heating, 0 for cooling.
// Safety is OK, or SHUTDOWN while the software temperature limit is active.
//
// This is open-loop manual control. No feedback control.
//
// SOFTWARE SAFETY INTERLOCK
// If the averaged temperature exceeds SOFTWARE_TEMP_LIMIT_C (or the thermistor
// reading is invalid), both H-bridge inputs are set to zero and the requested
// PWM is cleared. The sketch keeps printing so the GUI shows what happened.
// The shutdown clears once the temperature falls SAFETY_RESET_MARGIN_C below the
// limit, but the TEC stays off until Python sends a new command.
// The hardware thermal switch in series with the TEC (opens near 70 C) remains
// the independent final protection; this code does not replace it.

const int THERMISTOR_PIN = A0;
const int HBRIDGE_PIN_1 = 9;
const int HBRIDGE_PIN_2 = 10;

const int ADC_SAMPLES = 1000;                    // Module 2 averaging
const unsigned long PRINT_INTERVAL_MS = 1000;    // about one line per second
const long SERIAL_BAUD = 115200;

// ------------------------------------------------------------------
// SOFTWARE TEMPERATURE LIMIT
// ------------------------------------------------------------------
// Normal operation: 60.0 C.
// For the in-class verification ONLY, temporarily set this to 30.0, warm the
// block above 30 C at low heating PWM, confirm "Safety: SHUTDOWN" and PWM 0,
// then restore 60.0 and re-upload before collecting calibration data.
const float SOFTWARE_TEMP_LIMIT_C = 60.0;
const float SAFETY_RESET_MARGIN_C = 2.0;

// Thermistor constants -- Module 2 values.
const float SERIES_RESISTOR = 100000.0;
const float NOMINAL_RESISTANCE = 100000.0;
const float NOMINAL_TEMPERATURE_C = 25.0;
const float BETA_COEFFICIENT = 4540.0;
const float ADC_MAX = 1023.0;

// ------------------------------------------------------------------
// EXPERIMENTALLY VERIFIED DIRECTION MAPPING
// ------------------------------------------------------------------
// From the Module 3 Part 2 direction test (docs/module_notes in Module 3):
//   HEAT = PWM on pin 10 with pin 9 LOW
//   COOL = PWM on pin 9 with pin 10 LOW
// Re-confirm at low PWM from the observed temperature response. If heating and
// cooling are reversed, swap these two values.
const int HEAT_ACTIVE_PIN = 10;
const int COOL_ACTIVE_PIN = 9;

// ------------------------------------------------------------------
// STATE
// ------------------------------------------------------------------
int currentPwm = 0;          // applied PWM, 0-255, starts at 0
bool currentIsHeat = true;   // true = HEAT, false = COOL
bool safetyShutdown = false; // true while the software limit is active

unsigned long startTime;
unsigned long lastPrint = 0;

String commandBuffer = "";

// ------------------------------------------------------------------
// THERMISTOR MEASUREMENT
// ------------------------------------------------------------------
float readTemperatureC() {
  unsigned long sum = 0;

  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(THERMISTOR_PIN);
  }

  float adc = sum / (float)ADC_SAMPLES;

  if (adc <= 0 || adc >= ADC_MAX) {
    return NAN;
  }

  float resistance = SERIES_RESISTOR * adc / (ADC_MAX - adc);

  float steinhart = resistance / NOMINAL_RESISTANCE;
  steinhart = log(steinhart);
  steinhart /= BETA_COEFFICIENT;
  steinhart += 1.0 / (NOMINAL_TEMPERATURE_C + 273.15);
  steinhart = 1.0 / steinhart;
  steinhart -= 273.15;

  return steinhart;
}

// ------------------------------------------------------------------
// H-BRIDGE OUTPUT
// ------------------------------------------------------------------
// Only one H-bridge input gets PWM at a time. The other is held LOW.
void applyOutput() {
  int pwmPin;
  int lowPin;

  if (currentIsHeat) {
    pwmPin = HEAT_ACTIVE_PIN;
    lowPin = COOL_ACTIVE_PIN;
  } else {
    pwmPin = COOL_ACTIVE_PIN;
    lowPin = HEAT_ACTIVE_PIN;
  }

  analogWrite(lowPin, 0);
  analogWrite(pwmPin, currentPwm);
}

// Set both H-bridge PWM outputs to zero.
void zeroOutput() {
  currentPwm = 0;
  analogWrite(HBRIDGE_PIN_1, 0);
  analogWrite(HBRIDGE_PIN_2, 0);
}

// ------------------------------------------------------------------
// SAFETY CHECK: called every loop with the averaged temperature
// ------------------------------------------------------------------
void checkSafety(float tempC) {
  bool overLimit = isnan(tempC) || tempC > SOFTWARE_TEMP_LIMIT_C;

  if (overLimit) {
    if (!safetyShutdown) {
      Serial.print("SAFETY SHUTDOWN: ");
      if (isnan(tempC)) {
        Serial.print("invalid thermistor reading");
      } else {
        Serial.print("temperature ");
        Serial.print(tempC, 2);
        Serial.print(" C exceeds limit ");
        Serial.print(SOFTWARE_TEMP_LIMIT_C, 1);
        Serial.print(" C");
      }
      Serial.println("; TEC PWM set to 0");
    }
    safetyShutdown = true;
    zeroOutput();
  } else if (safetyShutdown &&
             tempC < SOFTWARE_TEMP_LIMIT_C - SAFETY_RESET_MARGIN_C) {
    safetyShutdown = false;
    Serial.println("SAFETY CLEARED: temperature below limit; PWM remains 0 until a new command");
  }
}

// ------------------------------------------------------------------
// PARSER: handle one command line
// ------------------------------------------------------------------
// Accepted format (case-insensitive on keywords):
//   SET PWM <0-255> DIR HEAT
//   SET PWM <0-255> DIR COOL
//
// Any malformed or unknown command returns PWM to 0.
// While the safety shutdown is active, the direction is accepted but PWM stays 0.
void handleCommand(String line) {
  line.trim();
  line.toUpperCase();

  if (line.length() == 0) {
    return;
  }

  int t0 = line.indexOf(' ');
  if (t0 < 0) { zeroOutput(); return; }
  String tok0 = line.substring(0, t0);

  int t1 = line.indexOf(' ', t0 + 1);
  if (t1 < 0) { zeroOutput(); return; }
  String tok1 = line.substring(t0 + 1, t1);

  int t2 = line.indexOf(' ', t1 + 1);
  if (t2 < 0) { zeroOutput(); return; }
  String tok2 = line.substring(t1 + 1, t2);

  int t3 = line.indexOf(' ', t2 + 1);
  if (t3 < 0) { zeroOutput(); return; }
  String tok3 = line.substring(t2 + 1, t3);

  String tok4 = line.substring(t3 + 1);
  tok4.trim();

  if (tok0 != "SET") { zeroOutput(); return; }
  if (tok1 != "PWM") { zeroOutput(); return; }
  if (tok3 != "DIR") { zeroOutput(); return; }
  if (tok4 != "HEAT" && tok4 != "COOL") { zeroOutput(); return; }

  if (tok2.length() == 0 || tok2.length() > 5) { zeroOutput(); return; }
  for (unsigned int i = 0; i < tok2.length(); i++) {
    if (!isDigit(tok2.charAt(i))) {
      zeroOutput();
      return;
    }
  }

  long pwmValue = tok2.toInt();
  if (pwmValue < 0) pwmValue = 0;
  if (pwmValue > 255) pwmValue = 255;

  currentIsHeat = (tok4 == "HEAT");

  if (safetyShutdown) {
    Serial.println("SAFETY SHUTDOWN ACTIVE: command ignored, PWM held at 0");
    zeroOutput();
    return;
  }

  currentPwm = (int)pwmValue;
  applyOutput();
}

// ------------------------------------------------------------------
// SETUP
// ------------------------------------------------------------------
void setup() {
  pinMode(HBRIDGE_PIN_1, OUTPUT);
  pinMode(HBRIDGE_PIN_2, OUTPUT);

  // Safety: PWM starts at zero.
  zeroOutput();

  Serial.begin(SERIAL_BAUD);

  startTime = millis();
  lastPrint = 0;
  commandBuffer.reserve(64);

  Serial.println("Module 4 TEC control with software temperature limit");
  Serial.print("Software temperature limit (C): ");
  Serial.println(SOFTWARE_TEMP_LIMIT_C, 1);
  Serial.println("Commands: SET PWM <0-255> DIR HEAT | COOL");
}

// ------------------------------------------------------------------
// LOOP
// ------------------------------------------------------------------
void loop() {
  // ---- read incoming serial commands ----
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      if (commandBuffer.length() > 0) {
        handleCommand(commandBuffer);
        commandBuffer = "";
      }
    } else {
      if (commandBuffer.length() < 64) {
        commandBuffer += c;
      } else {
        commandBuffer = "";
        zeroOutput();
      }
    }
  }

  // ---- measure and check the software limit every loop ----
  float tempC = readTemperatureC();
  checkSafety(tempC);

  // ---- print the measurement line about once per second ----
  unsigned long now = millis();

  if (now - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = now;

    float elapsed = (now - startTime) / 1000.0;

    Serial.print("Temperature (C): ");
    if (isnan(tempC)) {
      Serial.print("nan");
    } else {
      Serial.print(tempC, 2);
    }

    Serial.print(", Time (s): ");
    Serial.print(elapsed, 2);

    Serial.print(", PWM: ");
    Serial.print(currentPwm);

    Serial.print(", Heat/Cool: ");
    Serial.print(currentIsHeat ? 1 : 0);

    Serial.print(", Safety: ");
    Serial.println(safetyShutdown ? "SHUTDOWN" : "OK");
  }
}
