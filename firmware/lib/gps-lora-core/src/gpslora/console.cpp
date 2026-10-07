// SPDX-License-Identifier: Apache-2.0
#include "console.h"

#include <Arduino.h>

#include "config.h"
#include "gnss.h"
#include "lora_link.h"
#include "net.h"
#include "role.h"
#include "security.h"
#include "settings.h"
#include "snapshot.h"
#include "storage.h"
#include "timekeeping.h"

namespace console {
namespace {

char line[160];
size_t len = 0;

const char HELP[] =
    "commands:\n"
    "  status                 show state\n"
    "  wifi ssid <name>       set network (rest of line, spaces allowed)\n"
    "  wifi pass <password>   set network password\n"
    "  web pass <password>    set web page password, 8+ chars (user: admin)\n"
    "  wifi on | off          service mode; pauses LoRa TX while on\n"
    "  key set <32 hex>       install key from tools/gps_lora.py, reboots\n"
    "  key clear              remove key, reboots\n"
    "  gnss reset             UBX-CFG-RST hot start\n"
    "  eject | resume         SD card\n"
    "  reboot\n";

// Returns the text after "cmd " if line starts with it, else nullptr.
const char *arg(const char *cmd) {
  size_t n = strlen(cmd);
  if (strncmp(line, cmd, n) != 0 || line[n] != ' ') return nullptr;
  return line + n + 1;
}

void status() {
  snapshot::Gnss g = snapshot::gnss();
  char wifi[40];
  net::statusText(wifi, sizeof(wifi));
  Serial.printf("fw %s %s, up %lus, time from %s\n", role::name(), FW_VERSION,
                (unsigned long)(millis() / 1000), timekeeping::source());
  Serial.printf("gnss: link %s, %s, sats %lu, hdop %.1f, pps %lu\n",
                gnss::linkAlive() ? "ok" : "silent",
                snapshot::fixFresh(g) ? "fix" : "no fix", (unsigned long)g.sats, g.hdop,
                (unsigned long)gnss::ppsCount());
  if (snapshot::fixFresh(g))
    Serial.printf("      %.7f, %.7f, %.1f m\n", g.lat, g.lon, g.altM);
  Serial.printf("sd: %s %s, %lu records\n", storage::stateName(), storage::fileName(),
                (unsigned long)storage::records());
  Serial.printf("lora: %s, node %04x, sent %lu, frames %lu, crc errors %lu, rejected %lu\n",
                lora_link::ready() ? "ok" : "absent", lora_link::nodeId(),
                (unsigned long)lora_link::sentCount(), (unsigned long)lora_link::frameCount(),
                (unsigned long)lora_link::crcErrors(),
                (unsigned long)security::rejectedCount());
  Serial.printf("security: self-test %s, %s key %s%s\n",
                security::selfTestPassed() ? "passed" : "FAILED",
                role::receiver() ? "master" : "device", security::keyFingerprint(),
                security::ready() ? "" : role::receiver() ? " (cannot decrypt)"
                                                          : " (LoRa off, log UNENCRYPTED)");
  Serial.printf("%s, network \"%s\", web password %s\n", wifi,
                settings::wifiSsid().c_str(),
                settings::webPass().length() >= 8 ? "set" : "NOT set");
}

void run() {
  const char *a;
  if (!strcmp(line, "help") || !strcmp(line, "?")) {
    Serial.print(HELP);
  } else if (!strcmp(line, "status")) {
    status();
  } else if ((a = arg("wifi ssid"))) {
    settings::setWifiSsid(a);
    Serial.printf("ok, network \"%s\"\n", a);
  } else if ((a = arg("wifi pass"))) {
    settings::setWifiPass(a);
    Serial.println("ok");  // Never echo secrets
  } else if ((a = arg("web pass"))) {
    if (strlen(a) < 8) {
      Serial.println("too short, use 8+ characters");
    } else {
      settings::setWebPass(a);
      Serial.println("ok, takes effect next time WiFi comes on");
    }
  } else if (!strcmp(line, "wifi on")) {
    net::start();
  } else if (!strcmp(line, "wifi off")) {
    net::stop();
  } else if ((a = arg("key set"))) {
    // The key was typed, so it is in this terminal's scrollback; it is never
    // printed by the board.
    if (!security::setKey(a)) {
      Serial.println("need exactly 32 hex digits (from tools/gps_lora.py provision)");
      return;
    }
    Serial.printf("ok, key %s installed, rebooting\n", security::keyFingerprint());
    storage::eject();
    delay(100);
    ESP.restart();
  } else if (!strcmp(line, "key clear")) {
    security::clearKey();
    Serial.println("key removed, rebooting");
    storage::eject();
    delay(100);
    ESP.restart();
  } else if (!strcmp(line, "gnss reset")) {
    gnss::softReset();
  } else if (!strcmp(line, "eject")) {
    storage::eject();
  } else if (!strcmp(line, "resume")) {
    storage::resume();
  } else if (!strcmp(line, "reboot")) {
    storage::eject();
    delay(100);
    ESP.restart();
  } else if (len) {
    Serial.println("unknown command, try help");
  }
}

}  // namespace

void service() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') {
      line[len] = 0;
      while (len && line[len - 1] == ' ') line[--len] = 0;
      run();
      len = 0;
    } else if (c == 8 || c == 127) {
      if (len) len--;
    } else if (len < sizeof(line) - 1 && isprint((unsigned char)c)) {
      line[len++] = c;
    }
  }
}

}  // namespace console
