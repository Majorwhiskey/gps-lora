// SPDX-License-Identifier: Apache-2.0
#include "lora_link.h"

#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <atomic>

#include "board.h"
#include "config.h"

namespace lora_link {
namespace {

SPIClass loraSpi(HSPI);
// Reset pin passed as NC: RadioLib's SX127x reset drives RESET high, which the
// RFM95W datasheet never describes. We reset the module ourselves below.
SX1276 radio = new Module(PIN_LORA_NSS, PIN_LORA_DIO0, RADIOLIB_NC, PIN_LORA_DIO1,
                          loraSpi, SPISettings(LORA_SPI_HZ, MSBFIRST, SPI_MODE0));

volatile bool dio0Flag = false;
bool present = false;
bool receiving = false;
std::atomic<bool> busy{false};
uint16_t node = 0;
uint32_t sent = 0, frames = 0, crcBad = 0;
uint32_t airtimeMs = 0;
uint32_t nextAllowedMs = 0;
uint32_t txStartMs = 0;

Frame last;
bool lastFresh = false;

void IRAM_ATTR onDio0() { dio0Flag = true; }

// RFM §7.2: pull low >= 100 us, release, ready 5 ms later. Open drain so the
// pin can never drive the line high.
void resetModule() {
  pinMode(PIN_LORA_RESET, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_LORA_RESET, LOW);
  delay(1);
  pinMode(PIN_LORA_RESET, INPUT);
  delay(10);
}

void serviceTx() {
  if (!busy) return;
  if (dio0Flag) {
    dio0Flag = false;
    radio.finishTransmit();  // Clears IRQ flags, radio to standby
    sent++;
    busy = false;
  } else if (millis() - txStartMs > 2 * airtimeMs + 1000) {
    // DIO0 never fired: wiring or module fault. Don't wedge the radio forever.
    Serial.println("lora: tx timeout, DIO0 missing?");
    radio.finishTransmit();
    busy = false;
  }
}

void serviceRx() {
  if (!dio0Flag) return;
  dio0Flag = false;
  size_t len = radio.getPacketLength();
  if (len > sizeof(last.data)) len = sizeof(last.data);
  int16_t rc = radio.readData(last.data, len);
  if (rc == RADIOLIB_ERR_NONE) {
    last.len = len;
    last.rssi = radio.getRSSI();
    last.snr = radio.getSNR();
    lastFresh = true;
    frames++;
  } else {
    crcBad++;
  }
  radio.startReceive();
}

}  // namespace

bool begin() {
  node = uint16_t(ESP.getEfuseMac() >> 32);  // Last two MAC bytes
  resetModule();
  loraSpi.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_NSS);

  int16_t rc = radio.begin(LORA_FREQ_MHZ, LORA_BW_KHZ, LORA_SF, LORA_CR,
                           LORA_SYNC_WORD, LORA_POWER_DBM);
  if (rc != RADIOLIB_ERR_NONE) {
    Serial.printf("lora: init failed (%d)\n", rc);
    present = false;
    return false;
  }
  radio.setCRC(true);
  radio.setDio0Action(onDio0, RISING);  // TX done or RX done
  present = true;
  Serial.printf("lora: %.1f MHz SF%u BW%.0f %d dBm, node %04x\n", LORA_FREQ_MHZ,
                LORA_SF, LORA_BW_KHZ, LORA_POWER_DBM, node);
  return true;
}

void service() {
  if (!present) return;
  if (receiving) serviceRx();
  else serviceTx();
}

bool canSend() {
  return present && !receiving && !busy && int32_t(millis() - nextAllowedMs) >= 0;
}

bool send(const uint8_t *data, size_t len) {
  if (!canSend()) return false;

  airtimeMs = uint32_t(radio.getTimeOnAir(len) / 1000);
  dio0Flag = false;
  int16_t rc = radio.startTransmit(data, len);
  if (rc != RADIOLIB_ERR_NONE) {
    Serial.printf("lora: tx failed (%d)\n", rc);
    return false;
  }
  busy = true;
  txStartMs = millis();
  // Silence after each packet keeps airtime at or below LORA_MAX_DUTY over
  // any window, not just on average.
  nextAllowedMs = millis() + uint32_t(airtimeMs / LORA_MAX_DUTY);
  return true;
}

bool transmitting() { return busy; }

bool startReceive() {
  if (!present) return false;
  dio0Flag = false;
  int16_t rc = radio.startReceive();
  if (rc != RADIOLIB_ERR_NONE) {
    Serial.printf("lora: rx start failed (%d)\n", rc);
    return false;
  }
  receiving = true;
  return true;
}

bool takeFrame(Frame &out) {
  if (!lastFresh) return false;
  out = last;
  lastFresh = false;
  return true;
}

bool ready() { return present; }
uint16_t nodeId() { return node; }
uint32_t sentCount() { return sent; }
uint32_t frameCount() { return frames; }
uint32_t crcErrors() { return crcBad; }
uint32_t lastAirtimeMs() { return airtimeMs; }

}  // namespace lora_link
