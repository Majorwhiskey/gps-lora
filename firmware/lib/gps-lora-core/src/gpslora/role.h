// SPDX-License-Identifier: Apache-2.0
// Which firmware this is. Fixed at build time: tracker.ino and receiver.ino
// each pass their own role to app::begin().
#pragma once

namespace role {

enum class Role : unsigned char { Tracker, Receiver };

void set(Role r);
Role current();
bool receiver();
const char *name();  // "tracker" or "receiver"

}  // namespace role
