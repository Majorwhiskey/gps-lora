// SPDX-License-Identifier: Apache-2.0
#include "storage.h"

#include <SPI.h>
#include <SdFat.h>
#include <freertos/semphr.h>

#include "board.h"
#include "config.h"

namespace storage {
namespace {

SPIClass sdSpi(FSPI);
SdFs sd;
FsFile file;
SemaphoreHandle_t lock;

const char *filePrefix = "LOG";
const char *fileHeader = "";

volatile State st = State::NoCard;
char name[16] = "";
uint32_t recordCount = 0;
uint32_t lastAttemptMs = 0;
uint32_t mountGen = 0;  // Bumped on every unmount; invalidates open Readers

// The loop waits at most this long; a stalled download costs one record,
// not a watchdog reset.
constexpr TickType_t LOOP_WAIT = pdMS_TO_TICKS(500);

struct Guard {
  explicit Guard(TickType_t wait = portMAX_DELAY) : ok(xSemaphoreTake(lock, wait)) {}
  ~Guard() { if (ok) xSemaphoreGive(lock); }
  bool ok;
};

bool mount() {
  lastAttemptMs = millis();
  // SD on the IO_MUX pins, dedicated bus: no other device shares it.
  if (!sd.begin(SdSpiConfig(PIN_SD_CS, DEDICATED_SPI, SD_SPI_HZ, &sdSpi))) {
    Serial.printf("sd: mount failed (error 0x%02x)\n", sd.sdErrorCode());
    st = State::NoCard;
    return false;
  }
  Serial.printf("sd: mounted, %s\n", sd.fatType() == FAT_TYPE_EXFAT ? "exFAT" : "FAT");
  st = State::Ready;
  return true;
}

void unmount() {
  if (file.isOpen()) {
    file.sync();
    file.close();
  }
  sd.end();
  mountGen++;
}

// Number from <prefix>nnnn.CSV, or -1.
int fileNumber(const char *n, const char *prefix) {
  size_t pl = strlen(prefix);
  if (strncmp(n, prefix, pl) != 0 || strlen(n) != pl + 8) return -1;
  for (size_t i = pl; i < pl + 4; i++)
    if (!isdigit((unsigned char)n[i])) return -1;
  if (strcmp(n + pl + 4, ".CSV") != 0) return -1;
  return atoi(n + pl);
}

// One directory pass instead of an exists() probe per number, which could
// take seconds on a card with many logs.
bool openNewFile() {
  int highest = 0;
  FsFile root, entry;
  char n[32];
  if (root.open("/")) {
    while (entry.openNext(&root, O_RDONLY)) {
      entry.getName(n, sizeof(n));
      highest = max(highest, fileNumber(n, filePrefix));
      entry.close();
    }
    root.close();
  }
  if (highest >= 9999) {
    Serial.println("sd: file numbers exhausted");
    st = State::Error;
    lastAttemptMs = millis();
    return false;
  }
  snprintf(name, sizeof(name), "%s%04d.CSV", filePrefix, highest + 1);

  size_t hl = strlen(fileHeader);
  if (!file.open(name, O_WRONLY | O_CREAT | O_EXCL) || file.write(fileHeader, hl) != hl ||
      !file.sync()) {
    Serial.printf("sd: cannot create %s\n", name);
    file.close();
    st = State::Error;
    lastAttemptMs = millis();
    return false;
  }
  recordCount = 0;
  st = State::Logging;
  Serial.printf("sd: logging to %s\n", name);
  return true;
}

}  // namespace

void begin(const char *prefix, const char *header) {
  lock = xSemaphoreCreateMutex();
  filePrefix = prefix;
  fileHeader = header;
  sdSpi.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  Guard g;
  mount();
}

void service() {
  if ((st != State::NoCard && st != State::Error) || millis() - lastAttemptMs < SD_RETRY_MS)
    return;
  Guard g(LOOP_WAIT);
  if (!g.ok) return;
  unmount();
  mount();
}

bool append(const char *line) {
  Guard g(LOOP_WAIT);
  if (!g.ok) {
    Serial.println("sd: busy, record dropped");
    return false;
  }
  if (st == State::Ready && !openNewFile()) return false;
  if (st != State::Logging) return false;

  size_t n = strlen(line);
  // Sync after every record: no battery, so every power-off is unclean
  // (PCB_DESIGN, power-loss handling).
  if (file.write(line, n) != n || !file.sync()) {
    Serial.println("sd: write failed");
    file.close();
    st = State::Error;
    lastAttemptMs = millis();
    return false;
  }
  recordCount++;
  return true;
}

void eject() {
  Guard g;
  if (st == State::Ejected) return;
  unmount();
  st = State::Ejected;
  Serial.println("sd: ejected, safe to remove");
}

void resume() {
  Guard g;
  if (st == State::Ejected) mount();
}

void powerFail() {
  // No waiting here: power is going away. If the web task holds the lock,
  // the last record was already synced anyway.
  Guard g(0);
  if (!g.ok || st != State::Logging) return;
  file.sync();
  file.close();
  st = State::Error;  // Remount if power returns
  lastAttemptMs = millis();
}

State state() { return st; }

const char *stateName() {
  switch (st) {
    case State::NoCard:  return "no card";
    case State::Ready:   return "ready";
    case State::Logging: return "logging";
    case State::Ejected: return "ejected";
    case State::Error:   return "error";
  }
  return "?";
}

const char *fileName() { return st == State::Logging ? name : ""; }

uint32_t records() { return recordCount; }

bool validName(const char *n) {
  return fileNumber(n, "LOG") >= 0 || fileNumber(n, "RX") >= 0;
}

void list(const std::function<void(const char *, uint64_t)> &fn) {
  Guard g;
  if (st != State::Ready && st != State::Logging) return;
  FsFile root, entry;
  char n[32];
  if (!root.open("/")) return;
  while (entry.openNext(&root, O_RDONLY)) {
    entry.getName(n, sizeof(n));
    if (!entry.isDir() && validName(n)) fn(n, entry.fileSize());
    entry.close();
  }
  root.close();
}

bool remove(const char *n) {
  if (!validName(n)) return false;
  Guard g;
  if (st != State::Ready && st != State::Logging) return false;
  if (st == State::Logging && strcmp(n, name) == 0) return false;
  return sd.remove(n);
}

bool Reader::open(const char *n) {
  close();
  if (!validName(n)) return false;
  Guard g;
  if (st != State::Ready && st != State::Logging) return false;
  auto *f = new FsFile;
  if (!f->open(n, O_RDONLY)) {
    delete f;
    return false;
  }
  file_ = f;
  gen_ = mountGen;
  size_ = f->fileSize();  // Snapshot: a file being logged keeps growing
  return true;
}

int Reader::read(uint8_t *buf, size_t n) {
  if (!file_) return -1;
  Guard g;
  if (gen_ != mountGen) return -1;  // Card ejected or remounted meanwhile
  return static_cast<FsFile *>(file_)->read(buf, n);
}

void Reader::close() {
  if (!file_) return;
  {
    Guard g;
    if (gen_ == mountGen) static_cast<FsFile *>(file_)->close();
  }
  delete static_cast<FsFile *>(file_);
  file_ = nullptr;
}

}  // namespace storage
