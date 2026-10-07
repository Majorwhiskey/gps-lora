// SPDX-License-Identifier: Apache-2.0
// microSD on SPI2. One CSV per session, synced after every record.
// Thread safe: the main loop writes, the web task lists and reads.
#pragma once

#include <Arduino.h>
#include <functional>

namespace storage {

enum class State : uint8_t {
  NoCard,   // Mount failed; retried every SD_RETRY_MS
  Ready,    // Mounted, no file open yet (waiting for the first record)
  Logging,  // File open
  Ejected,  // User ejected; safe to remove. Waits for a button press
  Error,    // Write failed; remounted after SD_RETRY_MS
};

// prefix: "LOG" or "RX". Files are <prefix>nnnn.CSV; header is the CSV header.
void begin(const char *prefix, const char *header);
void service();                       // Call every loop: retries mounts
bool append(const char *line);        // Writes one CSV line and syncs
void eject();                         // Sync, close, unmount
void resume();                        // Leave Ejected and remount
void powerFail();                     // VBUS lost: close the file now

State state();
const char *stateName();
const char *fileName();               // Current log file, "" if none
uint32_t records();

// For the web task. Only names matching (LOG|RX)nnnn.CSV are accepted.
bool validName(const char *name);
void list(const std::function<void(const char *name, uint64_t size)> &fn);
bool remove(const char *name);        // Refuses the file being written

// Streams a file in chunks; the SD lock is held only per chunk, so logging
// continues during a long download. Returns false if the card went away.
class Reader {
 public:
  bool open(const char *name);
  int read(uint8_t *buf, size_t n);   // -1 on error, 0 at end
  uint64_t size() const { return size_; }
  void close();
  ~Reader() { close(); }

 private:
  void *file_ = nullptr;
  uint32_t gen_ = 0;
  uint64_t size_ = 0;
};

}  // namespace storage
