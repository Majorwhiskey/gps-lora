# Datasheets

Reference documents used for schematic capture and layout. PDFs are kept
locally in this folder and are not committed, because vendor datasheets are
copyrighted and not licensed for redistribution. Download each from the
manufacturer's website and save it here under the file name given.

## Required before schematic capture

| # | Part | Document | Vendor | File name |
|---|---|---|---|---|
| 1 | ESP32-S3-WROOM-1-N8 | ESP32-S3-WROOM-1 / WROOM-1U datasheet | Espressif | `esp32-s3-wroom-1_datasheet.pdf` |
| 2 | ESP32-S3 | ESP32-S3 series datasheet | Espressif | `esp32-s3_datasheet.pdf` |
| 3 | ESP32-S3 | ESP32-S3 hardware design guidelines | Espressif | `esp32-s3_hardware_design_guidelines.pdf` |
| 4 | SAM-M10Q | SAM-M10Q data sheet | u-blox | `sam-m10q_datasheet.pdf` |
| 5 | SAM-M10Q | SAM-M10Q integration manual | u-blox | `sam-m10q_integration_manual.pdf` |
| 6 | RFM95W-868S2 | RFM95W/96W/98W datasheet | HopeRF | `rfm95w_datasheet.pdf` |
| 7 | SX1276 | SX1276/77/78/79 datasheet | Semtech | `sx1276_datasheet.pdf` |
| 8 | AP7361C-33E-13 | AP7361C datasheet | Diodes Inc. | `ap7361c_datasheet.pdf` |
| 9 | USBLC6-2SC6 | USBLC6-2 datasheet | STMicroelectronics | `usblc6-2_datasheet.pdf` |
| 10 | TYPE-C-31-M-12 | USB-C receptacle drawing | HRO (Korean Hroparts) | `type-c-31-m-12_drawing.pdf` |
| 11 | SSD1306 | SSD1306 controller datasheet | Solomon Systech | `ssd1306_datasheet.pdf` |

## Required once the part is selected

| # | Part | Document | Notes |
|---|---|---|---|
| 12 | OLED panel: EastRising ER-OLED0.96-1.1W | ER-OLED0.96-1 series datasheet, file `er-oled0.96-1_datasheet.pdf` | Selected |
| 13 | ZIF connector: Hirose FH12-30S-0.5SH(55) | Hirose FH12 series datasheet | Selected; datasheet needed |
| 14 | microSD socket: Hirose DM3AT-SF-PEJM5 | Socket drawing | Selected |
| 15 | Polyfuse: Littelfuse 1206L075THYR | 1206L series datasheet | Selected |
| 16 | u.FL receptacle | Hirose U.FL-R-SMT-1 drawing | |
| 17 | Tactile switch: C&K PTS810 SJM 250 SMTR LFS | PTS810 drawing | Selected |
| 18 | 100uF bulk capacitor | Datasheet with DC-bias curve | Polymer or 1210 X5R ceramic |

## Footprint references

| # | Item | Document |
|---|---|---|
| 19 | Tag-Connect TC2030-NL | TC2030 footprint drawing (Tag-Connect) |

## Holdup and backup options (DNP in v1, needed before layout)

| # | Part | Document |
|---|---|---|
| 20 | Schottky diode, ≤0.45V at 600mA | Datasheet |
| 21 | 2200uF holdup capacitor | Datasheet (footprint size) |
| 22 | GNSS backup supercap: Elna DSK-3R3H224U-HL | DSK series datasheet |

## Added during schematic capture

| # | Part | Document |
|---|---|---|
| 24 | TI TLV75801PDBV (OLED VBAT LDO) | TLV758P datasheet |
| 25 | Littelfuse SMF5.0A (VBUS TVS) | SMF series datasheet |
| 26 | Microchip MCP120T-300I/TT (EN supervisor) | MCP120 datasheet |

## Fabricator

| # | Item | Source |
|---|---|---|
| 23 | 4-layer 1.6mm stackup and capability sheet | Lion Circuits (sales@lioncircuits.com) |

## Status

| # | Status |
|---|---|
| 1-9, 11 | Downloaded and checked against the spec (2026-10-05) |
| 10 | Only a low-resolution image (`images.jpeg`); PDF drawing still needed |
| 12 | Downloaded and checked (2026-10-05) |
| 13 | Part selected, datasheet needed |
| 14-23 | Pending part selection |

Note on #6: the RFM95W datasheet text calls the reset pin "pin 7 (NRESET)" in
§7.2. On the module, pin 6 is RESET and pin 7 is DIO5 (Table 2).
