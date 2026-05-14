# Solar AI for FoxESS

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)

> **An intelligent Home Assistant integration that autonomously manages your FoxESS battery — buying cheap grid electricity, selling at peak prices, protecting your circuit breakers, and learning your household's patterns over time.**

---

## What it does

Solar AI sits between your FoxESS inverter, your EV charger (EVCC), and the electricity spot market. Every 5 minutes it:

1. Reads live spot prices, solar forecasts, battery state, grid draw, and EV charge power
2. Runs its decision model — export? grid-charge? do nothing?
3. Acts — setting the FoxESS work mode, force-charge power, and EVCC battery mode
4. Learns — refining its understanding of charge rates, solar accuracy, EV habits, and house load

All thresholds are adjustable via live dashboard sliders. No YAML editing, no restarts needed.

---

## Features

### ⚡ Core Arbitrage Engine
- **Grid charging** — charges the battery when the spot price is in the cheapest 25th percentile of the next 24 hours, then uses or exports that energy when prices rise
- **Battery export** — activates FoxESS *Feed-in First* mode to push battery energy to the grid, but **only when the current price is at or above the 75th percentile** of the day — reserving stored energy for true evening peaks, not mediocre mid-day prices
- **Minimum spread threshold** — configurable minimum price difference (sell − cheapest buy) before arbitrage triggers. Live slider on the dashboard (0.10–3.00 DKK/kWh)

### 🌞 Solar-Aware Decision Making
- **Solcast integration** (via EVCC) — uses your roof's 24-hour solar forecast
- **Solar accuracy learning** — compares actual PV output to Solcast forecasts over a rolling 4-day window and applies a learned correction factor (0.3–1.5×), so decisions use realistic rather than optimistic numbers
- **Net solar for battery** — subtracts predicted house load from the solar forecast to compute the true surplus available for the battery. Grid charging is automatically skipped when solar will fill the battery anyway

### 🏠 House Load Model
- **2-hour rolling average** — captures current consumption trends
- **28-day rolling average** — establishes a long-term baseline
- **Vacation / low-load detection** — if consumption drops below 25% of the 28-day baseline for 4+ hours, Solar AI enters vacation mode and applies a more conservative load estimate

### 🚗 EV-Aware Scheduling (EVCC)
- **Real charging detection** — uses actual EV charge power (> 3 000 W) rather than "connected" state, so scheduled or idle sessions don't block battery operations
- **Hourly EV pattern learning** — exponential smoothing learns when your EV typically charges, hour by hour (~8-day memory). Grid charging is skipped during hours where the EV charges ≥ 70% of the time
- **EVCC battery mode coordination** — sets EVCC battery mode to *hold* during export/charging and restores *normal* when done. Respects EVCC if it has independently taken control of the battery

### 🔋 Self-Calibrating Battery Model
- **Auto-detected round-trip efficiency** — reads FoxESS lifetime charge/discharge totals (`discharge ÷ charge`) and uses the real measured efficiency instead of a manual estimate. Falls back to the configured value until 100 kWh of lifetime data is available.
- **Learned battery capacity** — during Force Charge cycles, measures energy in vs SoC rise per tick to learn the true usable capacity. Activates after 20 samples (a few charge cycles); configured value is the fallback until then.
- Both values are exposed as sensors so you can watch calibration progress in real time.

### 🌡️ Temperature-Adaptive Charging
- **7 temperature buckets** — learned charge rates across `< 0 °C`, `0–5 °C`, `6–15 °C`, `16–21 °C`, `21–35 °C`, `35–50 °C`, `> 50 °C`
- **Automatic calibration** — during Force Charge cycles the system records actual charge power and updates the learned rate at the 90th percentile (neither noisy max nor underestimating average)
- **Manual override** — each bucket is exposed as an editable number entity

### 🗓️ Seasonal Mode
- **28-day rolling daily solar average** — switches between *summer* and *winter* mode based on observed production (threshold: 6 kWh/day)
- Defaults to *winter* (conservative) until 7+ days of data are in
- Adapts gradually — no hard-coded calendar dates

### 🔌 Grid Overcurrent Protection
- Reads live grid import power from EVCC every 5 minutes
- Calculates available headroom: `limit − 0.5 kW safety margin − current grid draw`
- Automatically caps the battery charge rate to stay within your circuit breaker limit
- Grid charging is skipped entirely if headroom drops below 0.3 kW
- **Configurable limit** — enter your breaker capacity directly on the dashboard (5–63 kW, default 17 kW)

### 💰 Savings Tracker
- **Actual savings** — revenue from battery export + estimated value of cheap grid charging
- **Missed savings** — estimated opportunity cost when the system is switched off
- Available for: today / 7 days / 30 days
- Stored in a 90-day rolling log that survives HA restarts

### 🎛️ Live Dashboard Controls
All key thresholds are adjustable from the dashboard without restarting HA:

| Control | Range | Default |
|---------|-------|---------|
| Battery floor SoC (export minimum) | 10–100 % | 50 % |
| Battery max SoC (grid charge ceiling) | 10–100 % | 100 % |
| Minimum arbitrage spread | 0.10–3.00 DKK/kWh | 1.00 |
| Grid import limit | 5–63 kW | 17 kW |

---

## Prerequisites

You need all of the following already working in Home Assistant:

| Component | Purpose | Link |
|-----------|---------|------|
| FoxESS Modbus integration | Read battery SoC, temperature, power; set work mode and charge power | [GitHub](https://github.com/nathanmarlor/foxess_modbus) |
| EVCC | Solar forecast (Solcast), live grid power, EV charge power, battery mode API | [evcc.io](https://evcc.io) |
| Strømligning | Electricity spot prices (Denmark) | [stromligning.dk](https://www.stromligning.dk) |
| Solcast | Solar production forecast — connected to EVCC | [solcast.com](https://solcast.com) |

### Default FoxESS Modbus entity IDs

Solar AI auto-detects these during setup. If your names differ, you can override them in the config flow:

```
sensor.foxessmodbus_battery_soc_1
sensor.foxessmodbus_bms_cell_temp_low_1
sensor.foxessmodbus_battery_charge
sensor.foxessmodbus_battery_discharge
sensor.foxessmodbus_load_power
sensor.foxessmodbus_feed_in
select.foxessmodbus_work_mode
number.foxessmodbus_force_charge_power
number.foxessmodbus_force_discharge_power
```

---

## Installation

### 1. Copy the integration

Copy the `custom_components/battery_arbitrage` folder into your HA config directory:

```
/homeassistant/custom_components/battery_arbitrage/
```

Via HACS: add this repository as a custom repository and install from there.

### 2. Restart Home Assistant

### 3. Add the integration

**Settings → Devices & Services → Add Integration → Solar AI**

The setup wizard walks you through:
1. **EVCC URL** — e.g. `http://your-ha-ip:7070`
2. **FoxESS entities** — auto-detected; override if your names differ
3. **Strømligning entity** — select your spot price sensor (excl. VAT)
4. **Battery & trading parameters** — capacity, efficiency, initial thresholds
5. **Dashboard** — optionally link an existing Lovelace dashboard

### 4. Import the dashboard

Import `dashboard/battery_arbitrage_dashboard.yaml` via **Settings → Dashboards → Add Dashboard → From YAML**.

### 5. Start monitoring, then enable

The system starts in **monitoring-only mode** (switch off). Watch the *Decision reason* sensor for a few days to see what Solar AI *would* do. When you're satisfied, flip the **Arbitrage enabled** switch.

---

## How the decision loop works

```
Every 5 minutes:

1. Fetch EVCC state     → grid power, solar forecast, EV charge power, battery mode
2. Fetch grid tariff    → 24h spot price array → min, max, mean, p25, p75
3. Read FoxESS          → SoC, cell temp, charge/discharge power, work mode
4. Update models        → load history, solar accuracy, EV hourly probability, daily solar kWh
5. Compute headroom     → grid limit − 0.5 kW − current grid import
6. Make decision:

   EXPORT?       price ≥ p75
             AND spread ≥ threshold
             AND exportable kWh ≥ 0.5
             AND SoC > floor
             AND no EV charging (now/minpv mode)
             AND EVCC not managing battery

   GRID CHARGE?  next-slot price (incl. VAT) ≤ p25 (incl. VAT)
             AND solar won't fill battery
             AND importable kWh ≥ 0.5
             AND headroom ≥ 0.3 kW
             AND EV unlikely to charge this hour

7. Act if enabled       → set FoxESS work mode, capped charge power, EVCC mode
8. Track savings        → accumulate actual/missed DKK into daily log
9. Save to storage      → learned rates, load history, EV probabilities, solar history
```

---

## Setting up with Claude Code

If you use [Claude Code](https://claude.ai/code), it can dramatically speed up the process of adapting Solar AI to your own Home Assistant installation. This section shows practical ways to use it as a hands-on configuration tool — not as a replacement for understanding the system, but as a fast assistant for the tedious parts.

### Finding your entity IDs

Solar AI needs to know the exact entity IDs for your FoxESS Modbus sensors, your spot price sensor, and your EVCC URL. Claude Code can query your live HA instance and find them for you:

> *"List all entities from the foxess_modbus integration in my Home Assistant"*

> *"Find the Strømligning or Nordpool spot price sensor in my HA entity registry"*

> *"What entity IDs does the battery_arbitrage integration expose right now?"*

Claude Code can call the Home Assistant REST API or WebSocket directly and return a filtered list — far faster than scrolling through Settings → Developer Tools → States.

### Adapting for a different inverter

Solar AI is built around FoxESS Modbus. If you have a different inverter (SolarEdge, Sungrow, Huawei, SMA, etc.) the work mode control is in `coordinator.py`. Point Claude Code at the file:

> *"I have a SolarEdge inverter. Read coordinator.py and tell me what I need to change to replace the FoxESS work mode and force-charge logic with SolarEdge Modbus entities"*

It will identify the three or four places where `select.foxessmodbus_work_mode`, `number.foxessmodbus_force_charge_power`, and `number.foxessmodbus_force_discharge_power` are called, and propose equivalents for your hardware.

### Adapting for a different price source

The integration currently reads spot prices from Strømligning (Denmark). For Nordpool, Tibber, Entsoe, or any other HA price sensor:

> *"I use the Nordpool integration. Read coordinator.py and sensor.py and show me what to change so Solar AI reads prices from sensor.nordpool_kwh_dk2_dkk_3 instead of Strømligning"*

The price array format may differ — Claude Code can inspect both integrations and write the adapter.

### Debugging unexpected decisions

If Solar AI does something unexpected (charges when it shouldn't, doesn't export when prices are high), Claude Code can pull the live decision state and explain it:

> *"Read the current state of all battery_arbitrage sensors in my HA and explain why the system decided not to export right now"*

> *"Show me the last 30 minutes of logbook entries for the battery_arbitrage integration"*

The `sensor.*_begrundelse_for_tilstand` (Decision reason) sensor already gives a plain-language explanation, but Claude Code can cross-reference it with raw price data, SoC, and EV state to go deeper.

### General tips

- Always run in **monitoring mode** (switch off) for a few days first — Claude Code can help you read the decision reason sensor and explain what the system *would* have done before you let it act.
- Use `battery_arbitrage.reset_learning` via Developer Tools → Services after any major configuration change, so the learned charge rates and load model restart from a clean slate.
- The `coordinator.py` file is the single source of truth for all decision logic. If something doesn't make sense, that's the file to read and the file to change.

---

## Sensors reference

### Decision & control
| Entity | Description |
|--------|-------------|
| `switch.*_arbitrage_aktiv` | Master on/off switch |
| `sensor.*_driftstilstand` | Current mode: `normal` / `exporting` / `grid_charging` / `disabled` |
| `sensor.*_begrundelse_for_tilstand` | Plain-language reason for the current decision |

### Price sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_eksportpris` | Current export price (DKK/kWh) |
| `sensor.*_net_arbitrage_spread` | Spread: export price − 24 h minimum |
| `sensor.*_24h_prisminimum/maksimum/gennemsnit` | 24 h price statistics |
| `sensor.*_24h_pris_25/75_percentil` | Quartile thresholds used for decisions |
| `sensor.*_naeste_slots_pris` | Price for the next 30-minute slot |

### Solar sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_solcelle_prognose_24h/6h` | Raw Solcast forecast (kWh) |
| `sensor.*_solcelle_prognose_24h/6h_justeret` | Accuracy-corrected forecast |
| `sensor.*_solcelle_prognose_nojagtighed` | Rolling accuracy factor (%) |
| `sensor.*_netto_sol_til_batteri_24h` | Net solar surplus after house load (kWh) |
| `sensor.*_sol_gennemsnit_28_dage` | 28-day average daily solar production (kWh) |
| `sensor.*_saesontilstand` | `summer` or `winter` |

### Battery sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_eksporterbar_energi` | kWh available for export above floor SoC |
| `sensor.*_importerbar_energi` | kWh room to charge below max SoC |
| `sensor.*_tid_til_fuld_opladning` | Hours to reach max SoC at current rate |
| `sensor.*_batteritemperatur_laveste_celle` | Lowest cell temperature |
| `sensor.*_laert_opladningshastighed_*` | Learned charge rate per temperature bucket (kW) |

### Grid sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_net_importeffekt` | Live grid import power (kW) |
| `sensor.*_net_raaderum` | Headroom before breaker limit (kW) |

### EV & load sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_ev_opladningssandsynlighed_denne_time` | Learned EV charge probability this hour (%) |
| `sensor.*_husstand_forbrug_2h_gennemsnit` | 2 h average house load (kW) |
| `sensor.*_husstand_forbrug_28_dages_gennemsnit` | 28-day average house load (kW) |
| `sensor.*_forudsagt_husstand_forbrug_24h` | Predicted house consumption today (kWh) |

### Savings sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_faktisk_besparelse_i_dag/7_dage/30_dage` | Actual savings earned (DKK) |
| `sensor.*_forpasset_besparelse_i_dag/7_dage/30_dage` | Missed savings while disabled (DKK) |

---

## Configuration reference

All settings are available in **Settings → Devices & Services → Solar AI → Configure**, or live via dashboard number entities:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Battery capacity | 11.52 kWh | Fallback usable capacity — replaced automatically by the learned value after ~20 Force Charge samples |
| Round-trip efficiency | 92 % | Fallback efficiency — replaced automatically by the FoxESS lifetime totals once 100+ kWh have been cycled |
| Forecast horizon | 24 h | Hours of price data to analyse |
| Min SoC during export | 50 % | Battery will not export below this SoC |
| Max SoC for grid charge | 100 % | Battery will not grid-charge above this SoC (configurabel)|
| Min arbitrage spread | 1.00 DKK/kWh | Minimum sell−buy spread to trigger arbitrage |
| Min solar export price | 0.50 DKK/kWh | Minimum price to export solar surplus |
| Grid import limit | 17 kW | Circuit breaker capacity |

---

## Services

| Service | Description |
|---------|-------------|
| `battery_arbitrage.force_export` | Immediately activate Feed-in First regardless of prices |
| `battery_arbitrage.force_grid_charge` | Immediately start grid charging |
| `battery_arbitrage.restore_normal` | Cancel active export or charging, return to Self-Use |
| `battery_arbitrage.reset_learning` | Clear all learned rates, load history, and solar samples |

---

## Known limitations

- **Denmark-focused** — built around DKK/kWh spot prices from Strømligning. Other markets need a different price entity and currency unit.
- **FoxESS Modbus required** — work mode control uses FoxESS-specific entities. Other inverters need code changes in `coordinator.py`.
- **EVCC required** — solar forecasts and grid power readings come from EVCC's API.
- **Learning period** — the system works best after 1–2 weeks of data. During the first few days it uses conservative defaults for charge rates and EV patterns.
- **Buy-side pricing** ✅ **(FIXED)** — sell side uses the excl. VAT spot price (what you receive from the grid). Buy side applies 25% Danish VAT on top, so spread calculations reflect what you actually pay vs. what you receive. Grid tariffs beyond VAT are not yet modelled separately.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

## License

MIT — use freely, adapt for your own setup.
