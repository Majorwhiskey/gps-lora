# Theoros PCB design: USB-powered ESP32-S3 GPS logger with LoRa telemetry

Mains/USB powered. No battery. Production-grade, fully machine-assembled
4-layer board: every component is placed and reflowed by the assembler
(Lion Circuits, Bangalore, turnkey PCBA), single-sided, top side only. No
headers, no breakout boards, all routing internal. The only manual step is
plugging the OLED panel's flex cable into its connector at final assembly.

Datasheet citations in this document use the short names below. The documents
themselves are listed in [datasheets/README.md](datasheets/README.md).

| Short name | Document |
|---|---|
| WROOM | ESP32-S3-WROOM-1 datasheet v1.8 |
| S3 | ESP32-S3 series datasheet v2.2 |
| HDG | ESP32-S3 hardware design guidelines |
| SAM-DS | SAM-M10Q data sheet UBX-22013293 |
| SAM-IM | SAM-M10Q integration manual UBX-22020019 |
| RFM | RFM95W/96W/98W datasheet v2.0 |
| AP | AP7361C datasheet DS37274 |
| SSD | SSD1306 datasheet rev 1.1 and charge pump app note rev 0.4 |
| OLED | EastRising ER-OLED0.96-1 series datasheet rev 2.0 |
| USBLC6 | USBLC6-2 datasheet (ST) |

## Scope

- ESP32-S3-WROOM-1-N8 (module, PCB antenna)
- USB-C, native USB — no bridge chip
- u-blox SAM-M10Q GNSS module (integrated patch antenna), UART
- microSD socket, SPI2
- RFM95W-868S2 (SX1276) radio module, SPI3, u.FL antenna connector
- EastRising ER-OLED0.96-1.1W 128x64 OLED panel (SSD1306), I2C, Hirose FH12 ZIF connector
- 5V to 3.3V low-dropout linear regulation

## Integration strategy

| Function | Part | Reason |
|---|---|---|
| GNSS | u-blox SAM-M10Q | Patch antenna, SAW filter and LNA are integrated and tuned by u-blox. No RF design on our board beyond following the integration manual's ground plane and keep-out rules. |
| LoRa | RFM95W-868S2, castellated module | Pre-certified radio module. Antenna on a cable from u.FL to an enclosure bulkhead SMA, which moves the transmitting antenna off the board and away from the GNSS patch. |
| Display | Bare SSD1306 panel, FPC into a ZIF connector | A glass panel cannot go through reflow, so the ZIF connector is reflowed and the panel is plugged in at final assembly. This is how displays are fitted in any production product. |
| Storage | Push-push microSD socket | Passive mechanical part. |

A chip-down GNSS (MAX-M10S plus a discrete patch) was considered and rejected
for v1: it adds a 50 ohm feed and patch ground-plane design for no functional
gain over the SAM-M10Q.

## Selected parts

Parts whose exact type matters. Generic passives (resistors, MLCCs) are chosen
at BOM stage from stocked equivalents.

| Ref | Function | Part | Notes |
|---|---|---|---|
| U301 | MCU module | Espressif ESP32-S3-WROOM-1-N8 | |
| U202 | 3.3V LDO | Diodes AP7361C-33E-13 | SOT-223, E package pinout only |
| U501 | OLED VBAT LDO | TI TLV75801PDBV | Adjustable, set to 3.795V by 59k/10k (VFB = 0.55V) |
| U201 | USB ESD | ST USBLC6-2SC6 | |
| U401 | GNSS | u-blox SAM-M10Q | Pin-compatible with SAM-M8Q; stock SAM-M8Q symbol and footprint used |
| U402 | LoRa | HopeRF RFM95W-868S2 | No substitution |
| U302 | EN supervisor (DNP) | Microchip MCP120T-300I/TT | Open-drain, 3.0V ±75mV, 350ms reset hold |
| J201 | USB-C | HRO TYPE-C-31-M-12 | 16-pin USB 2.0 |
| J401 | Antenna | Hirose U.FL-R-SMT-1 | |
| J501 | microSD | Hirose DM3AT-SF-PEJM5 | Push-push |
| J502 | OLED FPC | Hirose FH12-30S-0.5SH(55) | Bottom contact, 0.5mm pitch |
| — | OLED panel | EastRising ER-OLED0.96-1.1W | Bought separately, fitted at final assembly |
| F201 | Polyfuse | Littelfuse 1206L075THYR | 0.75A hold, 1.5A trip, 8V. The 1206L075SLYR is only 6V |
| D201 | VBUS TVS | Littelfuse SMF5.0A | Uni, 5V standoff, 6.4V min breakdown, 9.2V clamp, SOD-123FL |
| D202 | Holdup diode (DNP) | Schottky, SMA | Select with holdup option |
| D401 | GNSS backup diode | BAT54 class, SOD-323 | Charges C403 from 3V3 through R401 (1k) |
| C403 | GNSS backup | Seiko CPH3225A | 11 mF 3.3 V chip EDLC, 3.2 x 2.5 mm, reflowable, polarised. **Rated -20 to +60°C only** |
| SW301-303 | Buttons | C&K PTS810 SJM 250 SMTR LFS | Top actuated, 4.2 x 3.2mm |

## Why the S3

Native USB on GPIO19/20 removes the USB-UART bridge, its crystal, and the
two-transistor DTR/RTS auto-reset circuit entirely. USB Serial/JTAG is built in,
so debugging needs no external probe.

Cost: pin assignments do not port from classic ESP32. Libraries and logic do.

## Pin assignment

| GPIO | Function | Bus | Notes |
|---|---|---|---|
| 17 | GNSS RXD (ESP32 TX) | UART1 | 100 ohm series resistor |
| 18 | GNSS TXD (ESP32 RX) | UART1 | 100 ohm series resistor |
| 15 | GNSS TIMEPULSE (PPS) | input | Glitch-free pin, see GNSS section |
| 7 | GNSS RESET_N | open drain | Last-resort recovery only |
| 8 | OLED SDA | I2C | |
| 9 | OLED SCL | I2C | |
| 41 | OLED RES# | | 10k pull-up |
| 10 | SD CS | SPI2 (IO_MUX FSPICS0) | |
| 11 | SD MOSI | SPI2 (IO_MUX FSPID) | |
| 12 | SD SCK | SPI2 (IO_MUX FSPICLK) | Direct, see EMC provisions |
| 13 | SD MISO | SPI2 (IO_MUX FSPIQ) | |
| 14 | LoRa NSS | SPI3 | |
| 47 | LoRa MOSI | SPI3 | |
| 16 | LoRa SCK | SPI3 | Direct, see EMC provisions |
| 21 | LoRa MISO | SPI3 | |
| 48 | LoRa RESET | | Drive low or high-Z only |
| 1 | LoRa DIO0 | interrupt | |
| 42 | LoRa DIO1 | interrupt | RX timeout, needed for LoRaWAN stacks |
| 4 | Eject button, to GND | | |
| 2 | Status LED | | |
| 5 | VBUS sense | | Holdup option, see power-loss handling |

Spare: 6, 38.

Pin choice follows the board layout: the four LoRa lines that reach the module's
left edge (NSS, MISO, MOSI, RESET on pins 22-25) are ordered to match the
routing channel beside the module, and DIO0/DIO1 use bottom-edge pins. Changed
during layout (rev V1.0): PPS 47→15, LoRa MOSI 15→47, LoRa RESET 38→48,
LoRa DIO0 48→1.

Do not use: 39, 40. In USB-OTG download mode the S3 drives GPIO39 (MTCK) low
and GPIO40 (MTDO) high (HDG Table 12), which would fight any device output
connected to them. GPIO38 is also driven low in that mode; it is left unused.
LoRa RESET is on GPIO48, which download mode does not drive. Burning
`EFUSE_DIS_USB_OTG_DOWNLOAD_MODE` would remove the behaviour entirely, but the
pin assignment above makes it unnecessary.

SD on GPIO10-13 uses the SPI2 IO_MUX pins directly, bypassing the GPIO matrix,
which allows the full 80MHz SPI clock if a card supports it (S3, SPI2).

All assigned pins are brought out on WROOM-1 module pins (WROOM Table 3-1).
GPIO47/48 (LoRa MOSI, LoRa RESET) run at 3.3V on the N8; only R16V variants
put them at 1.8V.

### Power-up glitches

GPIO1-14 and GPIO17 output a ~60us low pulse during chip power-up, and GPIO18
outputs both a low and a high pulse (S3 Table 2-2). Consequences:

- GNSS TIMEPULSE cannot be on any of these pins (see GNSS section). It is on
  GPIO15, which has no glitch.
- GPIO1 (LoRa DIO0) glitches low at power-up. DIO0 is an input to the ESP32
  and the radio is idle at that time, so this is harmless.
- GPIO7 (GNSS RESET_N): the 60us pulse is far shorter than the 1ms minimum
  reset pulse, so it does not reset the receiver.
- GPIO18: the glitch briefly drives against the GNSS TXD output. The 100 ohm
  series resistor limits the current.
- SD CS and LoRa NSS glitch low before either device is initialised. Harmless.

### Pins that must stay free

- GPIO26-32: SPI flash on the module. Not brought out.
- GPIO33, 34: not brought out on WROOM-1.
- GPIO35-37: brought out, but connected to the octal PSRAM on R8/R16V modules
  (WROOM Table 3-1 note b). The N8 has no PSRAM, so they are usable, but they
  are kept free so the board accepts an N8R8 module without changes.
- GPIO19, 20: native USB D- and D+.
- GPIO43, 44: UART0, the console. Keep for debug output.
- GPIO45: strapping, VDD_SPI voltage select. Must not be pulled high; GPIO45 = 1
  selects 1.8V VDD_SPI (WROOM ch. 8). Default weak pull-down, leave
  unconnected.
- GPIO46: strapping, I/O. Must be low only for joint download boot with
  GPIO0 = 0; any value is allowed for normal SPI boot (S3 Table 3-3). Default
  weak pull-down, leave unconnected.
- GPIO0: strapping, boot mode. Boot button and pull-up only.
- GPIO3: strapping, JTAG source select. Ignored while the eFuse
  `EFUSE_STRAP_JTAG_SEL` is unburned (S3 Table 3-5). Leave unconnected.

Separate SPI buses for card and radio are deliberate. SD cards do not always
release MISO cleanly when deselected, and a shared bus turns that into
intermittent radio corruption. The S3 has the peripherals to avoid it.

## USB-C

- **Connector:** 16-pin USB 2.0 SMD receptacle with through-hole shell tabs
  (e.g. HRO TYPE-C-31-M-12). Not the 24-pin full-featured part.
- **Two 5.1k resistors**, CC1 to GND and CC2 to GND. Separate resistors, not one
  shared. Without them a compliant USB-C source sees no sink and supplies
  nothing. The board will appear dead on a modern charger while working on an
  old USB-A cable.
- **Tie A6 to B6 (D+) and A7 to B7 (D-) at the connector.** Without this, USB
  data works in only one plug orientation.
- D+ to GPIO20, D- to GPIO19, each through a series resistor footprint fitted
  with 0 ohm, plus a capacitor-to-GND footprint left unfitted, both placed
  close to the module (HDG §1.3.13). 22-33 ohm and a small capacitor can be
  fitted later if EMC testing calls for it.
- ESD protection on the data pair: USBLC6-2SC6 (SOT23-6), placed as close to
  the connector as possible. Pin 1/6 I/O1 (D+), pin 3/4 I/O2 (D-), pin 2 GND,
  pin 5 VBUS. Each data line passes straight through between its pin pair
  (USBLC6 pinout).
- 5V unidirectional TVS diode on VBUS after the polyfuse (HDG §1.3.2: ESD
  protection at the main power entrance). A sustained overvoltage then makes
  the TVS conduct and trips the polyfuse.
- Shield to GND through 1M in parallel with 4.7nF. This avoids a DC ground
  loop through the cable shield while still shunting ESD and RF to ground.
- VBUS to the regulator input via a 750mA-hold polyfuse.

## Power

### Budget

| Load | Current | Source |
|---|---|---|
| ESP32-S3, modem sleep | 22-64mA | WROOM Table 6-6 |
| ESP32-S3, WiFi receive / listening | 95-97mA | WROOM Table 6-5 |
| ESP32-S3, WiFi transmit burst | up to 355mA | WROOM Table 6-4 |
| GNSS tracking | 12-15mA | SAM-DS Table 14 |
| GNSS start-up inrush | up to 100mA | SAM-DS §4.3 |
| SD write burst | 100mA | |
| SX1276 transmit at +20dBm | 120mA | RFM, IDDT |
| OLED | 10-20mA | |
| **Worst-case coincident** | **~600mA** | |
| **Typical average** | **~150-250mA** | |

### Supply requirement

With 5.1k pull-downs the board is a USB-C sink using only "Default USB Power",
for which a USB 2.0 source guarantees just 500mA. In practice almost every
USB-C charger supplies 1.5A or more. The board is therefore specified as:

- **Supply: 5V, 1A minimum** (any USB-C phone charger).
- **Firmware rule: WiFi transmit and LoRa transmit never overlap.** This keeps
  real peaks near 450mA and inside a 500mA source when one is used.

The polyfuse is rated 750mA hold so that worst-case bursts never approach the
trip point. It protects against a short circuit, not against overload.

### Regulator

**AP7361C-33E-13, SOT-223 (E package).** 1A, stable with ceramic output
capacitors, no enable pin on this package (AP).

**The AP7361C comes in two SOT-223 variants with different pinouts.** SOT223
(E suffix) is pin 1 IN, pin 2 GND, pin 3 OUT. SOT223R (ER suffix) is pin 1
GND, pin 2 OUT, pin 3 IN. The footprint, symbol and BOM must all be the E
variant.

| Parameter | Value (AP) |
|---|---|
| Input range | 2.2-6.0V, 6.5V absolute maximum |
| Dropout at 1A | 340mV typ (table), 360mV typ (features); no maximum given |
| Dropout at 300mA | 90mV typ, 140mV max |
| Current limit | 1.1A min, 1.5A typ |
| Thermal shutdown | 150°C, ~20°C hysteresis |
| θJA, SOT-223, minimum pad | 110°C/W |
| Input / output capacitor | ≥1uF / ≥2.2uF ceramic |

The ESP32-S3 needs a regulator rated for at least 500mA (WROOM Table 6-2,
HDG §1.3.2). The AP7361C meets this with margin.

The AMS1117-3.3 from the original draft was rejected. Its 1.1-1.3V dropout at
600mA needs at least 4.5V input. USB allows VBUS to fall to 4.75V at the source
and lower at the device after cable and polyfuse losses, which would let the
3.3V rail sag during WiFi transmit bursts. Several AMS1117 clones also require
a tantalum output capacitor for stability.

Input headroom check at the worst-case USB voltage:

| | Volts |
|---|---|
| VBUS minimum at device | 4.40 |
| Polyfuse drop at 600mA | -0.15 |
| Holdup diode (only when fitted, see below) | -0.45 |
| Regulator input | 3.80 |
| Required (3.3 + 0.36 typical dropout at 1A) | 3.66 |

The margin rests on a typical dropout figure, because the datasheet gives no
maximum at 1A. At the 300mA average load the guaranteed maximum is 140mV,
which leaves a wide margin.

Dissipation is (Vin - 3.3) x I. At 300mA average that is ~0.5W, at 600mA peak
~1.0W. On the minimum pad, 0.5W is a 55°C rise and a continuous 1W would hit
thermal shutdown at about 40°C ambient. Peaks are short bursts, so the average
governs. Provide at least 400mm2 of top copper on the tab, stitched to the
inner planes with thermal vias, and measure the temperature rise on the first
boards.

**Place it at the opposite end of the board from the GNSS module.** The GNSS
TCXO is sensitive to heat and sudden temperature drift (SAM-IM §4.4); a warm
regulator alongside produces slow drift that presents as degraded fixes. The
inner planes spread heat well, which makes physical distance more important on
4 layers, not less.

A 5V to 3.3V buck would remove the heat at ~95% efficiency, but injects
switching noise in the band the GNSS receiver cares about. For v1 the heat is
the lesser risk. Revisit in v2 if thermal measurements justify it.

### Decoupling

| Location | Parts | Basis |
|---|---|---|
| Regulator input | 22uF + 0.1uF | AP minimum 1uF |
| Regulator output | 22uF + 0.1uF | AP minimum 2.2uF |
| ESP32-S3 3V3 | 100uF + 10uF + 0.1uF | WROOM reference: 22uF + 0.1uF; HDG: at least 10uF |
| SD socket | 100uF + 10uF + 0.1uF | Design choice, 100mA write bursts |
| LoRa module | 100uF + 10uF + 0.1uF | Design choice, 120mA TX bursts; RFM reference shows none |
| GNSS module | 10uF + 0.1uF | Design choice; SAM-IM typical design shows none |
| OLED panel | see display section | OLED §1.6.2 |

All SMD, no through-hole electrolytics. 0.1uF in 0402, 10uF and 22uF in 0805,
100uF as SMD polymer capacitors or 1210 X5R ceramic. Check DC-bias derating
for ceramics: a 6.3V 100uF 1210 retains well under half its value at 3.3V.

Bulk capacitance is not optional. 120mA LoRa bursts and 100mA SD writes on a
shared rail will brown out the MCU mid-write.

The total capacitance behind VBUS exceeds the USB 2.0 inrush limit of 10uF.
This matters only for USB-IF certification, which is not a goal for this board.

## GNSS (SAM-M10Q)

### Pins (SAM-DS Table 9)

| Pin | Name | Connection |
|---|---|---|
| 1, 4, 5, 6, 10, 11, 15, 16, 20 | GND | Ground, with vias |
| 2 | V_IO | 3V3, tied to VCC |
| 3 | V_BCKP | Backup network D401/R401/C403 from 3V3, see below |
| 7 | TIMEPULSE | GPIO15 |
| 8 | SAFEBOOT_N | Open, with a test pad |
| 9 | SDA | Open |
| 12 | SCL | Open |
| 13 | TXD | GPIO18 via 100 ohm |
| 14 | RXD | GPIO17 via 100 ohm |
| 17 | VCC | 3V3 |
| 18 | RESET_N | GPIO7 |
| 19 | EXTINT | Open |

### Supply

- VCC and V_IO tied together to 3V3, as in the u-blox typical design
  (SAM-IM §4.1.1, Fig. 28). VCC range 2.7-3.6V, V_IO 2.7V to VCC.
- **No more than 0.2 ohm series resistance in the supply** (SAM-IM §4.1.1).
  No ferrite bead unless its DC resistance is below this.

### TIMEPULSE and SAFEBOOT_N

SAFEBOOT_N is connected to TIMEPULSE inside the module through 1k. If
TIMEPULSE is pulled low at start-up, the receiver enters safe boot mode
(SAM-IM §3.2.3.3). Therefore:

- TIMEPULSE goes to GPIO15, which has no power-up glitch. It must not go to
  GPIO1-14, 17 or 18, which drive low for ~60us at power-up.
- No pull-down, capacitor or other load on TIMEPULSE.
- GPIO15 is configured as an input with no pull-down.
- SAFEBOOT_N gets a test pad so it can be grounded during power-up to recover
  a receiver with corrupted firmware.

### RESET_N

- Internal 7-13k pull-up to V_IO (SAM-DS Table 13). Minimum pulse 1ms.
- **No capacitor on RESET_N** (SAM-IM §3.2.3.1).
- RESET_N clears battery-backed RAM: configuration, RTC and orbit data, which
  forces a cold start. u-blox says to use it only in critical situations.
  Firmware uses the UBX-CFG-RST software reset for routine resets and drives
  GPIO7 low (open drain) only to recover a hung receiver.

### Backup supply

- V_BCKP (1.65-3.6 V, 28 uA in hardware backup mode, SAM-DS Tables 12 and
  15) is fed from 3V3 through D401 (BAT54) and R401 (1k) and held up by C403,
  a Seiko CPH3225A 11 mF chip EDLC. The diode drop keeps the charge at about
  3.1-3.2 V, under the part's 3.3 V limit; Seiko needs no charge-current limit.
- Hold-up: about 5 uAh usable from 3.1 V down to 1.65 V, so roughly 10 minutes
  at 28 uA. A restart within that window (a stop, a brief power cut) is a ~1 s
  hot start; longer outages fall back to a warm or 23-29 s cold start
  (SAM-DS Tables 1-2). Larger parts (coin cells, 0.22 F coin EDLCs) give hours
  to days but do not fit beside V_BCKP or cannot be reflowed.
- Polarity matters: pad 1 is + (the end with the printed + mark), on the
  V_BCKP side. Rated -20 to +60 °C: in a hot cabin expect faster ageing.
- C403 sits just outside the 10 mm GNSS keep-out, in line with R401.

### UART

9600 baud 8N1 by default, NMEA output (SAM-DS Table 18). Firmware raises the
rate and waits ~100ms after a baud change. The receiver disables RX after more
than 100 framing errors per second (SAM-IM §3.2.1).

### Placement (SAM-IM §4.3.1.1, §4.4)

This section sets the board outline.

- **Centre of a solid ground plane of 50 x 50mm.** Performance degrades
  significantly below 40 x 40mm. The module is not placed at a board edge.
- Nothing within 10mm of any module edge. Components taller than 3mm at least
  10mm away.
- **No signal traces under the module, on any layer.**
- No layer changes within 20mm of the module edge.
- Ground under the module filled with GND vias. GND pads may use 0.2mm thermal
  reliefs.
- Solder mask openings 0.1mm larger than the pads; 120um stencil.
- Enclosure at least 5mm above the antenna.
- Patch faces up; the enclosure lid above it must not be metal or metallised.

### Assembly (SAM-DS Table 20, SAM-IM §5)

- MSL 4. Kept in dry pack and baked if the floor life is exceeded.
- Reflow: preheat ≤3°C/s for 60-120s ending at 150-200°C, 40-60s above 217°C,
  peak 245°C, cooling ≤4°C/s. Convection oven preferred.
- One reflow in normal production, plus at most one more for rework. No
  hot-air gun.
- No-clean paste. No washing, solvent or ultrasonic cleaning.
- **No conformal coating or potting.** It detunes the antenna and voids the
  warranty.
- Pick-and-place aligns to the pads, not the module edge.

## microSD

- SPI mode, 3.3V.
- **Pull-ups, 47k to 3V3, on CS, MISO (DAT0), DAT1 and DAT2.** Cards start in
  SD mode and need defined levels on these lines to enter SPI mode reliably;
  floating DAT1/DAT2 cause intermittent init failures that depend on the card
  brand.
- Card-detect switch on the socket left unconnected in v1.

## LoRa radio (RFM95W-868S2)

### Part

- **Order code RFM95W-868S2** (RFM §8.2). The same datasheet, pin table and
  package cover RFM95W-915S2, RFM96W-433S2/470S2 and RFM98W-169S2/433S2/470S2,
  so a wrong part fits the footprint. The BOM states the full code and forbids
  substitution.
- The synthesiser covers 862-1020MHz, which includes India's 865-867MHz band.

### Pins (RFM Table 2)

| Pin | Name | Connection |
|---|---|---|
| 1, 8, 10 | GND | Ground |
| 2 | MISO | GPIO21 |
| 3 | MOSI | GPIO47 |
| 4 | SCK | GPIO16 |
| 5 | NSS | GPIO14 |
| 6 | RESET | GPIO48 |
| 7 | DIO5 | Open |
| 9 | ANT | u.FL via 50 ohm microstrip |
| 11 | DIO3 | Open |
| 12 | DIO4 | Open |
| 13 | 3.3V | 3V3 |
| 14 | DIO0 | GPIO1 |
| 15 | DIO1 | GPIO42 |
| 16 | DIO2 | Open |

The RFM datasheet text calls the reset pin "pin 7 (NRESET)" in §7.2. That text
was copied from the SX1276 chip datasheet; on the module, pin 6 is RESET and
pin 7 is DIO5.

Package: 16 x 16mm, 2mm pitch castellations, 8 per side (RFM Fig. 57).

### RESET

- Active low. Left floating during power-on reset, then ready after 10ms.
  Manual reset: pull low for at least 100us, release, wait 5ms (RFM §7.2).
- The datasheet only describes pulling low and releasing. GPIO48 is therefore
  either high-Z (input) or driven low, never driven high.

### SPI and RF

- SPI mode 0, maximum 10MHz (RFM Table 10).
- +20dBm on PA_BOOST is limited to **1% duty cycle at VSWR ≤3:1**. Continuous
  operation is rated up to +17dBm (RFM Tables 33-34).
- u.FL connector, cabled to a bulkhead SMA on the enclosure. The trace from
  the ANT pad to the u.FL is a 50 ohm microstrip over the solid L2 ground, kept
  under 10mm, flanked by ground-via fences.
- The datasheet gives no matching or ESD network for ANT. The module is ESD
  class 2 (HBM); the u.FL is internal to the enclosure.

## Display (bare SSD1306 panel)

### Panel and connector

| Item | Part | Key data |
|---|---|---|
| Panel | **EastRising ER-OLED0.96-1.1W** (white, connector-type FPC, bottom contact) | 0.96", 128x64, SSD1306, 26.7 x 19.26 x 1.4mm |
| Connector | **Hirose FH12-30S-0.5SH(55)** | 30-pin, 0.5mm pitch, bottom contact, rotating ZIF, SMT right angle, for 0.3mm FPC |

FPC tail (OLED drawing 1.4.1): 30 pins at 0.5mm pitch, 0.30mm conductor
width, 0.3 ± 0.05mm thick at the contacts with a 3.0mm stiffener, contacts on
the bottom face. The panel lies face up on the board and its FPC runs straight
into the connector with no fold, so the contacts face down onto the
bottom-contact FH12.

Alternatives considered:

- ER-OLED0.96-1.3W, the same panel with top-contact FPC. Would need a
  top-contact connector or a 180° FPC fold under the panel.
- Raystar REX012864D (ZIF version). Same pinout and a wider -40 to +80°C
  rating, but a 0.7mm FPC pitch, for which no widely stocked ZIF connector
  was found.
- Winstar WEO012864D. Only the hotbar (solder) FPC datasheet was available.

The panel is bought directly from BuyDisplay and supplied for final assembly;
it is not part of the PCBA BOM.

### Pins (OLED datasheet, pin table)

| Pin | Name | Connection |
|---|---|---|
| 1, 30 | NC (GND) | GND (support pins) |
| 2 | C2N | C6 1uF to C2P |
| 3 | C2P | C6 |
| 4 | C1P | C5 1uF to C1N |
| 5 | C1N | C5 |
| 6 | VBAT | VBAT rail, C2 1uF to GND |
| 7 | NC | Open |
| 8 | VSS | GND |
| 9 | VDD | 3V3, C1 1uF to GND |
| 10 | BS0 | GND |
| 11 | BS1 | 3V3 |
| 12 | BS2 | GND |
| 13 | CS# | GND |
| 14 | RES# | GPIO41, 10k pull-up to 3V3 |
| 15 | D/C# | GND (I2C address 0x3C) |
| 16 | R/W# | GND |
| 17 | E/RD# | GND |
| 18 | D0 | SCL (GPIO9) |
| 19 | D1 | SDA (GPIO8), tied to D2 |
| 20 | D2 | SDA (GPIO8), tied to D1 |
| 21-25 | D3-D7 | GND |
| 26 | IREF | R1 390k to VLSS |
| 27 | VCOMH | C4 4.7uF X7R to VLSS |
| 28 | VCC | C3 2.2uF to VLSS (internal charge pump output) |
| 29 | VLSS | GND |

Capacitor and resistor values are from the panel's "VCC generated by internal
DC/DC circuit" application circuit (OLED §1.6.2). They differ from the
controller app note (VCOMH 4.7uF not 2.2uF, IREF 390k not 400k); the panel
values apply.

### Power (OLED §3.2)

| Rail | Panel limit | Design |
|---|---|---|
| VDD | 1.65-3.3V (4.0V abs. max) | 3V3. At the top of the range; within absolute maximum with regulator tolerance. |
| VBAT (internal DC/DC on) | **3.5-4.2V**, 5V abs. max | **3.8V LDO (TLV75801, adjustable)** from the 5V rail after the polyfuse |
| VBAT current | 25.6mA typ, 32mA max | LDO rated ≥50mA |
| VCC (generated) | 7.0-7.5V | Charge pump output, capacitor only |

The panel narrows VBAT to 3.5-4.2V; the controller app note allowed 3.3V.
VBAT from 3V3 is therefore out of specification, which is why the 3.8V LDO
exists. A 3.8V ±2% LDO stays inside the window. Its input is the 5V rail,
≥4.25V at minimum USB voltage, so dropout must be ≤0.4V at 32mA. With the
holdup diode fitted and VBUS at its minimum, the rail can fall to ~3.8V and
VBAT may sag below 3.5V; the display dims but nothing is damaged.

### Interface

- I2C up to 400kHz. Pull-ups 4.7k to 3V3 on the main board (the bare panel
  has none).
- RES# has a 10k pull-up so it has a defined level while GPIO41 floats at
  boot. Firmware pulses RES# low for at least 3us after VDD is stable, then
  runs the panel's initialisation sequence (OLED §4.4) with the internal
  DC/DC values: charge pump 8Dh 14h, contrast 81h CFh, pre-charge D9h F1h,
  then AFh.

### Temperature

**The panel is rated -30 to +70°C operating** (OLED §2). The rest of the board
is rated to at least +85°C. A vehicle dashboard in direct sun can exceed 70°C.
Keep the board out of direct sun in the enclosure design; a wider-temperature
panel is a v2 item if field use needs it.

### Mechanical

- The panel sits on the top side, face up, over a component-free area, held by
  double-sided foam tape, with its outline on the silkscreen.
- The FH12 sits beyond the panel's FPC edge, aligned so the FPC enters
  straight. Exact offset from the FH12 datasheet's FPC insertion depth and the
  panel drawing, set at layout.
- The FH12 is rotated 180 degrees, so the panel (pin 1 on the left in the
  front view) lands mirrored: panel pin n mates J502 pin 31-n. The schematic
  shows this with a mirrored J502 symbol.
- The enclosure window follows the panel position.

## Boot and reset

- EN pull-up 10k to 3V3, 1uF to GND for the power-on delay (HDG §1.3.3).
- Footprint, unfitted in v1, for a ~3.0V open-drain voltage supervisor on EN.
  HDG §1.3.3 calls for one when the supply rises or falls slowly, which the
  holdup option causes. Fit it together with the holdup parts.
- RESET button: EN to GND.
- BOOT button: GPIO0 to GND, **plus a 10k pull-up to 3V3**. No large
  capacitor on GPIO0 (HDG §1.3.9).
- Eject button: GPIO4 to GND.
- All buttons SMD tactile switches, placed at the board edge so the enclosure
  can reach them.

Native USB can enter download mode without the buttons, but fit both. They cost
nothing and recover a board that firmware has wedged.

## EMC provisions

- **499 ohm series resistor on UART0 TX (GPIO43)** (HDG §1.3.7).
- 100 ohm series resistors on UART1, both directions (GPIO17, GPIO18).
- **SPI clocks (GPIO12 SD SCK, GPIO16 LoRa SCK): no filter footprints.**
  HDG §1.3.8 suggests a series resistor and capacitor close to the module.
  The draft had them (R309/C307, R310/C308), but at layout no position on
  either clock path could take them without forcing crossings, so they were
  removed (rev V1.0). Mitigation: both clocks run point-to-point over the
  solid In1 ground plane, at the far end of the board from the GNSS, and
  firmware keeps SPI clocks at the lowest rate that meets throughput. If EMC
  testing shows GNSS desense, v2 restores the footprints with the clock pins
  re-placed.
- USB series resistor and capacitor footprints, see USB-C.

## Service and test access

**Tag-Connect TC2030-NL footprint** (pads only, no component fitted):
UART0 TX (GPIO43), UART0 RX (GPIO44), EN, GPIO0, 3V3, GND.

This is the only way to reach a console if the USB stack itself is the thing
that is broken, which is exactly when you need it.

**Test pads** (SMD, 1mm round) for production test: VBUS, 5V after the
polyfuse, 3V3, OLED VBAT (3.8V), GND, and GNSS SAFEBOOT_N.

## Power-loss handling

No battery means every disconnection is an unclean shutdown. In a vehicle, that
is every single time the engine stops.

**v1 approach: sync the SD card after every record.** The reason for batching
writes was battery energy, and that reason no longer exists. At 1Hz this costs
about 20ms of card activity per second and narrows the corruption window to
roughly 2%.

**Holdup option, footprints only, marked DNP in v1:**

- Schottky diode (≤0.45V at 600mA) from the polyfuse output to the regulator
  input rail, so a holdup capacitor cannot back-feed the USB port. A parallel
  0 ohm resistor, fitted in v1, bridges it.
- 2200uF holdup capacitor on the regulator input rail, after the diode.
- Divider 10k/15k from VBUS, before the diode, to GPIO5 (~3.0V when present).
  Sensing before the diode reports power loss immediately, not after the
  capacitor has drained.
- EN voltage supervisor fitted at the same time (see boot and reset).

Holdup energy, discharging from 4.55V to the 3.66V regulator limit:
E = ½ × 2200uF × (4.55² − 3.66²) ≈ 8mJ. With radios off and an SD write in
progress (~150mA at ~4.1V, ~0.6W) that is **~13ms**. This is enough to finish
a write already in flight, but not to open and close a file, since SD sync
latency can reach 100ms or more on some cards. 100ms of holdup would need about
15,000uF, or a supercapacitor with an inrush limiter. That is a v2 decision,
made only if field testing shows corruption despite per-record sync.

## Schematic sheets

Hierarchical, one root sheet with four sub-sheets:

1. **Power and USB** — USB-C connector, CC resistors, USBLC6-2, VBUS TVS,
   shield network, polyfuse, holdup option, AP7361C, bulk caps, power test
   pads.
2. **MCU** — ESP32-S3-WROOM-1, EN RC and supervisor option, GPIO0 pull-up,
   boot, reset and eject buttons, status LED, USB series parts, UART and SPI
   clock EMC parts, Tag-Connect footprint.
3. **Radio** — SAM-M10Q with backup option and SAFEBOOT_N test pad, RFM95W
   with u.FL, per-module decoupling.
4. **Storage and display** — microSD socket and pull-ups, FH12 ZIF connector,
   3.8V VBAT LDO, charge-pump and IREF parts, RES# pull-up, I2C pull-ups.

## Stackup (4-layer, 1.6mm)

| Layer | Use |
|---|---|
| L1 (top) | Components, signals, RF feeds, GND pour |
| L2 | **Solid GND. No traces, ever.** |
| L3 | 3V3 plane, with a VBUS/5V region around the regulator input |
| L4 (bottom) | Signals, GND pour. No components. |

Lion Circuits' published standard 4-layer 1.6 mm stackup (capabilities page,
"Stack-Up Details"): 35 um copper / 0.12 mm 2116 prepreg / 1.165 mm NP-140
core / 0.12 mm 2116 prepreg / 35 um copper. Lion publishes no Dk; NP-140 is
Dk 3.8-4.4 (Nan Ya data), so impedances below are given for Dk 3.9-4.4, with
solder mask, from a 2D field solve:

| Trace as routed | Target | Result |
|---|---|---|
| LORA_ANT, 0.2 mm, CPWG with 0.25 mm gaps to the L1 pour, 5.3 mm long | 50 ohm | 46.6-48.9 ohm |
| USB D+/D-, 0.2 mm on L1 or L4 (L4 references the L3 plane, same 0.12 mm) | 45 ohm each | 47.6-50.0 ohm |
| USB pair where coupled (0.3 mm gap, 4.4 mm of the run) | 90 ohm | 89-93 ohm |
| USB pair elsewhere (lines > 0.7 mm apart) | 90 ohm | about 95-100 ohm |

All are inside USB's 90 ohm +/-15 % and within a few percent of 50 ohm on a
trace that is 1/33 of a wavelength at 868 MHz, so the board needs **no
impedance-controlled order**. For reference, the exact-target widths on this
stackup are 0.18 mm (50 ohm CPWG, 0.2 mm gap) and 0.18 mm at 0.2 mm spacing
(90 ohm differential). If Lion's quote shows a different L1-L2 prepreg (for
example 7628 at 0.21 mm), recompute before ordering: the widths roughly double.

## Layout rules

1. L2 solid ground everywhere. L1 and L4 ground pours stitched to it with vias
   every ~5mm along edges and around RF areas, ~10mm elsewhere.
2. **ESP32-S3 module antenna** (HDG §1.4.7, Fig. 26): module at a board edge
   with the antenna beyond the board outline and its feed point close to the
   edge. Where the board continues beside the antenna, cut it back at least
   15mm from the antenna. No copper on any layer under or beside the antenna.
   Do not place the module mid-board with a cut-out on all sides. Inside the
   enclosure, at least 15mm clearance around the antenna in all directions.
   Module outline 18 x 25.5mm (WROOM Fig. 10-1).
3. **GNSS zone** per the GNSS placement section: module centred in a 50 x 50mm
   solid ground area, 10mm clear around it, no signal traces under it on any
   layer, no layer changes within 20mm.
4. GNSS module, LoRa u.FL and ESP32 antenna as far apart as the outline allows.
5. Regulator far from the GNSS module.
6. Neither SPI bus routed through the GNSS zone. SPI clock harmonics desense
   GNSS receivers and this is the usual cause of poor satellite counts on
   integrated boards.
7. Signals changing layer next to a ground via, so the return current has a
   path between L2 and the other ground pours.
8. Decoupling within 5mm of the pin it serves, each with its own ground via.
9. USB D+/D- as a 90 ohm ±10% differential pair, length-matched, no stubs,
   short, with ground return vias at every via transition and ground copper
   alongside (HDG §1.4.8).
10. LoRa antenna feed as 50 ohm microstrip, see LoRa radio.
11. Series resistors for USB and SPI clocks placed close to the module.
12. No components under the OLED panel outline.
13. All components on the top side (single-sided assembly).
14. Three fiducials on the top side, asymmetric. M2 mounting holes, plated,
    connected to GND. The enclosure model follows the board, not the reverse.
15. Silkscreen: pin 1 on every polarised part. Top: `THEOROS ${REVISION}`
    (follows the title block) and ΘΕΩΡΟΣ above the GNSS module, "ANTENNA
    BEFORE TX" pointing at J401, and a line under the OLED panel that is only
    visible with the panel removed. Bottom: an owl made as a solder-mask
    opening over the GND pour (gold with ENIG; every via inside stays tented)
    and the motto "ΟΡΩ ΚΑΙ ΑΓΓΕΛΛΩ / I SEE AND I REPORT". Item 13 applies to
    components only; the bottom side carries artwork but no parts.

### Routing notes (rev V1.0, routing completed 2026-10-07)

Signals use L1 and L4 only; L2 and L3 carry no traces. Every pad, via and
pour island on GND reaches the L2 plane.

- **USB corner:** the microSD bus runs on L4 directly under USB D+ (y 106.9
  to 108.2 mm, 0.22 mm gaps), with D- below it. This leaves room for a GND
  via beside USBLC6 pin 2 and for D201 (TVS) GND to drop straight to a via
  between its pad and the LoRa SPI lines. The three LoRa lines NSS, MISO
  and MOSI turn east 1.4 mm higher than before to make room for that via.
- **USB pair:** full speed only. D+ and D- differ by about 2 mm in length,
  with 2 and 4 vias. This is acceptable at 12 Mbit/s. Impedance on the
  Lion stackup is checked in the Stackup section.
- **Placement changes made during routing:**
  - C306 (DNP) moved beside R305.
  - R302 moved up 1.2 mm, then 0.4 mm east (J502 rework below).
- **J502 rework (2026-10-08):** the panel FPC lands mirrored on J502 (panel
  pin n on J502 pin 31-n, see Display), so the J502 nets were re-mapped in
  the schematic (J502 symbol mirrored) and the OLED support row re-placed
  west to east in pad order: C504/C505 (charge pump, horizontal), C506
  (VBAT), C507 (VDD), R505/R507/R506 (RES/SCL/SDA pull-ups), R508 (IREF),
  C509 (VCOMH), C508 (VCC). C305 (DNP) is now horizontal at x 93.4.
  - VBAT reaches the regulator network through an L4 jumper from a via north
    of pin 25 to TP501.
  - RES and SDA arrive on L4 at vias north of the connector; SCL on L1.
  - +3V3 pins 20/22 share one plane via; the GND pins get vias north of the
    connector or pad-to-pad bridges.
  - DRC after the rework: same 4 silk-edge warnings as before, 0 unconnected.
- **In-pad vias:** removed from R205, R505, R204, R507 and U301 pin 7.
  - One remains, on R504.2 (SD_DAT1 pull-up), where no legal spot exists.
    Ask Lion for a filled via there, or accept it on a pull-up.
  - The R301.1 via ring overlaps the pad edge by 0.07 mm; its hole is
    outside the pad.
- **GND stitching:** 6 mm staggered grid plus a 4 mm edge fence, 0.8/0.4 mm
  vias. Small GND pads with no room for thermal spokes use a solid zone
  connection.

## Fab and assembly (Lion Circuits)

| Parameter | Value |
|---|---|
| Layers | 4 |
| Thickness | 1.6mm |
| Copper | 1oz outer, 0.5oz inner |
| Surface finish | ENIG (flat pads for the LGA GNSS module and fine-pitch FPC connector) |
| Min trace / space (design rule) | 0.2mm / 0.2mm |
| Signal trace | 0.2mm, or impedance width where controlled |
| Power trace | 0.5-0.8mm |
| Via | 0.4mm drill / 0.8mm pad |
| Assembly | Top side only, turnkey PCBA |

Lion Circuits' published limits (Make in India service): 2 or 4 layers, 1oz,
6/6mil (0.152mm) min trace/space, 0.35mm min drill, 0.152mm annular ring,
12mil min via spacing. Their Rush service is tighter at 8/8mil and 0.4mm
drill. The rules above meet all of their services, so the design can be
ordered on any of them without changes.

To confirm with Lion Circuits before ordering: ENIG availability on the MII
service, inner copper weight, 4-layer stackup, impedance control, MSL 4 dry
storage and baking for the GNSS module, and that their reflow profile meets
the SAM-M10Q limits. X-ray is optional: u-blox requires optical inspection
only.

Assembly notes passed to Lion Circuits with the order:

- SAM-M10Q: MSL 4, reflow limits and restrictions as in the GNSS assembly
  section. No conformal coating on the board.
- No-clean flux, no washing.
- OLED panel not assembled; the ZIF connector is.
- DNP parts as marked in the BOM.

Every BOM line carries manufacturer, manufacturer part number and at least one
distributor part number available in India (Mouser, DigiKey, element14 or
LCSC), so Lion Circuits can source it turnkey.

## WiFi

Now effectively free on USB power. Worth enabling for NTP time sync, a web page
to download logs without removing the card, and OTA firmware updates. OTA
matters more than usual on a board with no programming header.

Requires the module antenna keep-out above to be honoured exactly.

## Firmware consequence

`gps_logger.ino` targets the ATmega328P and does not carry over. TinyGPSPlus and
SdFat both run on ESP32-S3, but pin constants, the two SPI bus instances, the
I2C display and USB console handling all differ. Rewrite reusing the logic.

Requires Arduino ESP32 core 2.0.5 or later, or ESP-IDF 4.4+, for S3 support.

Firmware must enforce:

- WiFi and LoRa transmit never overlap (see supply requirement).
- SD sync after every record.
- Radio at 866MHz. +20dBm limited to 1% duty cycle, otherwise ≤+17dBm.
- LoRa RESET (GPIO48) only high-Z or low, never driven high.
- GNSS reset by UBX-CFG-RST; GPIO7 RESET_N only for recovery, open drain.
- GPIO15 (TIMEPULSE) input, no pull-down.
- OLED: RES# pulse after power-up, then the panel's initialisation sequence
  with internal DC/DC values (8Dh 14h, 81h CFh, D9h F1h, AFh).
- GPIO39 and GPIO40 left unconfigured.

## Open items

- J502 pin order: panel pin 1 is on the left in the front view (OLED
  datasheet drawing 1.4.1) and lands on J502 contact 30, so panel pin n mates
  J502 pin 31-n. Fixed 2026-10-08 (schematic re-map plus re-placement and
  re-routing, see Routing notes).
- TYPE-C-31-M-12: KiCad's `USB_C_Receptacle_HRO_TYPE-C-31-M-12` was checked
  against HRO's recommended layout (LCSC C165948 drawing). Signal pads,
  5.78 mm NPTH and 8.64 mm shell slots match. The power pads sit 0.05 mm
  wider than the drawing, within the 0.6 mm pad. OK.
- Confirm Lion Circuits can source SAM-M10Q, RFM95W-868S2, AP7361C-33E-13,
  USB-C receptacle and microSD socket turnkey, or whether any must be
  supplied by us.
- C403 (Seiko CPH3225A) is rated only to +60°C, below vehicle cabin
  extremes; it ages faster when hot but does not affect anything else if it
  fails. Lion Circuits listed it out of stock (2026-10-08): order it from
  DigiKey (8692444) and supply it, or ask Lion to source it.
- PTS810: the KiCad footprint matches C&K's recommended layout exactly
  (1.05 x 0.65 mm pads, 3.1/5.2 and 1.5/2.8 mm spans). OK.
- Panel operating range is -30 to +70°C; enclosure design must keep it out of
  direct sun.
- Set the radio to 866MHz, not the 868MHz library default. India's delicensed
  allocation is 865-867MHz.
- Breadboard the full system on a DevKit before ordering boards (layout is
  done, but it is still the cheapest test of the firmware), using a SAM-M10Q
  breakout and an RFM95W adapter board so the tested parts match the design.
- Confirm whether GPS and LoRa ever transmit simultaneously, or whether firmware
  holds off transmit until a fix is acquired.
