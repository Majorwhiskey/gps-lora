// SPDX-License-Identifier: Apache-2.0
#include "timekeeping.h"

#include <Arduino.h>
#include <SdFat.h>
#include <esp_sntp.h>
#include <sys/time.h>
#include <time.h>

namespace timekeeping {
namespace {

// Anything earlier means the clock was never set (it boots at 1970).
constexpr time_t MIN_VALID = 1767225600;  // 2026-01-01

const char *src = "none";

// Days since 1970-01-01 for a proleptic Gregorian date (H. Hinnant).
int32_t daysFromCivil(int y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = unsigned(y - era * 400);
  const unsigned doy = (153 * (m > 2 ? m - 3 : m + 9) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + int32_t(doe) - 719468;
}

void sdDateTime(uint16_t *date, uint16_t *time_, uint8_t *ms10) {
  time_t now = time(nullptr);
  struct tm t;
  gmtime_r(&now, &t);
  *date = FS_DATE(t.tm_year + 1900, t.tm_mon + 1, t.tm_mday);
  *time_ = FS_TIME(t.tm_hour, t.tm_min, t.tm_sec);
  *ms10 = 0;
}

void onNtpSync(struct timeval *) {
  src = "ntp";
  Serial.println("time: set from NTP");
}

}  // namespace

void begin() {
  setenv("TZ", "UTC0", 1);
  tzset();
  FsDateTime::setCallback(sdDateTime);
}

uint32_t gnssUnixTime(TinyGPSPlus &g) {
  if (!g.date.isValid() || !g.time.isValid() || g.date.year() < 2026) return 0;
  return uint32_t(daysFromCivil(g.date.year(), g.date.month(), g.date.day())) * 86400u +
         g.time.hour() * 3600u + g.time.minute() * 60u + g.time.second();
}

void updateFromGnss(TinyGPSPlus &g) {
  // Only trust the date once the receiver has a fix: before that, the
  // receiver may report a default date.
  if (!g.location.isValid()) return;
  uint32_t t = gnssUnixTime(g);
  if (!t) return;
  // NMEA arrives a few hundred ms after the epoch, so only correct drift
  // larger than that. Good enough for file timestamps; PPS would give more.
  time_t now = time(nullptr);
  if (now >= MIN_VALID && labs(long(now) - long(t)) <= 1) return;
  struct timeval tv = {time_t(t), 0};
  settimeofday(&tv, nullptr);
  if (strcmp(src, "gnss") != 0) Serial.println("time: set from GNSS");
  src = "gnss";
}

void startNtp() {
  if (esp_sntp_enabled()) return;
  sntp_set_time_sync_notification_cb(onNtpSync);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}

bool valid() { return time(nullptr) >= MIN_VALID; }

const char *source() { return src; }

}  // namespace timekeeping
