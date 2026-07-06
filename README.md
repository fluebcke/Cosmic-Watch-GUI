# Cosmic-Watch-GUI

A real-time muon detector system built on Raspberry Pi Pico with a modern PyQt6 GUI. Monitor cosmic rays, analyze muon events, and measure detector coincidences with simultaneous two-detector mode.

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.6.1-green.svg)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

Cosmic Watch is a complete muon detection and analysis platform that turns your Raspberry Pi Pico into a precision cosmic ray detector. With live rate monitoring, event logging, and coincidence detection between two detectors, it's perfect for physics experiments, education, and research.

### Key Features

- **Live Detection**: Real-time muon event streaming from one or two detectors
- **Dual-Detector Mode**: Hardware coincidence mode with live visualization and analysis.
- **Live Analytics**: Instantaneous rate monitoring with configurable time windows
- **Event Logging**: Tab-separated data export with full event metadata
- **Statistical Analysis**: Mean/median rates, Poisson uncertainty bands, and decay fitting
- **Hardware Control**: Threshold adjustment, detector naming, and remote reboot
- **Portable**: Works on Mac, Linux; minimal Python dependencies

---

## Quick Start

### Requirements
- **Hardware**: 1–2 Raspberry Pi Pico boards with muon detector firmware
- **Software**: Python 3.9+, PyQt6, pyqtgraph, numpy, scipy, pyserial
- **OS**: macOS or Linux (Ubuntu, Debian, Fedora, etc.)

### Installation (5 minutes)

```bash
# Clone the repository
git clone https://github.com/fluebcke/Cosmic-Watch-GUI.git
cd Cosmic-Watch-GUI

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the program
python3 main.py
```

**First time?** See the [Setup Guide](docs/SETUP_GUIDE.md) for detailed instructions with screenshots.

---

## Usage

### Single Detector Mode
1. Plug in one Pico detector via USB
2. Launch Cosmic Watch: `python3 main.py`
3. Select the port in the startup dialog and click "Connect"
4. Watch live rates, event log, and ADC spectra in real-time

### Coincidence Mode (Two Detectors)
1. Plug in both Picos (different USB ports)
2. Launch Cosmic Watch: `python3 main.py`
3. Select "Coincidence Mode" and choose both ports
4. Monitor master, slave, and coincident events simultaneously
5. Analyze muon lifetime using decay curves

### Controls

| Feature | How |
|---------|-----|
| **Threshold** | Slider in toolbar (20–1000 mV) |
| **Live Window** | Settings → "Live rate window" (1–60 s) |
| **Logging** | "Start Logging" button → event file saved |
| **Restart** | "Restart" button → reset counters |
| **Export** | Event Log tab → "Export CSV..." |

---

## Project Structure

```
cosmic-watch/
├── detector/                 # Hardware interface layer
│   ├── detector.py          # SerialReader, DetectorReader class
│   ├── parser.py            # Event parsing (MuonEvent dataclass)
│   ├── analysis.py          # Rolling rate windows, ADC stats
│   ├── protocol.py          # Firmware command/response definitions
│   └── coincidence.py       # Two-detector event matching
├── gui/                     # PyQt6 graphical interface
│   ├── main_window.py       # Main app window, tab setup
│   ├── plots.py             # Rate and ADC histogram panels
│   ├── coinc_tab.py         # Coincidence-mode dashboard
│   ├── lifetime_tab.py      # Muon lifetime analysis (optional)
│   ├── toolbar.py           # Control panel
│   ├── statusbar.py         # Connection status display
│   ├── widgets.py           # Reusable panels (stats bar, event log)
│   └── settings.py          # Configuration dialog
├── session/                 # Multi-detector session management
│   └── coincidence.py       # CoincidenceSession class
├── main.py                  # Entry point, startup dialog
├── requirements.txt         # Python dependencies
└── docs/                    # Documentation
    ├── SETUP_GUIDE.md       # Installation & setup
    ├── IMPLEMENTATION_PLAN.md  # Feature roadmap
    └── ...
```

---

## Features

### Current Features
- [x] Single-detector event streaming  
- [x] Dual-detector coincidence mode  
- [x] Live rate monitoring (configurable windows)  
- [x] ADC histogram with threshold overlay  
- [x] Event logging (TSV format with metadata)  
- [x] CSV export  
- [x] Real-time statistics (count, rate, mean ADC, standard deviation)  
- [x] Threshold control (firmware command)  
- [x] Detector naming via firmware  
- [x] Connection status & error reporting  
- [x] Bayesian uncertainty band

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    PyQt6 Main Window                     │
├──────────────────────────────────────────────────────────┤
│  Toolbar │ StatusBar │ Tabs: Live | Coincidence | Log    │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐    ┌────▼────┐  ┌─────▼──────┐
   │RatePanel│    │ADCHist  │  │EventLogPanel│
   └────▲────┘    └────▲────┘  └─────▲──────┘
        │              │              │
        │    ┌─────────┴──────────┐   │
        │    │ CoincidenceSession │   │
        │    └─────────┬──────────┘   │
        │              │              │
   ┌────┴──────────────┼──────────────┴────┐
   │                   │                    │
┌──▼───────┐      ┌──▼──────┐       ┌─────▼────┐
│  Master  │      │  Slave  │       │SessionLog │
│ (Pico 1) │      │ (Pico 2)│       │ (File)    │
└──────────┘      └─────────┘       └───────────┘
     ↓                  ↓
  USB/Serial       USB/Serial
```

**Data Flow:**
1. Picos send event lines over USB serial (independent)
2. DetectorReader threads parse events → queue
3. CoincidenceSession (if active) matches events by PC timestamp
4. GUI drains queues and dispatches to plot/table panels
5. SessionLogger writes matched events to TSV file

---

## Hardware Setup

### Single Detector
```
Pico 1 (Master)  ←USB→  Laptop
```

### Dual Detector (Coincidence)
```
Pico 2 (Slave) ←TRS→ Pico 1 (Master)  ←USB→  Laptop    
```

**Requirements per Pico:**
- Raspberry Pi Pico W or standard Pico
- Scintillation detector (e.g., plastic scintillator + PMT)
- Signal conditioning to 3.3V logic
- Firmware: Muon detector code (custom `.ino` for Arduino IDE)

**Firmware communication:**
- Baud rate: 115200
- Protocol: Tab-separated event lines
- Commands: `THRESHOLD:X`, `NAME:Y`, `START`, `RESET`, etc.

See firmware repository (link in [Contributing](#contributing)) for hardware schematic.

---

## Configuration

### Settings Dialog
Access via toolbar: **Settings** button

| Setting | Range | Default | Effect |
|---------|-------|---------|--------|
| **Author name** | 0–17 chars | "(unset)" | Sent to firmware, saved in log metadata |
| **Log directory** | Any path | `./measurements` | Where event files are saved |
| **Live rate window** | 1–60 s | 5 s | Sliding window for instantaneous rate plot |
| **Rate windows** | 5–86400 s | 30, 60, 300 s | Per-tile windows in stats bar |

### Command Line
Currently none. All settings via GUI (future: config file support).

---

## Output Files

### Event Log
**Location:** `measurements/YYYY-MM-DD_HH-MM-SS/detector_log.txt`

**Format:** Tab-separated with metadata header
```
# Detector log started : 2026-07-06 12:34:56.789
# Port                 : /dev/ttyUSB0  Baud: 115200
# Author               : Alice
# Threshold            : 150 mV
# Columns              : pc_timestamp  evNum  picoTimeMs  adcAtEvent  rateOverall  threshold_mV
pc_timestamp          evNum  picoTimeMs  adcAtEvent  rateOverall  threshold_mV
2026-07-06 12:35:01.234  1      1234      512         0.5000      150
2026-07-06 12:35:02.456  2      2456      498         0.6667      150
...
```

**Import in Python:**
```python
import pandas as pd
df = pd.read_csv('detector_log.txt', sep='\t', comment='#')
print(df[['evNum', 'adcAtEvent', 'rateOverall']])
```

### CSV Export
Manual export from "Event Log" tab → "Export CSV..." button.
```
evNum,time_ms,adc,rate,threshold
1,1234,512,0.5000,150
2,2456,498,0.6667,150
```

---

## Troubleshooting

### "Port not found"
```bash
# Mac
ls /dev/tty.*

# Linux
ls /dev/ttyUSB*
```
If nothing shows, your Pico isn't plugged in or needs firmware.

### "ModuleNotFoundError: No module named 'PyQt6'"
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "Permission denied" on Linux
```bash
sudo usermod -a -G dialout $USER
# Log out and log back in
```

**More issues?** See [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

---

## Development

### Contributing
We welcome contributions! Areas for improvement:
- Hardware schematic & firmware code (separate repo)
- Fitting algorithms (muon lifetime, angular distribution)
- Data analysis tools (time-of-flight, spectrum fitting)
- Performance optimizations
- Documentation improvements

**Getting started:**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-thing`)
3. Make your changes and test locally
4. Submit a pull request with a clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Running Tests
```bash
python3 -m pytest tests/
```

### Building Documentation
```bash
# Requires mkdocs
pip install mkdocs
mkdocs serve
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| **PyQt6** | 6.6.1 | GUI framework |
| **numpy** | 1.24.3 | Array math (event processing) |
| **pyqtgraph** | 0.13.3 | Live plotting |
| **pyserial** | 3.5 | USB/serial communication |
| **scipy** | 1.11.1 | Statistics (Bayesian CI, decay fitting) |

See `requirements.txt` for full list with pinned versions.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

In summary: you're free to use, modify, and distribute this software, provided you include the license notice.

---

## Acknowledgments

Built with:
- **PyQt6** for the interface
- **pyqtgraph** for real-time plotting
- **Raspberry Pi Pico** as the detector platform
- **scipy** for statistical rigor
