/*
  Hybrid code for Smart Door Lock
  - Listens for Unlock/Lock commands ("U", "L")
  - Listens for a Timeout config command ("T=<seconds>")
  - Monitors an Ultrasonic sensor (HC-SR04)
  - If the door is open for > the configured timeout, sends "ALERT:DOOR_AJAR"
*/

// --- PINS ---
const int relayPin = 13;    // pin connected to relay IN
const int trigPin = 9;      // Ultrasonic sensor TRIG
const int echoPin = 10;     // Ultrasonic sensor ECHO

// --- BAUD ---
const unsigned long BAUD = 9600; // Using 9600 as configured in Python

// --- DOOR SENSOR LOGIC ---
const int DOOR_OPEN_THRESHOLD_CM = 15;   // If distance is > this, door is "open"
unsigned long doorOpenTimeoutMs = 20000; // Default 20s, will be set by Python
unsigned long doorOpenStartTime = 0;
boolean isDoorOpen = false;
boolean alertSent = false;

// --- TIMERS ---
unsigned long sensorCheckInterval = 2000; // Check sensor every 2 seconds
unsigned long previousSensorCheck = 0;

void setup() {
  pinMode(relayPin, OUTPUT);
  digitalWrite(relayPin, HIGH); // initially locked (relay off)
  
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  
  Serial.begin(BAUD);
}

void loop() {
  unsigned long currentMillis = millis();
  
  // 1. Check for commands from Python (non-blocking)
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      
      // --- Command Logic ---
      if (cmd == "U" || cmd == "UNLOCK" || cmd == "ON") {
        digitalWrite(relayPin, LOW); // Unlock
      } else if (cmd == "L" || cmd == "LOCK" || cmd == "OFF") {
        digitalWrite(relayPin, HIGH); // Lock
      
      // --- NEW: Timeout Config Command ---
      } else if (cmd.startsWith("T=")) {
        // Expects "T=20" (for 20 seconds)
        String timeoutValueStr = cmd.substring(2); // Get "20"
        long timeoutSeconds = timeoutValueStr.toInt();
        if (timeoutSeconds > 0) {
          doorOpenTimeoutMs = timeoutSeconds * 1000L; // Convert to ms
          Serial.println("ACK:Timeout set to " + String(timeoutSeconds) + "s");
        }
      }
    }
  }

  // 2. Check the door sensor (non-blocking, every 2 seconds)
  if (currentMillis - previousSensorCheck >= sensorCheckInterval) {
    previousSensorCheck = currentMillis;
    checkDoorSensor();
  }

  // 3. Check if door has been open too long
  if (isDoorOpen && !alertSent && (currentMillis - doorOpenStartTime > doorOpenTimeoutMs)) {
    Serial.println("ALERT:DOOR_AJAR");
    alertSent = true; // Only send alert once
  }
}

void checkDoorSensor() {
  // Standard HC-SR04 pulse logic
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Read the echo (with a timeout to prevent blocking)
  long duration = pulseIn(echoPin, HIGH, 50000); // 50ms timeout
  if (duration == 0) return; // Timeout, bad read

  // Calculate the distance
  int distance = duration * 0.034 / 2;

  // --- Main Sensor Logic ---
  if (distance > DOOR_OPEN_THRESHOLD_CM && distance < 200) { // (and < 200 to filter bad reads)
    // Door is OPEN
    if (!isDoorOpen) {
      // Door was just opened!
      isDoorOpen = true;
      doorOpenStartTime = millis();
      alertSent = false;
    }
  } else {
    // Door is CLOSED
    if (isDoorOpen) {
      // Door was just closed!
      isDoorOpen = false;
      doorOpenStartTime = 0;
      alertSent = false;
      Serial.println("STATUS:DOOR_CLOSED"); // Optional: tell python it's closed
    }
  }
}