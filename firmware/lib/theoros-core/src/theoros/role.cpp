// SPDX-License-Identifier: Apache-2.0
#include "role.h"

namespace role {
namespace {

Role r = Role::Tracker;

}  // namespace

void set(Role v) { r = v; }
Role current() { return r; }
bool receiver() { return r == Role::Receiver; }
const char *name() { return r == Role::Receiver ? "receiver" : "tracker"; }

}  // namespace role
