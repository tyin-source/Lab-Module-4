// Phys 39 Module 4 - Open-loop TEC calibration with software safety limit
//
// Started from the Module 3 Part 6 serial-command sketch.
//
// A0: thermistor divider (averaged)
// Pin 9 / Pin 10: H-bridge control signals
//
// Receives newline-terminated commands from the Python GUI:
//   SET PWM 120 DIR HEAT
//   SET PWM 45 DIR COOL
//
// Prints one measurement line per PRINT_INTERVAL_MS:
//   Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1, Safety: OK
//
// PWM is the value actually applied to the H-bridge (0 while the safety
// shutdown is active). Heat/Cool = 1 for HEAT, 0 for COOL.
// Safety is OK or SHUTDOWN.
//
// This is open-loop manual control. No feedback control.
// The hardware thermal switch (~70 C) in series with the TEC remains the
// independent final protection; this software limit does not replace it.

const int THERMISTOR_PIN = A0;
const int HBRIDGE_PIN_1 = 9;
const int HBRIDGE_PIN_2 = 10;

// Module 2 sequence: average 100-1000 raw readings before each temperature.
const int ADC_SAMPLES = 200;
const unsigned long PRINT_INTERVAL_MS = 200;

// Thermistor constants -- Module 2 values.
const float SERIES_RESISTOR = 100000.0;
const float NOMINAL_RESISTANCE = 100000.0;
const float NOMINAL_TEMPERATURE_C = 25.0;
const float BETA_COEFFICIENT = 4540.0;
const float ADC_MAX = 1023.0;

// ------------------------------------------------------------------
// SOFTWARE TEMPERATURE LIMIT
// ------------------------------------------------------------------
// If the averaged temperature exceeds this value (or the reading is
// invalid), both H-bridge outputs are forced to zero.
//
// Verification (TEC power OFF): temporarily set this just below the
// measured room temperature, upload, confirm "Safety: SHUTDOWN" and
// PWM 0 on both pins, then restore 60.0 and re-upload.
const float SOFTWARE_TEMP_LIMIT_C = 60.0;

// ------------------------------------------------------------------
// EXPERIMENTALLY VERIFIED DIRECTION MAPPING
// ------------------------------------------------------------------
// Module 3 notes record HEAT = pin 10 PWM / pin 9 LOW and
// COOL = pin 9 PWM / pin 10 LOW. Confirm with a low-PWM test in class:
// if HEAT cools the block, swap these two values.
const int HEAT_ACTIVE_PIN = 10;
const int COOL_ACTIVE_PIN = 9;

// ------------------------------------------------------------------
// STATE
// ------------------------------------------------------------------
int requestedPwm = 0;         // 0-255, last value commanded by Python
bool currentIsHeat = true;    // true = HEAT, false = COOL
bool safetyShutdown = false;  // latched when the limit is exceeded
float lastTemperatureC = NAN;

unsigned long startTime;
unsigned long lastPrint = 0;

String commandBuffer = "";

// ------------------------------------------------------------------
// THERMISTOR MEASUREMENT
// ------------------------------------------------------------------
float readTemperatureC() {
  long sum = 0;

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
void zeroOutput() {
  analogWrite(HBRIDGE_PIN_1, 0);
  analogWrite(HBRIDGE_PIN_2, 0);
  digitalWrite(HBRIDGE_PIN_1, LOW);
  digitalWrite(HBRIDGE_PIN_2, LOW);
}

// Only one H-bridge input gets PWM at a time; the other is held LOW.
void applyOutput() {
  if (safetyShutdown) {
    zeroOutput();
    return;
  }

  int pwmPin = currentIsHeat ? HEAT_ACTIVE_PIN : COOL_ACTIVE_PIN;
  int lowPin = currentIsHeat ? COOL_ACTIVE_PIN : HEAT_ACTIVE_PIN;

  analogWrite(lowPin, 0);
  digitalWrite(lowPin, LOW);
  analogWrite(pwmPin, requestedPwm);
}

int appliedPwm() {
  return safetyShutdown ? 0 : requestedPwm;
}

// ------------------------------------------------------------------
// SAFETY CHECK (called every loop)
// ------------------------------------------------------------------
// The shutdown latches: it stays active until the temperature is back
// below the limit AND Python sends a new SET command.
void checkSafety(float tempC) {
  if (isnan(tempC) || tempC > SOFTWARE_TEMP_LIMIT_C) {
    if (!safetyShutdown) {
      Serial.print("SAFETY SHUTDOWN: temperature ");
      if (isnan(tempC)) {
        Serial.print("invalid");
      } else {
        Serial.print(tempC, 2);
      }
      Serial.print(" C exceeds software limit ");
      Serial.print(SOFTWARE_TEMP_LIMIT_C, 1);
      Serial.println(" C. Both PWM outputs set to 0.");
    }
    safetyShutdown = true;
    requestedPwm = 0;
    zeroOutput();
  }
}

// ------------------------------------------------------------------
// PARSER
// ------------------------------------------------------------------
// Accepted format (case-insensitive):
//   SET PWM <0-255> DIR HEAT
//   SET PWM <0-255> DIR COOL
// Any malformed command sets PWM to 0.
void rejectCommand() {
  requestedPwm = 0;
  zeroOutput();
}

void handleCommand(String line) {
  line.trim();
  line.toUpperCase();

  if (line.length() == 0) {
    return;
  }

  int t0 = line.indexOf(' ');
  if (t0 < 0) { rejectCommand(); return; }
  int t1 = line.indexOf(' ', t0 + 1);
  if (t1 < 0) { rejectCommand(); return; }
  int t2 = line.indexOf(' ', t1 + 1);
  if (t2 < 0) { rejectCommand(); return; }
  int t3 = line.indexOf(' ', t2 + 1);
  if (t3 < 0) { rejectCommand(); return; }

  String tok0 = line.substring(0, t0);
  String tok1 = line.substring(t0 + 1, t1);
  String tok2 = line.substring(t1 + 1, t2);
  String tok3 = line.substring(t2 + 1, t3);
  String tok4 = line.substring(t3 + 1);
  tok4.trim();

  if (tok0 != "SET" || tok1 != "PWM" || tok3 != "DIR") { rejectCommand(); return; }
  if (tok4 != "HEAT" && tok4 != "COOL") { rejectCommand(); return; }

  if (tok2.length() == 0) { rejectCommand(); return; }
  for (unsigned int i = 0; i < tok2.length(); i++) {
    if (!isDigit(tok2.charAt(i))) { rejectCommand(); return; }
  }

  long pwmValue = tok2.toInt();
  if (pwmValue > 255) pwmValue = 255;

  // A new command may clear a latched shutdown only if the last averaged
  // temperature is valid and back below the limit.
  if (safetyShutdown) {
    if (!isnan(lastTemperatureC) && lastTemperatureC <= SOFTWARE_TEMP_LIMIT_C) {
      safetyShutdown = false;
      Serial.println("SAFETY RESET: temperature below limit, accepting commands.");
    } else {
      Serial.println("SAFETY SHUTDOWN active: command ignored.");
      return;
    }
  }

  requestedPwm = (int)pwmValue;
  currentIsHeat = (tok4 == "HEAT");
  applyOutput();
}

// ------------------------------------------------------------------
// SETUP
// ------------------------------------------------------------------
void setup() {
  pinMode(HBRIDGE_PIN_1, OUTPUT);
  pinMode(HBRIDGE_PIN_2, OUTPUT);

  // Safety: PWM starts at zero.
  requestedPwm = 0;
  zeroOutput();

  Serial.begin(115200);

  startTime = millis();
  commandBuffer.reserve(64);

  Serial.println("Module 4 open-loop TEC calibration");
  Serial.println("Commands: SET PWM <0-255> DIR HEAT | COOL");
  Serial.print("Software temperature limit (C): ");
  Serial.println(SOFTWARE_TEMP_LIMIT_C, 1);
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
    } else if (commandBuffer.length() < 64) {
      commandBuffer += c;
    } else {
      // Line too long: drop it and zero output.
      commandBuffer = "";
      rejectCommand();
    }
  }

  // ---- measure and check the software limit every loop ----
  lastTemperatureC = readTemperatureC();
  checkSafety(lastTemperatureC);

  // ---- print the measurement line on a timer ----
  unsigned long now = millis();

  if (now - lastPrint >= PRINT_INTERVAL_MS) {
    lastPrint = now;

    Serial.print("Temperature (C): ");
    if (isnan(lastTemperatureC)) {
      Serial.print("nan");
    } else {
      Serial.print(lastTemperatureC, 2);
    }

    Serial.print(", Time (s): ");
    Serial.print((now - startTime) / 1000.0, 2);

    Serial.print(", PWM: ");
    Serial.print(appliedPwm());

    Serial.print(", Heat/Cool: ");
    Serial.print(currentIsHeat ? 1 : 0);

    Serial.print(", Safety: ");
    Serial.println(safetyShutdown ? "SHUTDOWN" : "OK");
  }
}
