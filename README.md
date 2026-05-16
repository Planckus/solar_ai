# Solar AI for FoxESS

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)

> **An intelligent Home Assistant integration that autonomously manages your FoxESS battery — buying cheap grid electricity, selling at peak prices, protecting your circuit breakers, and learning your household's patterns over time.**

---

## ✨ New in v0.21.0 — Day-ahead optimizer

The decision engine has been rebuilt from the ground up. Instead of reactive threshold comparisons, Solar AI now runs a **full 24-hour dynamic programming optimizer** every time prices refresh:

- **Globally optimal multi-cycle planning** — finds the best combination of charge and export windows across all 24 future hours simultaneously, rather than checking one slot at a time
- **Per-hour house load profile** — the optimizer uses a learned 24-slot daily load profile (kW per hour, ~8-day EMA) to accurately estimate battery drain per slot, replacing the flat 24h average
- **EV solar shading model** — the optimizer accounts for how much of the solar forecast will be consumed by EV charging (learned max rate × hourly probability), giving the battery an accurate net-solar estimate per hour
- **Direct spot price feed** — prices now come from [Energi Data Service](https://api.energidataservice.dk) (Nord Pool `DayAheadPrices`, 15-min resolution) instead of EVCC, fixing the zero-rate issue and removing a dependency on EVCC's tariff endpoint

See [CHANGELOG.md](CHANGELOG.md) for full details.

---

## What it does

Solar AI sits between your FoxESS inverter, your EV charger (EVCC), and the electricity spot market. Every hour it:

1. **Fetches day-ahead spot prices** directly from Energi Data Service (Nord Pool) and runs a 24-hour DP optimizer to plan the best charge and export windows for the rest of the day
2. **Every 5 minutes**: reads live battery state, solar production, grid draw, and EV charge power, then follows the plan — setting the FoxESS work mode, force-charge power, and EVCC battery mode
3. **Learns** — refining its understanding of charge rates, solar accuracy, EV habits, and per-hour house load demand

All thresholds are adjustable via live dashboard controls. No YAML editing, no restarts needed.

---

## Features

### ⚡ Core Arbitrage Engine

Solar AI plans the day's charge and export schedule using a **backward-induction dynamic programming optimizer**, refreshed every hour when new spot prices arrive:

- **Day-ahead DP optimizer** — models 24 hourly slots with battery SoC as state (0–100 % at 1 % resolution). For each slot it evaluates three actions — CHARGE, EXPORT, IDLE — and finds the globally optimal sequence that maximises net revenue (export earnings minus charging cost) over the full horizon, given efficiency losses, house demand, solar production, and EV charging patterns
- **Multi-cycle awareness** — correctly handles scenarios like "charge at 02h, export at 11h, charge again at 14h, export again at 19h" that simple threshold logic cannot plan
- **Grid charging** — charges the battery in slots the optimizer identifies as optimal buy windows, subject to the full all-in cost stack: (spot + markup + DSO nettarif + Energinet tariff + elafgift) × VAT
- **Battery export** — activates FoxESS *Feed-in First* mode in slots the optimizer identifies as peak sell windows
- **Minimum spread threshold** — the optimizer only recommends export when `sell_price − cheapest_recharge_cost / efficiency ≥ min_spread`, ensuring the round-trip is profitable after losses. Configurable live slider on the dashboard (0.10–3.00 DKK/kWh)
- **Minimum export price floor** — configurable floor below which Solar AI will never export. When the price is at or below the floor, the FoxESS export limit register is set to 25 W — blocking both battery export *and* solar panel export. Default 0.00 blocks only negative/zero prices. Works even when the arbitrage switch is off
- **Export power cap** — optionally cap the battery's discharge rate during export (0–10 kW). Useful if your grid connection or feed-in contract has a power limit. Default 0 = no cap

### 🚫 Negative Price Guard & Export Floor
- **All export blocked** (25 W limit) when the net export price is at or below your configured floor — this stops both battery discharge and solar panel export at unprofitable prices
- **Forced grid charge** when the buy price drops to or below zero — if the grid is paying you to consume electricity, Solar AI charges the battery regardless of the spread threshold or EV schedule
- **Always active** — the export floor is enforced on every poll tick, even when the arbitrage switch is off

### 💶 Full Price Stack — Buy & Sell Side

Solar AI computes accurate buy and sell prices using all relevant cost components:

**Buy-side (what you pay per kWh from the grid):**
```
(spot price + retailer markup + DSO network tariff + Energinet tariff + elafgift) × VAT
```

**Sell-side (what you receive per kWh exported):**
```
spot price − sell-side fee − indfødningstarif (DSO + Energinet, auto-fetched)
```

All components are live-configurable number entities in the dashboard:

| Entity | Default | Description |
|--------|---------|-------------|
| Buy-side VAT | 25 % | VAT applied to grid electricity purchases |
| Sell-side fee | 0.00 DKK/kWh | Per-kWh cut taken by your electricity seller on exports |
| Spot price markup | 0.00 DKK/kWh | Retailer's add-on on top of spot price (handelstillæg / abonnementstillæg) |
| Elafgift | 0.01 DKK/kWh | Danish government electricity duty |
| Min. export price | 0.00 DKK/kWh | Floor below which Solar AI will not export |

### 🌐 Hourly Network Tariff Integration

Solar AI automatically fetches your grid operator's hourly time-of-use tariffs from the **Energi Data Service DatahubPricelist API**, refreshed once daily:

- **DSO nettarif C time** — the time-varying hourly network tariff from your local grid operator (e.g. Dinel/Jutland/Fyn), fetched by GLN number
- **Energinet transmission tariff** — system and transmission charges from the national TSO (code `40000`)
- **Auto-fetched indfødningstarif** — Solar AI also retrieves your DSO's feed-in production tariff (e.g. Nettarif indfødning C, code `TC_IND_03`) and the Energinet production tariff (code `40010`) and deducts them automatically from the export price. No manual entry needed — they update daily
- Select your DSO from the **Grid operator (DSO)** dropdown in *Settings → Integrations → Solar AI → Configure*. Dinel (Jutland/Fyn) is available now; more DSOs will be added over time
- The `Grid tariff this hour` sensor shows the combined DSO + Energinet + elafgift for the current hour
- The `Feed-in tariff` sensor shows the combined auto-fetched indfødningstarif (DSO + Energinet) currently being deducted from your export price

### 📊 24h Price Chart & Tonight's Plan

- **24h price chart** — a markdown card in the dashboard renders a live table of all upcoming hourly buy and sell prices, colour-coded by quartile (🟢 cheap / 🟡 normal / 🔴 expensive), with ⚡ and 💰 markers showing which hours are planned for charging and export
- **Tonight's plan** — a `todays_plan` sensor shows the full list of planned charge and export hours in plain text, plus a visual grid view in the dashboard. The plan only includes export hours where the price exceeds your configured minimum floor

### 🔔 Mode-Change Notifications
- Optional persistent notifications in HA whenever Solar AI changes operating mode (export → normal, grid charging → normal, etc.)
- Includes the reason for the transition (e.g. "Exporting: price 1.23 ≥ p75 1.10 DKK/kWh")
- Toggle on/off with the **Notifications** switch in the dashboard — no restart needed

### 🌞 Solar-Aware Decision Making
- **Solcast integration** (via EVCC) — uses your roof's 24-hour solar forecast
- **Live solar production** — exposes EVCC's real-time PV output as a `Solar production (live)` sensor (kW)
- **Solar accuracy learning** — compares actual PV output to Solcast forecasts over a rolling 4-day window and applies a learned correction factor (0.3–1.5×), so decisions use realistic rather than optimistic numbers
- **Net solar for battery** — subtracts predicted house load from the solar forecast to compute the true surplus available for the battery. Grid charging is automatically skipped when solar will fill the battery anyway

### 🏠 House Load Model
- **Per-hour daily profile** — a 24-slot learned profile (kW per hour of day, ~8-day EMA per slot) that the optimizer uses to forecast demand for each future hour. Adapts gradually to changes in household routine. Unobserved hours fall back to the short-term rolling average at startup
- **2-hour rolling average** — captures current consumption trends
- **28-day rolling average** — establishes a long-term baseline
- **Vacation / low-load detection** — if consumption drops below 25% of the 28-day baseline for 4+ hours, Solar AI enters vacation mode and applies a more conservative load estimate
- **Outlier-resistant learning** — each learning tick applies a two-layer guard: physical ceiling at `grid_max_kw` and a soft cap at 5× the current estimate (once model is warm), preventing sensor spikes from distorting the profile

### 🚗 EV-Aware Scheduling (EVCC)
- **Real charging detection** — uses actual EV charge power (> 3 000 W) rather than "connected" state, so scheduled or idle sessions don't block battery operations
- **Hourly EV pattern learning** — exponential smoothing learns when your EV typically charges, hour by hour (~8-day memory). Grid charging is skipped during hours where the EV charges ≥ 70 % of the time
- **EV max charge rate learning** — learns the car's peak AC charge rate (~20-sample EMA) from full-speed sessions only (≥ 80 % of current learned max). Solar-throttled summer sessions are excluded so the estimate stays accurate year-round. The optimizer uses this value to compute expected EV solar consumption per hour, giving the battery an accurate net-surplus forecast
- **Battery-bypass model** — the optimizer knows that the EV never charges from the battery (EVCC setting). Solar allocated to the EV is correctly subtracted from what is available to charge the battery, not from battery discharge
- **EV on Solar sensor** — binary sensor that activates when the EV is charging in EVCC's `pv` mode with real solar power flowing (> 3 000 W)
- **EVCC battery mode coordination** — sets EVCC battery mode to *hold* during export/charging and restores *normal* when done. Respects EVCC if it has independently taken control of the battery

### 🔋 Self-Calibrating Battery Model
- **Auto-detected round-trip efficiency** — reads FoxESS lifetime charge/discharge totals (`discharge ÷ charge`) and uses the real measured efficiency instead of a manual estimate. Falls back to the configured value until 100 kWh of lifetime data is available
- **Learned battery capacity** — during Force Charge cycles, measures energy in vs SoC rise per tick to learn the true usable capacity. Activates after 20 samples (a few charge cycles); configured value is the fallback until then
- Both values are exposed as sensors so you can watch calibration progress in real time

### 🌡️ Temperature-Adaptive Charging
- **7 temperature buckets** — learned charge rates across `< 0 °C`, `0–5 °C`, `6–15 °C`, `16–21 °C`, `21–35 °C`, `35–50 °C`, `> 50 °C`
- **Automatic calibration** — during Force Charge cycles the system records actual charge power and updates the learned rate at the 90th percentile (neither noisy max nor underestimating average)
- **Manual override** — each bucket is exposed as an editable number entity

### 🗓️ Seasonal Mode
- **28-day rolling daily solar average** — switches between *summer* and *winter* mode based on observed production (threshold: 6 kWh/day)
- Defaults to *winter* (conservative) until 7+ days of data are in
- Adapts gradually — no hard-coded calendar dates

### 🔌 Grid Overcurrent Protection
- Reads live grid import power from EVCC every fast-poll tick
- Calculates available headroom: `limit − 0.5 kW safety margin − current grid draw`
- Automatically caps the battery charge rate to stay within your circuit breaker limit
- Grid charging is skipped entirely if headroom drops below 0.3 kW
- **Configurable limit** — enter your breaker capacity directly on the dashboard (5–63 kW, default 17 kW)

### 💰 Savings Tracker
- **Actual savings** — revenue from battery export + estimated value of cheap grid charging
- **Missed savings** — estimated opportunity cost when the system is switched off
- Available for: today / 7 days / 30 days
- Stored in a 90-day rolling log that survives HA restarts
- Correctly excludes hours blocked by the minimum export price floor from both actual and missed calculations

### ⏱️ Split-Rate Polling
- **Live state** (grid power, solar production, EV status, battery mode) is fetched on every fast-poll tick
- **Price and tariff data** is refreshed at most once per hour, matching the rate at which DSO prices actually change — no unnecessary API hammering
- **Configurable poll interval** — set the live-data interval in *Settings → Integrations → Solar AI → Configure* (10–300 seconds, default 30 s)

### 🎛️ Live Dashboard Controls

All key thresholds are adjustable from the dashboard without restarting HA:

| Control | Range | Default |
|---------|-------|---------|
| Battery floor SoC (export minimum) | 10–100 % | 50 % |
| Battery max SoC (grid charge ceiling) | 10–100 % | 100 % |
| Minimum arbitrage spread | 0.10–3.00 DKK/kWh | 1.00 |
| Minimum export price floor | 0.00–2.00 DKK/kWh | 0.00 |
| Export power cap | 0–10 kW | 0 (no cap) |
| Grid import limit | 5–63 kW | 17 kW |
| Buy-side VAT | 0–50 % | 25 % |
| Sell-side fee | 0.00–0.50 DKK/kWh | 0.00 |
| Spot price markup | 0.00–0.50 DKK/kWh | 0.00 |
| Elafgift | 0.00–3.00 DKK/kWh | 0.01 |
| Notifications | On / Off | Off |

---

## Prerequisites

You need the following already working in Home Assistant:

| Component | Required | Purpose | Link |
|-----------|----------|---------|------|
| FoxESS Modbus integration | ✅ Required | Read battery SoC, temperature, power; set work mode and charge power | [GitHub](https://github.com/nathanmarlor/foxess_modbus) |
| EVCC | ✅ Required | Live grid power, EV charge power, battery mode API. (Solar forecast is optional from v0.23.0 — see below) | [evcc.io](https://evcc.io) |
| Solar forecast source | ✅ Required (one of) | One of: **EVCC → Solcast** (default) or **Forecast.Solar** (native HA integration). Configured in the setup wizard. | [Solcast](https://solcast.com) / [Forecast.Solar HA docs](https://www.home-assistant.io/integrations/forecast_solar/) |
| Spot price entity | ⚙️ Optional | Any HA sensor exposing the current spot price excl. VAT in DKK/kWh (e.g. [Strømligning](https://www.stromligning.dk), Tibber). If omitted, Solar AI reads the live spot price from Energi Data Service automatically — the same feed used by the optimizer | — |

### Optional dashboard dependencies (HACS)

The bundled dashboard YAML uses these custom Lovelace cards. Install them via HACS → Frontend before importing the dashboard, or substitute with built-in cards if you prefer not to add dependencies:

| Card | Required for | Link |
|------|--------------|------|
| Mushroom Cards | The status chips, large tiles and headers on the Oversigt tab and section titles in Indstillinger | [GitHub](https://github.com/piitaya/lovelace-mushroom) |
| ApexCharts Card | Time-series price/SoC overlays (optional polish — built-in `history-graph` works as a fallback) | [GitHub](https://github.com/RomRider/apexcharts-card) |

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
3. **Spot price entity** *(optional)* — select any HA sensor exposing hourly spot price excl. VAT in DKK/kWh. Leave blank and Solar AI will source the live price from Energi Data Service instead
4. **Battery & trading parameters** — capacity, efficiency, initial thresholds, DSO, currency
5. **Dashboard** — optionally link an existing Lovelace dashboard

### 4. Import the dashboard

Two dashboard files are included:

| File | Language |
|------|----------|
| `dashboard/dashboard_da.yaml` | Danish |
| `dashboard/dashboard_en.yaml` | English |

Import via **Settings → Dashboards → Add Dashboard → From YAML**.

### 5. Set your electricity cost parameters

In the dashboard, set the **Priskonfiguration / Price Configuration** card values to match your electricity contract:

- **Elafgift** — the Danish government electricity duty (check your bill)
- **Spotpris-tillæg / Spot markup** — your retailer's per-kWh add-on (handelstillæg / abonnementstillæg)
- **Moms / VAT** — leave at 25% for Denmark
- **Salgsgebyr / Sell-side fee** — your retailer's per-kWh cut on exports (if any)
- **Min. eksportpris / Min. export price** — optional floor below which Solar AI won't export (default 0.00)

The **indfødningstarif** (DSO + Energinet feed-in production tariff) is fetched and deducted automatically — no manual entry needed.

### 6. Start monitoring, then enable

The system starts in **monitoring-only mode** (switch off). Watch the *Decision reason* sensor for a few days to see what Solar AI *would* do. When you're satisfied, flip the **Arbitrage enabled** switch.

---

## How the decision loop works

### Hourly — optimizer run (triggered by price refresh)

```
Once per hour (when spot prices refresh):

1. Fetch prices         → Energi Data Service Elspotprices (Nord Pool day-ahead, DK2)
                          Falls back to EVCC /api/tariff/grid if EDS is unreachable
                          buy-side: (spot + markup + DSO tariff + Energinet tariff + elafgift) × VAT
                          sell-side: spot − sell-side fee − indfødningstarif (auto-fetched daily)

2. Run DP optimizer     → 24-hour backward-induction dynamic programming
                          State:   battery SoC (0–100 %, integer steps = 101 states)
                          Actions: CHARGE | EXPORT | IDLE per hourly slot
                          Inputs:  per-hour buy/sell prices, learned house load profile (24 slots),
                                   solar forecast per hour, EV hourly charge probability × learned max rate,
                                   charge/discharge efficiency, floor SoC, max SoC
                          EXPORT only allowed when:
                            sell_price > min_export_price floor
                            AND sell_price − cheapest_recharge / efficiency ≥ min_spread
                          CHARGE blocked for hours where EV typically charges (≥ 70 % probability)
                          Output:  ordered plan — {hour, action, expected SoC, buy, sell} for each slot

3. Store plan           → drives decisions for the next 60 minutes
```

### Every 5 minutes — decision execution

```
1. Fetch EVCC state     → grid power, solar forecast, EV charge power, battery mode
2. Read FoxESS          → SoC, cell temp, charge/discharge power, work mode
3. Update models        → house load hourly profile, EV max rate, load history,
                          solar accuracy, EV hourly probability, daily solar kWh
4. Compute headroom     → grid limit − 0.5 kW − current grid import

5. Look up optimizer plan for the current hour:

   EXPORT?       optimizer plan says EXPORT for this hour
             AND sell price > min export price floor          ← hard floor, always applied
             AND exportable kWh ≥ 0.5
             AND SoC > floor SoC
             AND EV not actively charging (now/minpv mode)   ← safety guard
             AND EVCC not managing battery independently

   GRID CHARGE?  optimizer plan says CHARGE for this hour
             AND solar won't fill battery on its own
             AND importable kWh ≥ 0.5
             AND grid headroom ≥ 0.3 kW
             AND EV not likely charging this hour

   FORCED CHARGE if buy price ≤ 0 (grid pays you to consume — overrides all other checks)

   FALLBACK      if no optimizer plan yet (first startup hour):
                 reactive logic — export if sell ≥ p75, charge if buy ≤ p25

6. Act if enabled       → set FoxESS work mode, capped charge power, EVCC mode
                          optionally cap discharge power to max_export_kw
7. Export limit (always)→ write FoxESS export limit register on every tick:
                            grid charging  → 0 W
                            price ≤ floor  → 25 W  (blocks solar + battery export)
                            price > floor  → 10 000 W
8. Notify (optional)    → persistent HA notification on every mode transition
9. Track savings        → accumulate actual/missed DKK into daily log
10. Save to storage     → learned rates, load history, EV probabilities, solar history
```

---

## Sensors reference

### Decision & control
| Entity | Description |
|--------|-------------|
| `switch.*_arbitrage_aktiv` | Master on/off switch |
| `switch.*_notifikationer_ved_tilstandsskift` | Toggle mode-change notifications |
| `sensor.*_driftstilstand` | Current mode: `normal` / `exporting` / `grid_charging` / `disabled` |
| `sensor.*_begrundelse_for_tilstand` | Plain-language reason for the current decision |

### Price sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_eksportpris` | Current net export price (DKK/kWh); never < 0 |
| `sensor.*_net_arbitrage_spread` | Spread: export price − 24 h minimum buy price |
| `sensor.*_24h_prisminimum/maksimum/gennemsnit` | 24 h price statistics |
| `sensor.*_24h_pris_25/75_percentil` | Quartile thresholds used for decisions |
| `sensor.*_naeste_slots_pris` | Price for the next 30-minute slot |
| `sensor.*_nettarif_denne_time` | Total grid tariff this hour: DSO + Energinet + elafgift (DKK/kWh) |
| `sensor.*_indfodningstarif_dso_energinet` | Auto-fetched feed-in production tariff currently deducted from export price (DKK/kWh) |
| `sensor.*_minimum_eksportpris` | Configured minimum export price floor, displayed at 2 decimal places (DKK/kWh) |
| `sensor.*_24h_priskort` | 24 h price chart sensor; `slots` attribute contains list of `{h, buy, sell}` dicts |
| `sensor.*_dagens_plan` | Tonight's plan in plain text; `charge_hours` and `export_hours` attributes |

### Number entities (live-configurable)
| Entity | Range | Description |
|--------|-------|-------------|
| `number.*_minimum_arbitrage_spread` | 0.10–3.00 DKK/kWh | Spread threshold before arbitrage triggers |
| `number.*_minimum_eksportpris_*` | 0.00–2.00 DKK/kWh | Minimum export price floor (editable) |
| `number.*_eksporteffekt_graense_*` | 0–10 kW | Max battery discharge power during export (0 = no cap) |
| `number.*_salgsgebyr_pr_kwh` | 0.00–0.50 DKK/kWh | Sell-side fee |
| `number.*_spotpris_tillaeg_*` | 0.00–0.50 DKK/kWh | Retailer spot price markup |
| `number.*_elafgift_dkk_kwh` | 0.00–3.00 DKK/kWh | Elafgift |
| `number.*_moms_pa_kob` | 0–50 % | VAT on purchases |
| `number.*_minimum_soc_eksport` | 10–100 % | Battery floor SoC for export |
| `number.*_maksimum_soc_netopladning` | 10–100 % | Battery max SoC for grid charging |
| `number.*_net_importgraense` | 5–63 kW | Circuit breaker capacity |

### Solar sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_solcelleproduktion_live` | Real-time PV output from EVCC (kW) |
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
| `sensor.*_laert_batterikapacitet` | Learned usable capacity (kWh); active after ~20 samples |
| `sensor.*_auto_detekteret_effektivitet` | Measured round-trip efficiency from FoxESS lifetime totals (%) |
| `sensor.*_kapacitets_laeringseksempler` | Number of capacity learning samples collected |

### Grid sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_net_importeffekt` | Live grid import power (kW) |
| `sensor.*_net_raaderum` | Headroom before breaker limit (kW) |

### EV & load sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_ev_opladningssandsynlighed_denne_time` | Learned EV charge probability this hour (%) |
| `sensor.*_ev_maks_opladningshastighed_laert` | Learned EV maximum AC charge rate (kW); season-independent; `profile_kw` attribute unused |
| `sensor.*_husstand_forbrug_2h_gennemsnit` | 2 h average house load (kW) |
| `sensor.*_husstand_forbrug_28_dages_gennemsnit` | 28-day average house load (kW) |
| `sensor.*_huslast_laert_denne_time` | Learned house load for the current hour of day (kW); `profile_kw` attribute = full 24-slot array |
| `sensor.*_forudsagt_husstand_forbrug_24h` | Predicted house consumption today (kWh) |
| `binary_sensor.*_ev_oplader_solenergi` | EV actively charging on solar power (pv mode, > 3 kW) |

### Savings sensors
| Entity | Description |
|--------|-------------|
| `sensor.*_faktisk_besparelse_i_dag/7_dage/30_dage` | Actual savings earned (DKK) |
| `sensor.*_forpasset_besparelse_i_dag/7_dage/30_dage` | Missed savings while disabled (DKK) |

---

## Configuration reference

All settings are available in **Settings → Devices & Services → Solar AI → Configure**, or live via dashboard number entities:

| Parameter | Default | Configurable live | Description |
|-----------|---------|------------------|-------------|
| Battery capacity | 11.52 kWh | No (config flow) | Fallback — auto-replaced by learned value after ~20 Force Charge samples |
| Round-trip efficiency | 92 % | No (config flow) | Fallback — auto-replaced by FoxESS lifetime totals once 100+ kWh cycled |
| Forecast horizon | 24 h | No (config flow) | Hours of price data to analyse |
| Min SoC during export | 50 % | ✅ Dashboard slider | Battery will not export below this SoC |
| Max SoC for grid charge | 100 % | ✅ Dashboard slider | Battery will not grid-charge above this SoC |
| Min arbitrage spread | 1.00 DKK/kWh | ✅ Dashboard slider | Minimum sell−buy spread to trigger arbitrage |
| Min export price floor | 0.00 DKK/kWh | ✅ Dashboard input | Floor below which Solar AI will not export; blocks negative/zero prices by default |
| Export power cap | 0 kW | ✅ Dashboard input | Max battery discharge power during export; 0 = no cap |
| Grid import limit | 17 kW | ✅ Dashboard input | Circuit breaker capacity for overcurrent protection |
| Buy-side VAT | 25 % | ✅ Dashboard input | VAT on grid electricity purchases |
| Sell-side fee | 0.00 DKK/kWh | ✅ Dashboard slider | Retailer's per-kWh cut on exports |
| Spot price markup | 0.00 DKK/kWh | ✅ Dashboard input | Retailer's add-on to spot price (handelstillæg) |
| Elafgift | 0.01 DKK/kWh | ✅ Dashboard input | Danish electricity duty |
| Indfødningstarif (DSO + Energinet) | Auto-fetched | Read-only sensor | Feed-in production tariff deducted from export price; updated daily from Energi Data Service |
| Notifications | Off | ✅ Dashboard switch | Send a persistent HA notification on every mode change |
| Grid operator (DSO) | Dinel (Jutland/Fyn) | Options flow | DSO for hourly network tariff and indfødningstarif data |
| Currency | DKK | Options flow | Price and savings sensor currency (DKK, EUR, SEK, NOK, GBP) |
| Live data poll interval | 30 s | Options flow | How often EVCC live state is fetched (10–300 s) |
| Spot price area | DK2 | `CONF_PRICE_AREA` in `const.py` | Nord Pool price zone for Energi Data Service (`DK1` = Jutland/Fyn, `DK2` = Zealand/Copenhagen). Change in `const.py` — config-flow selection coming in a future version |

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

- **Denmark-focused** — built around DKK/kWh spot prices (Nord Pool Elspot, fetched from Energi Data Service) and the Energi Data Service DatahubPricelist tariff APIs. Tariff fetching (DSO nettarif and indfødningstarif) is Danish-specific. The spot price area defaults to DK2; change `DEFAULT_PRICE_AREA` in `const.py` for DK1.
- **FoxESS Modbus required** — work mode control uses FoxESS-specific entities. Other inverters need code changes in `coordinator.py`.
- **EVCC required** — solar forecasts, live grid power, and EV charge data come from EVCC's API.
- **DSO coverage** — network tariff and indfødningstarif auto-fetch currently covers Dinel (Jutland/Fyn). Other Danish DSOs can be added in `const.py`; their GLN numbers are available in the Energi Data Service DatahubPricelist.
- **Learning period** — the system works best after 1–2 weeks of data. During the first few days it uses conservative defaults for charge rates and EV patterns.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

## License

MIT — use freely, adapt for your own setup.
