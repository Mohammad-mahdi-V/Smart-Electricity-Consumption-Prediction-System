#include "EmonLib.h"
#include <WiFi.h>
#include <HTTPClient.h>

EnergyMonitor emon1;

const char* ssid     = "";
const char* password = "";

const char* serverUrl = "http://62.60.198.228:8000/api/data";

const int ctPin = 34; 
double ctCalibration = 28.3; 


const int voltagePin = 35; 
double vCalibration = 83.3;     
double phaseCalibration = 1.7;  
unsigned long lastPostTime = 0;
const unsigned long postInterval = 10000; 

void connectWiFi() {
  Serial.print("connecting to WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("connected IP address: ");
  Serial.println(WiFi.localIP());
}

void sendReading(double Vrms, double Irms, double realPower, double apparentPower, double powerFactor) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected skipping POST");
    return;
  }

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  String payload = "{";
  payload += "\"current_A\":" + String(Irms, 3) + ",";
  payload += "\"voltage_V\":" + String(Vrms, 1) + ",";
  payload += "\"power_W\":" + String(realPower, 1) + ",";
  payload += "\"apparent_power_VA\":" + String(apparentPower, 1) + ",";
  payload += "\"power_factor\":" + String(powerFactor, 3);
  payload += "}";

  int httpCode = http.POST(payload);

  if (httpCode > 0) {
    Serial.print("POST response code: ");
    Serial.println(httpCode);
  } else {
    Serial.print("POST failed, error: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
}

void setup() {
  Serial.begin(115200);

  emon1.voltage(voltagePin, vCalibration, phaseCalibration);
  emon1.current(ctPin, ctCalibration);

  Serial.println("energy monitor starting...");
  connectWiFi();
  delay(1000);
}

void loop() {
  emon1.calcVI(20, 2000);

  double Vrms          = emon1.Vrms;
  double Irms           = emon1.Irms;
  double realPower      = emon1.realPower;
  double apparentPower  = emon1.apparentPower;
  double powerFactor    = emon1.powerFactor;

  Serial.print("V: ");
  Serial.print(Vrms, 1);
  Serial.print("  I: ");
  Serial.print(Irms, 3);
  Serial.print("  Real P: ");
  Serial.print(realPower, 1);
  Serial.print(" W  Apparent P: ");
  Serial.print(apparentPower, 1);
  Serial.print(" VA  PF: ");
  Serial.println(powerFactor, 3);

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (millis() - lastPostTime >= postInterval) {
    sendReading(Vrms, Irms, realPower, apparentPower, powerFactor);
    lastPostTime = millis();
  }
}
