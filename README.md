# Battery Arbitrage for Home Assistant

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)
[![hassfest](https://github.com/planckus/ha-battery-arbitrage/actions/workflows/validate.yaml/badge.svg)](https://github.com/planckus/ha-battery-arbitrage/actions/workflows/validate.yaml)

Automatically decide **when to export** stored energy from your solar + battery system and **when to grid-charge** your battery — all driven by a 24-hour price forecast, solar production forecast, and a self-learning household-load model.

Built for a **FoxESS H3 inverter** controlled via [foxess_modbus](https://github.com/nathanmarlor/foxess_modbus) and **EVCC** for grid-charge coordination, with electricity prices from [Strømligning](https://www.stromligning.dk/) via the HA integration.

---

## Features

| Feature | Description |
|---------|-------------|
| 📈 **Price-aware export** | Exports to grid only when the spot price minus deduction clears your minimum threshold |
| ⚡ **Grid arbitrage** | Buys cheap grid electricity into the battery when the price is in the lowest 25th percentile of the next 24 hours |
| ☀️ **Solar-aware** | Reads Solcast solar forecast via EVCC; skips grid charging if solar will fill the battery anyway |
| 🏠 **Load prediction** | 2-hour rolling average + 28-day baseline; vacation detection prevents over-exporting when nobody is home |
| 🌡️ **Temperature learning** | Learns real-world charge rates for 5 battery temperature buckets; improves time-to-charge estimates over time |
| 🔧 **HACS-installable** | One-click install/uninstall; clean entity teardown on removal |
| 🇩🇰 **Danish & English UI** | Full translations for both languages |

---

## Prerequisites

Before installing, make sure you have:

- **[foxess_modbus](https://github.com/nathanmarlor/foxess_modbus)** — Modbus integration for FoxESS inverters  
- **[EVCC](https://evcc.io/)** running locally (tested on v0.130+), with the HA add-on or standalone  
- **[Strømligning](https://stromligning.dk/)** HA integration — provides `sensor.stromligning_spotprice_ex_vat`  
- Home Assistant **2024.1** or newer

---

## Installation via HACS

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add `https://github.com/planckus/ha-battery-arbitrage` as an **Integration**
3. Search for *Battery Arbitrage* and click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** and search for *Battery Arbitrage*
6. Follow the 5-step setup wizard

---

## Manual Installation

```bash
# From your HA config directory
mkdir -p custom_components
git clone https://github.com/planckus/ha-battery-arbitrage.git
cp -r ha-battery-arbitrage/custom_components/battery_arbitrage custom_components/
# Restart Home Assistant
```

---

## Setup Wizard

The config flow walks you through five steps:

1. **EVCC connection** — URL tested live; battery capacity auto-filled
2. **FoxESS entities** — work-mode select, force-charge and force-discharge numbers; auto-detected from known entity IDs
3. **Electricity price** — Strømligning spot-price entity (excl. VAT)
4. **Battery & trading parameters** — capacity, floor/ceiling SoC, efficiency, spread thresholds, forecast horizon
5. **Dashboard** (optional) — link an existing Lovelace dashboard

After setup, all parameters are editable via **Configure** on the integration card.

---

## How It Works

Every 5 minutes the coordinator:

1. Fetches EVCC state (home power, PV power, EV charging mode) and the solar + grid price forecasts
2. Updates the load history ring buffer and runs vacation detection
3. Checks the three conditions for **exporting**:
   - Export price (spot − 0.01 DKK deduction) ≥ minimum threshold, **or** spread over 24h min ≥ arbitrage threshold
   - Truly exportable kWh (above floor SoC, minus predicted load, minus solar) ≥ 0.5 kWh
   - EV is not in *fast-charge* mode
4. If not exporting, checks the three conditions for **grid charging**:
   - Next-slot grid price ≤ 25th percentile of 24h window
   - Room in battery ≥ 0.5 kWh
   - Solar won't fill the battery in the next 6 hours
5. Executes: sets FoxESS work mode + export limit register + EVCC battery mode

### Mode Transitions

| Mode | FoxESS work mode | EVCC battery mode | Export gate |
|------|-----------------|-------------------|-------------|
| Normal | Self Use | normal | open |
| Exporting | Force Discharge | hold | open |
| Grid charging | Self Use | charge | open |

---

## Entities

### Sensors
| Entity | Description |
|--------|-------------|
| `sensor.battery_arbitrage_mode` | Current operating mode |
| `sensor.battery_arbitrage_mode_reason` | Human-readable reason |
| `sensor.battery_arbitrage_export_price` | Current export price (DKK/kWh) |
| `sensor.battery_arbitrage_grid_spread` | Price spread vs 24h min |
| `sensor.battery_arbitrage_price_min/max/mean/p25/p75` | 24h grid price statistics |
| `sensor.battery_arbitrage_price_next_slot` | Next 15-min grid price |
| `sensor.battery_arbitrage_solar_forecast_24h` | Solcast 24h forecast (kWh) |
| `sensor.battery_arbitrage_solar_forecast_6h` | Solcast 6h forecast (kWh) |
| `sensor.battery_arbitrage_predicted_load_24h` | Predicted house load (kWh) |
| `sensor.battery_arbitrage_exportable_kwh` | Truly exportable energy (kWh) |
| `sensor.battery_arbitrage_importable_kwh` | Room for grid charging (kWh) |
| `sensor.battery_arbitrage_load_2h_avg` | Rolling 2h house load (kW) |
| `sensor.battery_arbitrage_load_28d_avg` | 28-day baseline load (kW) |
| `sensor.battery_arbitrage_learned_charge_rate` | Current-bucket learned rate (kW) |
| `sensor.battery_arbitrage_time_to_charge` | Estimated hours to full charge |
| `sensor.battery_arbitrage_cell_temp_low` | Lowest BMS cell temperature |
| `sensor.battery_arbitrage_learned_rate_*` | Learned rate per temperature bucket |

### Binary Sensors
| Entity | Description |
|--------|-------------|
| `binary_sensor.battery_arbitrage_should_export` | Export conditions currently met |
| `binary_sensor.battery_arbitrage_should_grid_charge` | Grid-charge conditions met |
| `binary_sensor.battery_arbitrage_vacation_mode` | Home presence detected |
| `binary_sensor.battery_arbitrage_solar_will_fill` | Solar sufficient to fill battery |
| `binary_sensor.battery_arbitrage_ev_connected` | EV plugged in |

### Number Entities (editable)
Five `number.battery_arbitrage_charge_rate_*` entities — one per temperature bucket.  
These are auto-learned but can be manually overridden.

### Switch
`switch.battery_arbitrage_enabled` — Pause/resume the entire system without removing the integration. Turning it off immediately restores normal inverter operation.

---

## Services

| Service | Description |
|---------|-------------|
| `battery_arbitrage.force_export` | Immediately activate Force Discharge |
| `battery_arbitrage.force_grid_charge` | Immediately activate grid charging |
| `battery_arbitrage.restore_normal` | Cancel and restore Self-Use mode |
| `battery_arbitrage.reset_learning` | Clear all learned data |

---

## Removal

1. Go to **Settings → Devices & Services**, find *Battery Arbitrage*, click **Delete**
2. The integration will restore the inverter to Self-Use mode and EVCC to normal before removing itself
3. Persistent storage (learned rates + load history) is automatically deleted

---

## Configuration Defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| Battery floor SoC | 50% | Never export below this |
| Battery max SoC | 100% | Grid-charge ceiling |
| Round-trip efficiency | 92% | Used to calculate exportable kWh |
| Min spread (arbitrage) | 1.0 DKK/kWh | Min sell-vs-buy spread to grid-arbitrage |
| Min solar export price | 0.50 DKK/kWh | Min price to export solar surplus |
| Forecast horizon | 24 hours | Price and solar window |
| Export deduction | 0.01 DKK/kWh | Electricity company network fee (hardcoded) |

---

## Contributing

Pull requests welcome. Please run `pytest tests/` and ensure `hassfest` passes before submitting.

---

## License

MIT — see [LICENSE](LICENSE)
