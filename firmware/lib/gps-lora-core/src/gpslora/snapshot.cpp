// SPDX-License-Identifier: Apache-2.0
#include "snapshot.h"

#include <Arduino.h>

namespace snapshot {
namespace {

portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
Gnss gnssCopy;
Rx rxCopy;

}  // namespace

void publishGnss(const Gnss &g) {
  portENTER_CRITICAL(&mux);
  gnssCopy = g;
  portEXIT_CRITICAL(&mux);
}

Gnss gnss() {
  portENTER_CRITICAL(&mux);
  Gnss g = gnssCopy;
  portEXIT_CRITICAL(&mux);
  return g;
}

bool fixFresh(const Gnss &g) { return g.fix && g.epochMs && millis() - g.epochMs < 2500; }

void publishRx(const Rx &r) {
  portENTER_CRITICAL(&mux);
  rxCopy = r;
  portEXIT_CRITICAL(&mux);
}

Rx rx() {
  portENTER_CRITICAL(&mux);
  Rx r = rxCopy;
  portEXIT_CRITICAL(&mux);
  return r;
}

}  // namespace snapshot
