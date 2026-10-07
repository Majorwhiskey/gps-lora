// SPDX-License-Identifier: Apache-2.0
#include "gnss.h"

#include <Arduino.h>

#include "board.h"
#include "config.h"

namespace gnss {
namespace {

HardwareSerial &port = Serial1;
TinyGPSPlus parser;

volatile uint32_t ppsEdges = 0;
volatile uint32_t ppsMicros = 0;
volatile uint32_t ppsMillis = 0;

uint32_t lastSentenceMs = 0;
uint32_t lastPassed = 0;
uint8_t retries = 0;

void IRAM_ATTR onPps() {
  ppsMicros = micros();
  ppsMillis = millis();
  ppsEdges = ppsEdges + 1;
}

void ubxSend(uint8_t cls, uint8_t id, const uint8_t *payload, uint16_t len) {
  uint8_t hdr[6] = {0xB5, 0x62, cls, id, uint8_t(len), uint8_t(len >> 8)};
  uint8_t a = 0, b = 0;
  for (int i = 2; i < 6; i++) { a += hdr[i]; b += a; }
  for (uint16_t i = 0; i < len; i++) { a += payload[i]; b += a; }
  port.write(hdr, sizeof(hdr));
  port.write(payload, len);
  port.write(a);
  port.write(b);
  port.flush();
}

// UBX-CFG-VALSET builder. M10 firmware has no UBX-CFG-PRT/MSG; every setting
// goes through configuration keys (u-blox M10 SPG 5.10 interface description).
class ValSet {
 public:
  ValSet() {
    buf_[0] = 0;     // version
    buf_[1] = 0x01;  // layers: RAM only, so a power cycle restores defaults
    buf_[2] = buf_[3] = 0;
    len_ = 4;
  }
  void u1(uint32_t key, uint8_t v) { putKey(key); buf_[len_++] = v; }
  void u4(uint32_t key, uint32_t v) {
    putKey(key);
    for (int i = 0; i < 4; i++) buf_[len_++] = uint8_t(v >> (8 * i));
  }
  void send() { ubxSend(0x06, 0x8A, buf_, len_); }

 private:
  void putKey(uint32_t k) {
    for (int i = 0; i < 4; i++) buf_[len_++] = uint8_t(k >> (8 * i));
  }
  uint8_t buf_[96];
  uint16_t len_;
};

constexpr uint32_t CFG_UART1_BAUDRATE   = 0x40520001;
constexpr uint32_t CFG_MSGOUT_GGA_UART1 = 0x209100bb;
constexpr uint32_t CFG_MSGOUT_RMC_UART1 = 0x209100ac;
constexpr uint32_t CFG_MSGOUT_GLL_UART1 = 0x209100ca;
constexpr uint32_t CFG_MSGOUT_GSA_UART1 = 0x209100c0;
constexpr uint32_t CFG_MSGOUT_GSV_UART1 = 0x209100c5;
constexpr uint32_t CFG_MSGOUT_VTG_UART1 = 0x209100b1;

void sendMessageConfig(bool withBaud) {
  ValSet v;
  v.u1(CFG_MSGOUT_GGA_UART1, 1);  // GGA: altitude, sats, HDOP
  v.u1(CFG_MSGOUT_RMC_UART1, 1);  // RMC: date, speed, course
  v.u1(CFG_MSGOUT_GLL_UART1, 0);
  v.u1(CFG_MSGOUT_GSA_UART1, 0);
  v.u1(CFG_MSGOUT_GSV_UART1, 0);
  v.u1(CFG_MSGOUT_VTG_UART1, 0);
  if (withBaud) v.u4(CFG_UART1_BAUDRATE, GNSS_BAUD);
  v.send();
}

// The receiver may be at 9600 (fresh power-up) or already at GNSS_BAUD (the
// ESP32 reset but the receiver kept its RAM config). Talk to it at both rates.
// The bytes it sees at the wrong rate are a few dozen framing errors, well
// under the 100/s that makes it disable RX (SAM-IM 3.2.1).
void configure() {
  port.updateBaudRate(GNSS_BAUD_DEFAULT);
  sendMessageConfig(true);
  delay(100);  // Receiver applies the new rate (SAM-DS, UART)
  port.updateBaudRate(GNSS_BAUD);
  sendMessageConfig(false);
  lastSentenceMs = millis();
}

}  // namespace

void begin() {
  // GPIO15 stays an input with no pull: a low level on TIMEPULSE at receiver
  // start-up selects safe boot (SAM-IM 3.2.3.3).
  pinMode(PIN_GNSS_PPS, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_GNSS_PPS), onPps, RISING);

  // RESET_N is released (high-Z) unless we are recovering the receiver.
  pinMode(PIN_GNSS_RESET_N, INPUT);

  port.setRxBufferSize(1024);
  port.begin(GNSS_BAUD_DEFAULT, SERIAL_8N1, PIN_GNSS_RX, PIN_GNSS_TX);
  delay(50);
  configure();
}

void poll() {
  while (port.available()) parser.encode(port.read());

  uint32_t now = millis();
  if (parser.passedChecksum() != lastPassed) {
    lastPassed = parser.passedChecksum();
    lastSentenceMs = now;
    retries = 0;
    return;
  }
  if (now - lastSentenceMs < GNSS_SILENT_MS) return;

  if (retries < GNSS_RETRIES_BEFORE_HW_RESET) {
    retries++;
    Serial.printf("gnss: no NMEA, reconfiguring (%u)\n", retries);
    configure();
  } else {
    Serial.println("gnss: still silent, RESET_N pulse");
    retries = 0;
    hardReset();
  }
}

TinyGPSPlus &fix() { return parser; }

bool linkAlive() { return millis() - lastSentenceMs < GNSS_SILENT_MS; }

bool ppsRecent() { return ppsEdges && millis() - ppsMillis < 1500; }

uint32_t ppsCount() { return ppsEdges; }

uint32_t lastPpsMicros() { return ppsMicros; }

void softReset() {
  // navBbrMask 0x0000 = hot start, resetMode 0x01 = controlled software reset.
  // RAM config is lost, so reconfigure once the receiver is back.
  const uint8_t payload[4] = {0x00, 0x00, 0x01, 0x00};
  ubxSend(0x06, 0x04, payload, sizeof(payload));
  delay(1000);
  configure();
}

void hardReset() {
  // Open drain: pull low for >= 1 ms (SAM-DS Table 13), then release.
  pinMode(PIN_GNSS_RESET_N, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_GNSS_RESET_N, LOW);
  delay(10);
  pinMode(PIN_GNSS_RESET_N, INPUT);
  delay(1000);
  configure();
}

}  // namespace gnss
