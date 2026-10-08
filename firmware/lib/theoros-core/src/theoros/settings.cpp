// SPDX-License-Identifier: Apache-2.0
#include "settings.h"

#include <Preferences.h>

namespace settings {
namespace {

Preferences prefs;
String ssid, pass, web;

}  // namespace

void begin() {
  prefs.begin("theoros", false);
  ssid = prefs.getString("ssid", "");
  pass = prefs.getString("pass", "");
  web = prefs.getString("webpass", "");
}

String wifiSsid() { return ssid; }
String wifiPass() { return pass; }
String webPass() { return web; }

void setWifiSsid(const String &v) { ssid = v; prefs.putString("ssid", v); }
void setWifiPass(const String &v) { pass = v; prefs.putString("pass", v); }
void setWebPass(const String &v) { web = v; prefs.putString("webpass", v); }

}  // namespace settings
