const int relayPin = 13;    // pin connected to relay IN 
const unsigned long BAUD = 115200;

void setup() {
  pinMode(relayPin, OUTPUT);
  digitalWrite(relayPin, HIGH); // initially locked (relay off)
  Serial.begin(BAUD);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n'); // read one line
    cmd.trim();
    if (cmd.length() > 0) {
      if (cmd == "U" || cmd == "UNLOCK" || cmd == "ON") {
        digitalWrite(relayPin, LOW);
        Serial.println("ACK:UNLOCK");
      } else if (cmd == "L" || cmd == "LOCK" || cmd == "OFF") {
        digitalWrite(relayPin, HIGH);
        Serial.println("ACK:LOCK");
      } else {
        Serial.print("UNKNOWN:");
        Serial.println(cmd);
      }
    }
  }
}
