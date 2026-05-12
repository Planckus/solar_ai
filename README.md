# Solar AI for Home Assistant

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)

Automatically decide **when to export** stored energy from your solar + battery system and **when to grid-charge** your battery — all driven by a 24-hour price forecast, a self-calibrating solar production forecast, and a self-learning household-load model.

Built for a **FoxESS H3 inverter** controlled via [foxess_modbus](https://github.com/nathanmarlor/foxess_modbus) and **EVCC** for EV charging coordination, with electricity prices from [Strømligning](https://www.stromligning.dk/) via the HA integration.

---

## Features

| Feature | Description |
|---------|-------------|
| 📈 **Price-aware export** | Exports to grid only when the spot price clears your minimum threshold |
| ⚡ **Grid arbitrage** | Buys cheap grid electricity into the battery when the price is in the lowest 25th percentile of the next 24 hours |
| ☀️ **Self-calibrating solar forecast** | Compares Solcast predictions with actual EVCC PV production every 5 minutes; builds a rolling correction factor so decisions use realistic numbers |
| 🏠 **Load prediction** | 2-hour rolling average + 28-day baseline; vacation detection prevents over-exporting when nobody is home |
| 🌡️ **Temperature learning** | Learns real-world charge rates for 5 battery temperature buckets; improves time-to-charge estimates over time |
| 🚗 **EVCC co-existence** | Detects when EVCC is managing the battery for EV charging and steps aside; never fights EVCC over battery control |
| 🔒 **Safe by default** | Arbitrage switch is OFF on first install — turn it on after the system has had a few days to learn |
| 🇩🇰 **Danish & English UI** | Full translations for both languages |

---

## Prerequisites

- **[foxess_modbus](https://github.com/nathanmarlor/foxess_modbus)** — Modbus integration for FoxESS inverters
- **[EVCC](https://evcc.io/)** running locally (tested on v0.130+)
- **[Strømligning](https://stromligning.dk/)** HA integration — provides `sensor.stromligning_spotprice_ex_vat`
- Home Assistant **2024.1** or newer

---

## Installation

### Option A — deploy script (recommended)

```bash
git clone https://github.com/Planckus/solar_ai.git
cd solar_ai

pip install websockets PyYAML

# Edit INSTALL_DEFAULTS at the top of deploy.py if your entity IDs differ, then:
python3 deploy.py --install
```

The script deploys the files, restarts HA, runs the config flow automatically, and creates the dashboard.

### Option B — HACS manual repository

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add `https://github.com/Planckus/solar_ai` as an **Integration**
3. Search for *Solar AI* and click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** → search *Solar AI*
6. Follow the 5-step setup wizard

### Option C — manual copy

```bash
cp -r custom_components/battery_arbitrage /config/custom_components/
# Restart Home Assistant, then add the integration via the UI
```

---

## Setup Wizard

The config flow walks through five steps:

1. **EVCC connection** — URL tested live; battery capacity auto-filled
2. **FoxESS entities** — work-mode select, force-charge and force-discharge numbers; auto-detected
3. **Electricity price** — Strømligning spot-price entity (excl. VAT)
4. **Battery & trading parameters** — capacity, floor/ceiling SoC, efficiency, spread thresholds
5. **Dashboard** — links the Solar AI Lovelace dashboard

---

## How It Works

Every 5 minutes the coordinator:

1. Fetches EVCC state (home power, PV power, EV charging mode, battery mode) and the solar + grid price forecasts
2. Updates the solar accuracy tracker, load history and vacation detection
3. Checks EVCC co-existence — steps aside if EVCC is managing the battery for EV charging
4. Checks **export** conditions: price threshold met, enough exportable kWh, EV not fast-charging
5. Checks **grid charge** conditions: cheap next-slot price, room in battery, solar won't fill it
6. Executes: sets FoxESS work mode + export limit register + EVCC battery mode

### Mode Transitions

| Mode | FoxESS work mode | Export limit | EVCC battery mode |
|------|-----------------|-------------|-------------------|
| Normal | Self Use | 10 000 W | normal |
| Exporting | Feed-in First | 10 000 W | hold |
| Grid charging | Force Charge | 0 W | hold |

### Solar Accuracy Calibration

Every 5-minute tick the integration records `(Solcast forecast W, actual EVCC pvPower W)` for the current slot. After 12+ daytime samples it calculates a rolling median ratio and applies it as a correction factor (clamped 0.30–1.50) to all forecast values used in decisions. The raw and adjusted forecasts are both exposed as sensors.

---

## Dashboard

A full Lovelace dashboard is deployed automatically at `/battery-arbitrage`, showing:
- On/off control + current mode + decision reason
- Live electricity prices
- Solar forecast (raw vs adjusted) + accuracy factor
- Battery state, exportable/importable energy
- EVCC battery mode + EV charging status
- Load model (2h avg, 28d avg, predicted 24h)
- Learned charge rates per temperature bucket
- FoxESS live state (work mode, feed-in, load power)

---

## Deploy Script

```bash
python3 deploy.py                  # redeploy files + restart + push dashboard
python3 deploy.py --install        # full fresh install (files + config flow + dashboard)
python3 deploy.py --uninstall      # remove everything, restore HA to original state
python3 deploy.py --dashboard-only # push dashboard changes only (no restart)
```

---

## Services

| Service | Description |
|---------|-------------|
| `battery_arbitrage.force_export` | Immediately activate Feed-in First export |
| `battery_arbitrage.force_grid_charge` | Immediately activate Force Charge |
| `battery_arbitrage.restore_normal` | Cancel and restore Self-Use mode |
| `battery_arbitrage.reset_learning` | Clear all learned data and solar accuracy samples |

---

## Configuration Defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| Battery floor SoC | 50% | Never export below this |
| Battery max SoC | 100% | Grid-charge ceiling |
| Round-trip efficiency | 92% | Used to calculate exportable kWh |
| Min spread (arbitrage) | 1.0 DKK/kWh | Min sell-vs-buy spread to trigger grid arbitrage |
| Min solar export price | 0.50 DKK/kWh | Min price to export solar surplus |
| Forecast horizon | 24 hours | Price and solar window |
| Export deduction | 0.01 DKK/kWh | Network fee deducted by electricity company |

---

## Uninstall

```bash
python3 deploy.py --uninstall
```

Or manually: **Settings → Devices & Services → Solar AI → Delete**. The integration restores the FoxESS inverter to Self-Use mode, EVCC to normal, and re-enables any previously disabled automations before removing itself.

---

## License

MIT — see [LICENSE](LICENSE)
