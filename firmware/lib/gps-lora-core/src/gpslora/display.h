// SPDX-License-Identifier: Apache-2.0
// SSD1306 128x64 status screen on I2C. The panel is fitted at final assembly,
// so a missing panel is normal on a bare board and is not an error.
#pragma once

namespace display {

bool begin();
void render();  // Draws the current status of all modules
void message(const char *line1, const char *line2 = nullptr);

}  // namespace display
