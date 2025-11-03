/*
  Smart Door Lock Controller
  
  This Arduino code manages a smart door lock system. It does the following:
  - Listens for serial commands (e.g., from a Python script) to UNLOCK or LOCK a relay.
  - Listens for a special command ("T=<seconds>") to configure a door-ajar timeout.
  - Monitors an HC-SR04 ultrasonic sensor to detect if the door is open or closed.
  - If the door is detected as open for longer than the configured timeout,
    it sends a "ALERT:DOOR_AJAR" message back over serial.
*/

// --- Pin Definitions ---
const int relayPin = 13;   // Digital pin connected to the relay's IN pin
const int trigPin = 9;     // Ultrasonic sensor TRIG pin (sends the sound pulse)
const int echoPin = 10;    // Ultrasonic sensor ECHO pin (receives the echo)

// --- Serial Communication ---
const unsigned long BAUD = 9600; // Serial baud rate (must match host computer)

// --- Door Sensor Logic & State ---
const int DOOR_OPEN_THRESHOLD_CM = 15;   // Distance (cm) to consider the door "open"
unsigned long doorOpenTimeoutMs = 20000; // Default: 20s. Time until an alert is sent.
unsigned long doorOpenStartTime = 0;     // Timestamp (from millis()) when the door was opened
boolean isDoorOpen = false;              // State variable: true if the door is currently open
boolean alertSent = false;               // State variable: true if the "ajar" alert has been sent

// --- Non-Blocking Timers ---
unsigned long sensorCheckInterval = 2000; // How often to check the sensor (ms)
unsigned long previousSensorCheck = 0;    // Stores the last time the sensor was checked

void setup() {
  // --- Initialize Relay Pin ---
  pinMode(relayPin, OUTPUT);
  digitalWrite(relayPin, HIGH); // Start in the LOCKED state (assumes an Active-LOW relay)

  // --- Initialize Sensor Pins ---
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  
  // --- Initialize Serial ---
  Serial.begin(BAUD);
}

void loop() {
  // Get the current time at the start of the loop.
  // This is the foundation for all non-blocking operations.
  unsigned long currentMillis = millis();
  
  // --- Task 1: Check for Serial Commands ---
  handleSerialCommands();

  // --- Task 2: Check Door Sensor (on an interval) ---
  // This is a non-blocking timer, often called the "Blink without Delay" pattern.
  // It checks if enough time has passed since the last sensor check.
  if (currentMillis - previousSensorCheck >= sensorCheckInterval) {
    previousSensorCheck = currentMillis; // Reset the timer for the next interval
    checkDoorSensor();                   // Call the function to read the sensor
  }

  // --- Task 3: Check for Door-Ajar Alert ---
  // This logic runs continuously.
  if (isDoorOpen && !alertSent && (currentMillis - doorOpenStartTime > doorOpenTimeoutMs)) {
    // Check if:
    // 1. The door is currently open (isDoorOpen)
    // 2. We haven't already sent an alert (!alertSent)
    // 3. The time since the door was opened is GREATER than our timeout
    
    Serial.println("ALERT:DOOR_AJAR"); // Send the alert
    alertSent = true;                   // Set the flag to prevent sending more alerts
  }
}

/**
 * @brief Checks for and processes incoming serial commands.
 */
void handleSerialCommands() {
  if (Serial.available() > 0) { // Check if any data is waiting in the serial buffer
    String cmd = Serial.readStringUntil('\n'); // Read the entire line
    cmd.trim(); // Remove any leading/trailing whitespace

    if (cmd.length() == 0) {
      return; // Ignore empty commands
    }

    // --- Process Recognized Commands ---
    
    // Check for Unlock commands
    if (cmd == "U" || cmd == "UNLOCK" || cmd == "ON") {
      digitalWrite(relayPin, LOW); // Turn relay ON (Unlock)
    
    // Check for Lock commands
    } else if (cmd == "L" || cmd == "LOCK" || cmd == "OFF") {
      digitalWrite(relayPin, HIGH); // Turn relay OFF (Lock)
    
    // Check for Timeout configuration command (e.g., "T=30")
    } else if (cmd.startsWith("T=")) {
      // Extract the number part of the string
      String timeoutValueStr = cmd.substring(2); // Get everything after "T="
      long timeoutSeconds = timeoutValueStr.toInt(); // Convert string to an integer
      
      if (timeoutSeconds > 0) {
        // Convert seconds to milliseconds and store it
        doorOpenTimeoutMs = timeoutSeconds * 1000L; // Use 'L' for long constant
        // Send an acknowledgment back to the host
        Serial.println("ACK:Timeout set to " + String(timeoutSeconds) + "s");
      }
    }
  }
}

/**
 * @brief Reads the HC-SR04 sensor and updates the door's state.
 */
void checkDoorSensor() {
  // --- Step 1: Trigger the Sensor ---
  // Send a 10-microsecond high pulse to the TRIG pin
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // --- Step 2: Read the Echo ---
  // `pulseIn` waits for the echo pin to go HIGH, measures the duration
  // it stays HIGH, and then returns the time in microseconds.
  // A timeout (50,000 us) is added to prevent the code
  // from blocking indefinitely if the sensor fails.
  long duration = pulseIn(echoPin, HIGH, 50000); 

  if (duration == 0) {
    return; // A duration of 0 means the pulseIn timed out. Ignore this read.
  }

  // --- Step 3: Calculate Distance ---
  // (Duration in us * Speed of Sound in cm/us) / 2
  // (Speed of Sound = 0.034 cm/us)
  int distance = duration * 0.034 / 2;

  // --- Step 4: Update Door State ---
  // We use a "state change" logic. We only act when the state
  // (open/closed) is different from the last time we checked.
  
  // Filter out bad sensor reads (e.g., > 200cm is likely noise)
  if (distance > DOOR_OPEN_THRESHOLD_CM && distance < 200) {
    // --- Door is now OPEN ---
    if (!isDoorOpen) {
      // This is a state change: The door was just opened!
      isDoorOpen = true;            // Update the state
      doorOpenStartTime = millis(); // Start the door-ajar timer
      alertSent = false;            // Reset the alert flag (ready to send a new alert)
    }
    // If door is already open, do nothing. The timer is already running.
    
  } else {
    // --- Door is now CLOSED ---
    if (isDoorOpen) {
      // This is a state change: The door was just closed!
      isDoorOpen = false;         // Update the state
      doorOpenStartTime = 0;      // Clear the timer
      alertSent = false;          // Reset the alert flag
      Serial.println("STATUS:DOOR_CLOSED"); // Optional: Notify host
    }
    // If door is already closed, do nothing.
  }
}