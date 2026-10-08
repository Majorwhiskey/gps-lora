// SPDX-License-Identifier: Apache-2.0
#include "net.h"

#include <Arduino.h>
#include <ESPmDNS.h>
#include <Update.h>
#include <WebServer.h>
#include <WiFi.h>
#include <atomic>

#include "config.h"
#include "lora_link.h"
#include "role.h"
#include "security.h"
#include "settings.h"
#include "snapshot.h"
#include "storage.h"
#include "timekeeping.h"

namespace net {
namespace {

enum class Phase : uint8_t { Off, WaitLora, Connecting, Up };

// wantOn is written only by the main loop (button, console); everything else
// here is driven by the network task, so WiFi and the server are never
// touched from two tasks.
std::atomic<bool> wantOn{false};
std::atomic<Phase> phase{Phase::Off};
std::atomic<bool> reboot{false};
std::atomic<uint32_t> lastActivityMs{0};

WebServer server(80);
char user[] = "admin";
char webPass[65];
char hostname[24];
char status[40] = "WiFi off";
portMUX_TYPE statusMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t phaseStartMs = 0;

bool uploadAuthed = false;
bool uploadOk = false;

void setStatus(const char *s) {
  portENTER_CRITICAL(&statusMux);
  strlcpy(status, s, sizeof(status));
  portEXIT_CRITICAL(&statusMux);
}

void touch() { lastActivityMs = millis(); }

bool auth() {
  touch();
  if (server.authenticate(user, webPass)) return true;
  server.requestAuthentication(BASIC_AUTH, "theoros");
  return false;
}

String fileArg() {
  String f = server.arg("f");
  return storage::validName(f.c_str()) ? f : String();
}

String statusJson() {
  snapshot::Gnss g = snapshot::gnss();
  char buf[512];
  snprintf(buf, sizeof(buf),
           "{\"fw\":\"%s\",\"role\":\"%s\",\"uptime_s\":%lu,\"time_source\":\"%s\","
           "\"fix\":%s,\"sats\":%lu,\"hdop\":%.1f,\"lat\":%.7f,\"lon\":%.7f,\"alt_m\":%.1f,"
           "\"sd\":\"%s\",\"file\":\"%s\",\"records\":%lu,"
           "\"lora_sent\":%lu,\"lora_frames\":%lu,\"lora_rejected\":%lu,"
           "\"encrypted\":%s,\"key\":\"%s\"}",
           FW_VERSION, role::name(),
           (unsigned long)(millis() / 1000), timekeeping::source(),
           snapshot::fixFresh(g) ? "true" : "false", (unsigned long)g.sats, g.hdop,
           g.lat, g.lon, g.altM, storage::stateName(), storage::fileName(),
           (unsigned long)storage::records(), (unsigned long)lora_link::sentCount(),
           (unsigned long)lora_link::frameCount(), (unsigned long)security::rejectedCount(),
           security::ready() ? "true" : "false", security::keyFingerprint());
  return buf;
}

void handleRoot() {
  if (!auth()) return;
  String h;
  h.reserve(4096);
  h += F("<!doctype html><html><head><meta charset=utf-8>"
         "<meta name=viewport content='width=device-width,initial-scale=1'>"
         "<title>Theoros</title><style>"
         "body{font-family:system-ui,sans-serif;margin:16px;max-width:720px}"
         "table{border-collapse:collapse;width:100%}"
         "td,th{padding:4px 8px;border-bottom:1px solid #ccc;text-align:left}"
         "pre{background:#eee;padding:8px;overflow-x:auto}"
         "</style></head><body><h1>Theoros ");
  h += role::name();
  h += F("</h1><pre>");
  h += statusJson();
  h += F("</pre><h2>Logs</h2><table><tr><th>File</th><th>Size</th><th></th></tr>");
  storage::list([&](const char *n, uint64_t size) {
    char row[320];
    bool open = strcmp(n, storage::fileName()) == 0;
    snprintf(row, sizeof(row),
             "<tr><td><a href='/download?f=%s'>%s</a></td><td>%llu</td><td>%s</td></tr>", n, n,
             (unsigned long long)size,
             open ? "logging" : "");
    h += row;
    if (!open) {
      h += F("<tr><td colspan=3><form method=post action='/delete?f=");
      h += n;
      h += F("' onsubmit=\"return confirm('Delete ");
      h += n;
      h += F("?')\"><button>Delete</button></form></td></tr>");
    }
  });
  h += F("</table><h2>Firmware update</h2>"
         "<form method=post action=/update enctype=multipart/form-data>"
         "<input type=file name=fw accept=.bin> <button>Upload</button></form>"
         "<p>Upload <code>tracker.ino.bin</code> or <code>receiver.ino.bin</code> "
         "from the build output. Uploading the other one switches this board's "
         "role. The board reboots, and rolls back if the new image fails to "
         "start.</p>"
         "</body></html>");
  server.send(200, "text/html", h);
}

void handleStatus() {
  if (!auth()) return;
  server.send(200, "application/json", statusJson());
}

void handleDownload() {
  if (!auth()) return;
  String f = fileArg();
  storage::Reader r;
  if (f.isEmpty() || !r.open(f.c_str())) {
    server.send(404, "text/plain", "No such log\n");
    return;
  }
  server.setContentLength(r.size());
  server.sendHeader("Content-Disposition", "attachment; filename=\"" + f + "\"");
  server.send(200, "text/csv", "");
  uint8_t buf[2048];
  uint64_t left = r.size();
  while (left) {
    int n = r.read(buf, size_t(min<uint64_t>(left, sizeof(buf))));
    if (n <= 0) break;  // Card ejected: client sees a short transfer
    if (server.client().write(buf, n) != size_t(n)) break;
    left -= n;
    touch();
  }
}

void handleDelete() {
  if (!auth()) return;
  String f = fileArg();
  if (f.isEmpty() || !storage::remove(f.c_str())) {
    server.send(409, "text/plain", "Cannot delete (open, missing or bad name)\n");
    return;
  }
  server.sendHeader("Location", "/");
  server.send(303);
}

void handleUpdateDone() {
  if (!uploadAuthed) {
    server.requestAuthentication(BASIC_AUTH, "theoros");
    return;
  }
  if (uploadOk) {
    server.send(200, "text/plain", "Update OK, rebooting\n");
    reboot = true;
  } else {
    server.send(500, "text/plain", String("Update failed: ") + Update.errorString() + "\n");
  }
}

void handleUpdateUpload() {
  HTTPUpload &up = server.upload();
  touch();
  if (up.status == UPLOAD_FILE_START) {
    uploadOk = false;
    uploadAuthed = server.authenticate(user, webPass);
    if (uploadAuthed) {
      Serial.printf("ota: receiving %s\n", up.filename.c_str());
      Update.begin(UPDATE_SIZE_UNKNOWN);
    }
    return;
  }
  if (!uploadAuthed) return;
  if (up.status == UPLOAD_FILE_WRITE) {
    if (Update.write(up.buf, up.currentSize) != up.currentSize) Update.printError(Serial);
  } else if (up.status == UPLOAD_FILE_END) {
    uploadOk = Update.end(true);
    if (uploadOk) Serial.printf("ota: %u bytes written\n", up.totalSize);
    else Update.printError(Serial);
  } else if (up.status == UPLOAD_FILE_ABORTED) {
    Update.abort();
    Serial.println("ota: upload aborted");
  }
}

void shutdown() {
  server.stop();
  MDNS.end();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  phase = Phase::Off;
  setStatus("WiFi off");
  Serial.println("wifi: off");
}

void bringUp() {
  String pw = settings::webPass();
  strlcpy(webPass, pw.c_str(), sizeof(webPass));
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(hostname);
  WiFi.begin(settings::wifiSsid().c_str(), settings::wifiPass().c_str());
  phase = Phase::Connecting;
  phaseStartMs = millis();
  setStatus("WiFi connecting");
  Serial.printf("wifi: connecting to %s\n", settings::wifiSsid().c_str());
}

void task(void *) {
  for (;;) {
    Phase p = phase;
    switch (p) {
      case Phase::Off:
        if (wantOn) {
          phase = Phase::WaitLora;
          setStatus("WiFi waiting");
        }
        break;

      case Phase::WaitLora:
        // Let a LoRa packet already on air finish; the loop starts no new one
        // while wantOn is set.
        if (!wantOn) phase = Phase::Off;
        else if (!lora_link::transmitting()) bringUp();
        break;

      case Phase::Connecting:
        if (!wantOn) {
          shutdown();
        } else if (WiFi.status() == WL_CONNECTED) {
          MDNS.begin(hostname);
          MDNS.addService("http", "tcp", 80);
          server.begin();
          timekeeping::startNtp();
          touch();
          phase = Phase::Up;
          char s[40];
          snprintf(s, sizeof(s), "WiFi %s", WiFi.localIP().toString().c_str());
          setStatus(s);
          Serial.printf("wifi: up, http://%s/ or http://%s.local/\n",
                        WiFi.localIP().toString().c_str(), hostname);
        } else if (millis() - phaseStartMs > WIFI_CONNECT_TIMEOUT_MS) {
          Serial.println("wifi: connect timed out");
          wantOn = false;
          shutdown();
        }
        break;

      case Phase::Up:
        server.handleClient();
        if (reboot) break;  // Keep serving until the main loop restarts us
        if (millis() - lastActivityMs > WIFI_IDLE_OFF_MS) {
          Serial.println("wifi: idle, switching off");
          wantOn = false;
        }
        if (!wantOn) shutdown();
        break;
    }
    vTaskDelay(pdMS_TO_TICKS(p == Phase::Up ? 2 : 50));
  }
}

}  // namespace

void begin() {
  snprintf(hostname, sizeof(hostname), "theoros-%04x", lora_link::nodeId());
  WiFi.persistent(false);  // Credentials live in our own NVS namespace
  WiFi.mode(WIFI_OFF);
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/download", HTTP_GET, handleDownload);
  server.on("/delete", HTTP_POST, handleDelete);
  server.on("/update", HTTP_POST, handleUpdateDone, handleUpdateUpload);
  // Registered before the task exists; the server itself only ever runs there.
  xTaskCreatePinnedToCore(task, "net", 8192, nullptr, 1, nullptr, 0);
}

void start() {
  if (settings::wifiSsid().isEmpty()) {
    Serial.println("wifi: no network set (console: wifi ssid <name>)");
    return;
  }
  if (settings::webPass().length() < 8) {
    Serial.println("wifi: set a web password first (console: web pass <8+ chars>)");
    return;
  }
  wantOn = true;
}

void stop() { wantOn = false; }

void toggle() { wantOn ? stop() : start(); }

bool radioOn() { return wantOn || phase != Phase::Off; }

bool connected() { return phase == Phase::Up; }

void statusText(char *out, size_t n) {
  portENTER_CRITICAL(&statusMux);
  strlcpy(out, status, n);
  portEXIT_CRITICAL(&statusMux);
}

bool rebootRequested() { return reboot; }

}  // namespace net
