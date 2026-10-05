# gps-lora

USB-powered GPS logger with LoRa telemetry, built around the ESP32-S3.

Logs GPS fixes to a microSD card at 1 Hz, shows status on an OLED, and sends
position over 866 MHz LoRa. WiFi provides NTP time, log download and OTA
updates. Designed in KiCad as a 4-layer, fully machine-assembled board
(Lion Circuits PCBA, Bangalore, single-sided).

> **Status: schematic in progress (v1).** Not yet fabricated or tested. Do not
> order boards from this repository until a tagged release exists.

<!-- Replace with a 3D render once layout is done: docs/images/render.png -->

## Features

- ESP32-S3-WROOM-1-N8 with native USB (no USB-UART bridge)
- USB-C power and data, 5 V 1 A
- u-blox SAM-M10Q GNSS module with integrated antenna, UART and PPS
- microSD logging on a dedicated SPI bus
- RFM95W (SX1276) 868 MHz-band LoRa radio on a second SPI bus, u.FL antenna
- Bare SSD1306 128x64 OLED panel on I2C, FPC connector
- Low-dropout 3.3 V linear regulator (AP7361C)
- Tag-Connect footprint for UART0 console, EN and GPIO0
- 4-layer stackup with solid ground plane and impedance-controlled RF and USB traces

## Block diagram

```mermaid
flowchart LR
    USB[USB-C] -->|VBUS| FUSE[Polyfuse 750 mA] --> LDO[AP7361C 3.3 V]
    USB <-->|D+ / D-| ESD[USBLC6-2] <--> MCU
    LDO -->|3V3| MCU[ESP32-S3-WROOM-1]
    MCU <-->|UART1| GPS[SAM-M10Q GNSS]
    MCU <-->|SPI2| SD[microSD]
    MCU <-->|SPI3| LORA[RFM95W 868] --> ANT[u.FL to SMA]
    MCU <-->|I2C| OLED[SSD1306 panel]
```

## Repository layout

| Path | Contents |
|---|---|
| `hardware/` | KiCad 10 project (schematic, PCB) |
| `hardware/lib/` | Project-local symbols, footprints and 3D models |
| `docs/` | Design specification and images |
| `firmware/` | ESP32-S3 firmware (not started) |
| `production/` | Fabrication outputs (Gerbers, drill, BOM, CPL) per release |

## Documentation

- [PCB design specification](docs/PCB_DESIGN.md): pin assignment, power
  budget, layout rules and design decisions.

## Opening the design

Requires [KiCad](https://www.kicad.org/) 10.0 or later. Open
`hardware/gps-lora.kicad_pro`. All non-standard symbols, footprints and 3D
models are in `hardware/lib/`, so no external libraries are needed.

## Regulatory note

The LoRa radio is configured for 865–867 MHz, India's delicensed band.
Users elsewhere must set the frequency, power and duty cycle allowed in
their region.

## License

Hardware design files are licensed under the
[CERN Open Hardware Licence Version 2 – Permissive](LICENSE)
(CERN-OHL-P-2.0). Firmware will be licensed separately when added.
