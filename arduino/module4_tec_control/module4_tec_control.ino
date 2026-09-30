// Phys 39 Module 4 - Part 1
// Arduino serial-command control sketch with software temperature limit
// (based on the Module 3 Part 6 sketch, tec_python_control.ino)
//
// A0: thermistor divider, 48.00 kOhm external resistor (averaged)
// Pin 9 / Pin 10: H-bridge control signals
// No trim pot, no pin 11 switch.
//
// Receives commands from the Python GUI:
//   SET PWM 120 DIR HEAT
//   SET PWM 45 DIR COOL
//
// Prints one measurement line about once per second:
//   Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Direction input: 1, Active PWM pin: 9, Heat/Cool: 1, Safety shutdown: 0
//
// Heat/Cool = 1 only for observed HEATING.
// Heat/Cool = 0 only for observed COOLING.
// Safety shutdown = 1 while the software temperature limit holds both
// H-bridge PWM outputs at zero.
// This is open-loop manual control. No feedback control.

const int THERMISTOR_PIN = A0;
const int HBRIDGE_PIN_1 = 9;
const int HBRIDGE_PIN_2 = 10;

// Module 2 measurement sequence: each temperature is calculated from the
// average of 1000 raw ADC readings. One reading is taken every 1000 us, so
// each average spans about 1 s and a new line prints about once a second.
const int ADC_SAMPLES = 1000;
const unsigned long SAMPLE_INTERVAL_US = 1000;

// Thermistor constants -- Module 2 values, except the external divider
// resistor: Module 4 uses 48.00 kOhm (Module 3 used 100 kOhm).
// adcToTemperatureC() assumes the Module 3 divider arrangement:
// external resistor from 5 V to A0, thermistor from A0 to GND.
const float SERIES_RESISTOR = 48000.0;
const float NOMINAL_RESISTANCE = 100000.0;
const float NOMINAL_TEMPERATURE_C = 25.0;
const float BETA_COEFFICIENT = 4540.0;
const float ADC_MAX = 1023.0;

// ------------------------------------------------------------------
// SOFTWARE TEMPERATURE LIMIT
// ------------------------------------------------------------------
// If the averaged temperature is above this limit, both H-bridge PWM
// outputs are set to zero. The hardware thermal switch in series with the
// TEC is the independent final protection.
//
// To verify: temporarily set this to 30.0, upload, warm the thermistor
// above 30 C, and confirm "Safety shutdown: 1" with PWM 0. Then set it
// back to 60.0 and upload again before showing the instructor.
const float TEMP_LIMIT_C = 60.0;

// ------------------------------------------------------------------
// EXPERIMENTALLY VERIFIED PART 3 MAPPING
// ------------------------------------------------------------------
// Set these two flags after your Part 3 experiment.
//
// HEAT_ACTIVE_PIN  = the Arduino pin that must output PWM when HEATING.
// COOL_ACTIVE_PIN  = the Arduino pin that must output PWM when COOLING.
//
// In the Part 3 sketch, pin 11 HIGH -> pin 9 PWM, pin 11 LOW -> pin 10 PWM.
// If your Part 3 test showed that pin 9 heated and pin 10 cooled, keep:
//   HEAT_ACTIVE_PIN = 9
//   COOL_ACTIVE_PIN = 10
// If your experiment showed the opposite, swap these two values.
//
// Module 4 check: the Module 3 notes record HEAT = PWM on pin 10, the
// opposite of the values below. Confirm with the low-PWM heat/cool test
// (the red PWM trace must mean the temperature rises) and swap if needed.
const int HEAT_ACTIVE_PIN = 9;
const int COOL_ACTIVE_PIN = 10;

// ------------------------------------------------------------------
// STATE
// ------------------------------------------------------------------
int currentPwm = 0;          // 0-255, starts at 0
bool currentIsHeat = true;   // true = HEAT, false = COOL, starts as HEAT
bool safetyShutdown = false; // true while the temperature limit holds PWM at 0

float temperatureC = NAN;    // most recent averaged temperature

unsigned long startTime;

// Running sum for the 1000-reading average.
unsigned long adcSum = 0;
int adcCount = 0;
unsigned long lastSampleUs = 0;

// Serial line buffer for incoming commands.
String commandBuffer = "";

// ------------------------------------------------------------------
// THERMISTOR MEASUREMENT (Module 2 sequence: average 1000 readings)
// ------------------------------------------------------------------
// Convert an averaged ADC value to temperature (Beta equation).
float adcToTemperatureC(float adc) {
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

// Take one raw ADC reading each time SAMPLE_INTERVAL_US has passed.
// After ADC_SAMPLES readings, update temperatureC from their average and
// return true. Spreading the readings across loop() instead of taking
// them in one blocking burst keeps serial commands responsive while the
// average builds up.
bool takeSample() {
  unsigned long nowUs = micros();
  if (nowUs - lastSampleUs < SAMPLE_INTERVAL_US) {
    return false;
  }
  lastSampleUs = nowUs;

  adcSum += analogRead(THERMISTOR_PIN);
  adcCount++;

  if (adcCount < ADC_SAMPLES) {
    return false;
  }

  temperatureC = adcToTemperatureC(adcSum / (float)ADC_SAMPLES);
  adcSum = 0;
  adcCount = 0;
  return true;
}

// ------------------------------------------------------------------
// SAFETY: apply PWM to the H-bridge
// ------------------------------------------------------------------
// Only one H-bridge input gets PWM at a time. The other is held LOW.
// This prevents both inputs being active at once.
void applyOutput() {
  // Software temperature limit: never drive the TEC during a safety shutdown.
  if (safetyShutdown) {
    zeroOutput();
    return;
  }

  int pwmPin;
  int lowPin;

  if (currentIsHeat) {
    pwmPin = HEAT_ACTIVE_PIN;
    lowPin = COOL_ACTIVE_PIN;
  } else {
    pwmPin = COOL_ACTIVE_PIN;
    lowPin = HEAT_ACTIVE_PIN;
  }

  // Make sure both pins are digital outputs.
  pinMode(HBRIDGE_PIN_1, OUTPUT);
  pinMode(HBRIDGE_PIN_2, OUTPUT);

  // Hold the inactive pin LOW, then write PWM on the active pin.
  digitalWrite(lowPin, LOW);
  analogWrite(pwmPin, currentPwm);
}

// ------------------------------------------------------------------
// SAFETY: zero the output
// ------------------------------------------------------------------
void zeroOutput() {
  currentPwm = 0;
  digitalWrite(HBRIDGE_PIN_1, LOW);
  digitalWrite(HBRIDGE_PIN_2, LOW);
  analogWrite(HBRIDGE_PIN_1, 0);
  analogWrite(HBRIDGE_PIN_2, 0);
}

// ------------------------------------------------------------------
// SAFETY: software temperature limit
// ------------------------------------------------------------------
// Called every loop with the most recent averaged temperature.
// Above TEMP_LIMIT_C (or with no valid reading), both H-bridge PWM
// outputs are set to zero. zeroOutput() also clears the commanded PWM,
// so the TEC does not restart by itself when the temperature falls
// again: a new command from the GUI is required.
void checkTemperatureLimit() {
  bool overLimit = isnan(temperatureC) || temperatureC > TEMP_LIMIT_C;

  if (overLimit) {
    zeroOutput();

    if (!safetyShutdown) {
      safetyShutdown = true;
      Serial.print("SAFETY SHUTDOWN ACTIVE: ");
      if (isnan(temperatureC)) {
        Serial.print("no valid temperature reading (check thermistor wiring)");
      } else {
        Serial.print("temperature ");
        Serial.print(temperatureC, 2);
        Serial.print(" C is above the ");
        Serial.print(TEMP_LIMIT_C, 2);
        Serial.print(" C limit");
      }
      Serial.println(". Both H-bridge PWM outputs set to 0.");
    }
  } else if (safetyShutdown) {
    safetyShutdown = false;
    Serial.print("SAFETY SHUTDOWN CLEARED: temperature ");
    Serial.print(temperatureC, 2);
    Serial.print(" C is back at or below the ");
    Serial.print(TEMP_LIMIT_C, 2);
    Serial.println(" C limit. PWM stays 0 until a new command is sent.");
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
void handleCommand(String line) {
  line.trim();
  line.toUpperCase();

  // Reject empty lines silently.
  if (line.length() == 0) {
    return;
  }

  // Tokenize by spaces.
  // Expected tokens:
  //   0: SET
  //   1: PWM
  //   2: <number>
  //   3: DIR
  //   4: HEAT | COOL
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

  // Validate keywords.
  if (tok0 != "SET") { zeroOutput(); return; }
  if (tok1 != "PWM") { zeroOutput(); return; }
  if (tok3 != "DIR") { zeroOutput(); return; }
  if (tok4 != "HEAT" && tok4 != "COOL") { zeroOutput(); return; }

  // Validate and parse PWM value.
  // The string must be all digits, else malformed.
  if (tok2.length() == 0) { zeroOutput(); return; }
  for (unsigned int i = 0; i < tok2.length(); i++) {
    if (!isDigit(tok2.charAt(i))) {
      zeroOutput();
      return;
    }
  }

  long pwmValue = tok2.toInt();

  // Clamp numeric PWM to 0-255.
  if (pwmValue < 0) pwmValue = 0;
  if (pwmValue > 255) pwmValue = 255;

  // Commit the new state.
  currentPwm = (int)pwmValue;
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
  zeroOutput();

  Serial.begin(9600);

  startTime = millis();
  commandBuffer.reserve(64);

  Serial.println("Module 4 serial-command TEC control");
  Serial.println("Commands: SET PWM <0-255> DIR HEAT | COOL");
  Serial.print("SAFETY: software temperature limit (C): ");
  Serial.println(TEMP_LIMIT_C, 2);

  // Build the first 1000-reading average before accepting commands,
  // so the safety check always has a measured temperature to test.
  while (!takeSample()) {
  }
  checkTemperatureLimit();
}

// ------------------------------------------------------------------
// LOOP
// ------------------------------------------------------------------
void loop() {
  // ---- read incoming serial commands ----
  // We read one character at a time, accumulate into commandBuffer,
  // and process on newline.
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
        // Line too long: drop it and zero output.
        commandBuffer = "";
        zeroOutput();
      }
    }
  }

  // ---- take one thermistor reading (true when a new average is ready) ----
  bool newTemperature = takeSample();

  // ---- safety: check the averaged temperature every loop ----
  checkTemperatureLimit();

  // ---- print one measurement line per averaged temperature (about 1 s) ----
  if (newTemperature) {
    float elapsed = (millis() - startTime) / 1000.0;

    int activePin = currentIsHeat ? HEAT_ACTIVE_PIN : COOL_ACTIVE_PIN;
    int heatCool = currentIsHeat ? 1 : 0;
    int dirInput = currentIsHeat ? 1 : 0;

    Serial.print("Temperature (C): ");
    if (isnan(temperatureC)) {
      Serial.print("nan");
    } else {
      Serial.print(temperatureC, 2);
    }

    Serial.print(", Time (s): ");
    Serial.print(elapsed, 2);

    Serial.print(", PWM: ");
    Serial.print(currentPwm);

    Serial.print(", Direction input: ");
    Serial.print(dirInput);

    Serial.print(", Active PWM pin: ");
    Serial.print(activePin);

    Serial.print(", Heat/Cool: ");
    Serial.print(heatCool);

    Serial.print(", Safety shutdown: ");
    Serial.println(safetyShutdown ? 1 : 0);
  }
}
