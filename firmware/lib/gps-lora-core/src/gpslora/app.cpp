// SPDX-License-Identifier: Apache-2.0
#include "app.h"

#include <Arduino.h>
#include <esp_ota_ops.h>
#include <esp_system.h>

#include "board.h"
#include "config.h"
#include "console.h"
#include "display.h"
#include "gnss.h"
#include "lora_link.h"
#include "net.h"
#include "security.h"
#include "settings.h"
#include "snapshot.h"
#include "storage.h"
#include "timekeeping.h"

// The core would mark a freshly OTA'd image good as soon as it boots. Defer
// that until it has run OTA_CONFIRM_MS (see serviceOtaConfirm).
extern "C" bool verifyRollbackLater() { return true; }

namespace app {
namespace {

EpochHandler epochHandler = nullptr;
uint32_t lastEpochTime = UINT32_MAX;
uint32_t lastDisplayMs = 0;
uint32_t ledOffMs = 0;
uint32_t buttonDownMs = 0;
bool buttonHandled = false;
bool vbusWasPresent = true;
bool otaPending = false;

bool fixUsable(TinyGPSPlus &g) {
  return g.location.isValid() && g.location.age() < LOG_MAX_FIX_AGE &&
         g.date.isValid() && g.time.isValid() && g.hdop.isValid() &&
         g.hdop.hdop() <= LOG_MAX_HDOP;
}

void serviceLed() {
  uint32_t now = millis();
  switch (storage::state()) {
    case storage::State::Ejected:
      digitalWrite(PIN_LED, HIGH);
      return;
    case storage::State::NoCard:
    case storage::State::Error: {
      // 5 blinks of 60 ms on / 60 ms off, then 1.2 s dark: 1.8 s period
      uint32_t t = now % 1800;
      digitalWrite(PIN_LED, t < 600 && (t / 60) % 2 == 0);
      return;
    }
    case storage::State::Ready:
      if (now % 2000 < 30) ledBlip(30);
      break;
    case storage::State::Logging:
      break;  // Blip on each record
  }
  if (int32_t(now - ledOffMs) >= 0) digitalWrite(PIN_LED, LOW);
}

// Once per receiver epoch, triggered by GGA. u-blox sends RMC before GGA in
// each epoch, so every field used here comes from the same epoch.
void serviceGnssEpoch() {
  TinyGPSPlus &g = gnss::fix();
  if (!g.satellites.isUpdated()) return;  // Only GGA carries satellites
  g.satellites.value();                   // Reading clears the flag
  uint32_t t = g.time.value();            // hhmmsscc
  if (t == lastEpochTime) return;
  lastEpochTime = t;

  bool usable = fixUsable(g);
  snapshot::Gnss s;
  s.epochMs = millis();
  s.fix = usable;
  s.timeValid = g.time.isValid();
  s.hour = g.time.hour();
  s.minute = g.time.minute();
  s.second = g.time.second();
  s.unixTime = timekeeping::gnssUnixTime(g);
  s.sats = g.satellites.value();
  s.hdop = g.hdop.hdop();
  s.lat = g.location.lat();
  s.lon = g.location.lng();
  s.altM = g.altitude.meters();
  s.speedKmh = g.speed.kmph();
  s.courseDeg = g.course.deg();
  snapshot::publishGnss(s);

  timekeeping::updateFromGnss(g);
  if (epochHandler) epochHandler(g, usable);
}

void serviceButton() {
  bool down = digitalRead(PIN_EJECT_BTN) == LOW;
  uint32_t now = millis();
  if (!down) {
    if (buttonDownMs && !buttonHandled && now - buttonDownMs > 50) {
      // Short press
      if (storage::state() == storage::State::Ejected) storage::resume();
      else net::toggle();
    }
    buttonDownMs = 0;
    buttonHandled = false;
    return;
  }
  if (!buttonDownMs) buttonDownMs = now;
  if (!buttonHandled && now - buttonDownMs >= EJECT_HOLD_MS) {
    if (storage::state() != storage::State::Ejected) storage::eject();
    buttonHandled = true;  // Long press never also counts as a short one
  }
}

// VBUS divider on GPIO5. Without the (DNP) holdup capacitor the rail collapses
// within microseconds, so this mainly matters once holdup is fitted.
void serviceVbus() {
  bool present = digitalRead(PIN_VBUS_SENSE) == HIGH;
  if (!present && vbusWasPresent) {
    storage::powerFail();
    Serial.println("vbus: lost, file closed");
  }
  vbusWasPresent = present;
}

void serviceOtaConfirm() {
  if (!otaPending || millis() < OTA_CONFIRM_MS) return;
  esp_ota_mark_app_valid_cancel_rollback();
  otaPending = false;
  Serial.println("ota: new firmware confirmed");
}

void serviceReboot() {
  if (!net::rebootRequested()) return;
  storage::eject();
  delay(500);  // Let the HTTP response reach the browser
  ESP.restart();
}

}  // namespace

void begin(role::Role r, const char *logPrefix, HeaderFn logHeader, EpochHandler onEpoch) {
  role::set(r);
  epochHandler = onEpoch;

  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);
  pinMode(PIN_EJECT_BTN, INPUT_PULLUP);
  pinMode(PIN_VBUS_SENSE, INPUT);

  Serial.begin(115200);  // USB Serial/JTAG; baud rate is ignored
  delay(500);            // Give a host terminal a moment to attach
  Serial.printf("\ngps-lora %s %s, reset reason %d\n", role::name(), FW_VERSION,
                esp_reset_reason());

  esp_ota_img_states_t ota;
  if (esp_ota_get_state_partition(esp_ota_get_running_partition(), &ota) == ESP_OK &&
      ota == ESP_OTA_IMG_PENDING_VERIFY) {
    otaPending = true;
    Serial.println("ota: new firmware, confirming after 60 s");
  }

  settings::begin();
  timekeeping::begin();
  display::begin();
  display::message("gps-lora " FW_VERSION, role::name());
  gnss::begin();
  lora_link::begin();  // Also derives the node ID
  security::begin(lora_link::nodeId());
  storage::begin(logPrefix, logHeader());
  net::begin();

  // Reset if loop() stalls for 5 s (CONFIG_ESP_TASK_WDT_TIMEOUT_S). Before
  // OTA_CONFIRM_MS this also rolls a bad update back.
  enableLoopWDT();
  digitalWrite(PIN_LED, LOW);
  Serial.println("type help for commands");
}

void service() {
  gnss::poll();
  storage::service();
  lora_link::service();
  console::service();

  serviceButton();
  serviceVbus();
  serviceGnssEpoch();
  serviceLed();
  serviceOtaConfirm();
  serviceReboot();

  if (millis() - lastDisplayMs >= DISPLAY_PERIOD_MS) {
    lastDisplayMs = millis();
    display::render();
  }
}

void ledBlip(uint32_t ms) {
  digitalWrite(PIN_LED, HIGH);
  ledOffMs = millis() + ms;
}

}  // namespace app
