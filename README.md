# Solar AI for FoxESS

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)

A Home Assistant integration that schedules a FoxESS battery against Nord Pool day-ahead prices, drives an OCPP 1.6 EV charger from solar surplus, and learns from observed production and consumption.

The integration runs as a coordinator that pulls live state from FoxESS Modbus (and optionally EVCC), refreshes day-ahead prices from Energi Data Service once per hour, runs a backward-induction dynamic programming optimiser over a 24- to 48-hour horizon, and executes the resulting plan through FoxESS work-mode + force-charge controls and (optionally) OCPP `RemoteStartTransaction` / `SetChargingProfile` commands.

---

## Recent releases

### v0.28.x — production hardening after first weeks of live operation

- Solcast HA integration supports both `today` and `tomorrow` entities; optimiser plans against a full 48-hour PV horizon (previously 24 h).
- Intra-hour short-term solar correction (v0.28.6): per-tick residual tracking compares actual PV to the matching Solcast 15-min slot, computes a rolling ratio over the last 4 closed slots, and applies the correction with linear decay over a 2-hour horizon on top of the existing 4-day per-hour accuracy factor.
- 48-hour solar forecast chart on the EV / OCPP tab. Two series: raw Solcast (columns) and the per-hour adjusted forecast the optimiser uses (line). Includes today-remaining-kWh and tomorrow-expected-kWh totals.
- EV charge session log with per-tick grid vs solar energy split. Each completed session records start, stop, duration, total kWh, energy from solar surplus, and energy from grid. Rendered as a history table on the Logs tab.
- Bug fixes: lader_effekt now zeros on session end; cool-down restart works from any plugged-in OCPP state; ARMING timer clears when surplus drops below minimum; EV charge power is subtracted before house-load learning; live anti-flap countdown computes against a fixed-target timestamp.

See [CHANGELOG.md](CHANGELOG.md) for the per-version detail.

### v0.27.x — embedded OCPP server and EV charge controller

- Built-in OCPP 1.6 server. The charger connects directly to `ws://<ha-ip>:9000/<cpid>/`. No separate `lbbrhzn/ocpp` HACS integration required.
- Four EV charge modes: Locked, Solar-only, Solar+Battery-to-minimum, Full power (with house-battery discharge lock).
- Time-based anti-flap windows (configurable start / stop) and amp-step rate limiting to stay within charger and breaker tolerances.
- Persistent charger metadata across HA restarts; `TriggerMessage` on reconnect.

### Configuration reference

[docs/CONFIGURATION.md](docs/CONFIGURATION.md) lists every slider, switch, and setup field with the value range and effect.

---

## What it does

Solar AI operates as a Home Assistant integration. It reads live state from FoxESS (and optionally EVCC), fetches day-ahead spot prices, and runs an hourly dynamic programming optimiser that decides when to charge from the grid, when to export, when to idle, and at what current to drive a connected EV charger.

The decision loop has two layers:

1. **Hourly planning.** Fetch spot prices from Energi Data Service (Nord Pool, area `DK2` by default). Combine with auto-fetched DSO and Energinet tariffs, elafgift, VAT, and seller-side fees to compute per-slot buy and sell prices. Run a 24- to 48-hour DP optimiser over 15-minute slots with battery SoC as state (101 integer steps) and CHARGE / EXPORT / IDLE as actions. The result is an ordered plan: `{slot_start, action, expected SoC, buy, sell}`.

2. **Fast tick.** Every 10–300 seconds (configurable, default 30 s) read live state and execute the plan: set FoxESS work mode, write force-charge / force-discharge power, set the export limit register, and — if the OCPP controller is enabled — send `SetChargingProfile` to the EV charger.

All thresholds are live-configurable via dashboard number entities. No YAML editing required after initial setup.

---

## Features

### Arbitrage engine

| Item | Detail |
|---|---|
| Optimiser | Backward-induction dynamic programming. 15-min slots over 24–48 h. SoC state at 1% resolution. CHARGE / EXPORT / IDLE actions. |
| Multi-cycle planning | Handles `charge at 02h, export at 11h, charge again at 14h, export again at 19h` correctly. Simple threshold logic cannot. |
| Buy price | `(spot + retailer markup + DSO tariff + Energinet tariff + elafgift) × VAT` |
| Sell price | `spot − seller-side fee − indfødningstarif (DSO + Energinet, auto-fetched)` |
| Minimum spread | Export only when `sell_price − cheapest_recharge_cost / efficiency ≥ min_spread`. Default 1.00 DKK/kWh, configurable 0.10–3.00. |
| Minimum export price floor | Hard floor below which the export limit register is set to 25 W, blocking both battery and solar export. Default 0.00 (blocks only negative or zero prices). |
| Export power cap | Optional cap on battery discharge during export (0–10 kW). Default 0 (no cap). |
| Negative-price grid charge | When the buy price drops to ≤ 0 DKK/kWh, grid charging starts regardless of spread or EV schedule. |

### Price stack

All components are live-configurable number entities:

| Component | Default | Range |
|---|---|---|
| Buy-side VAT | 25% | 0–50% |
| Seller-side fee | 0.00 DKK/kWh | 0.00–0.50 |
| Spot price markup (retailer add-on) | 0.00 DKK/kWh | 0.00–0.50 |
| Elafgift | 0.01 DKK/kWh | 0.00–3.00 |
| Min. export price floor | 0.00 DKK/kWh | 0.00–2.00 |

### Network tariff integration

- Hourly DSO time-of-use tariffs are fetched from the Energi Data Service DatahubPricelist API by GLN number, refreshed daily.
- Energinet system and transmission charges (code `40000`) are fetched daily.
- The DSO feed-in production tariff (e.g. Nettarif indfødning C, code `TC_IND_03`) and Energinet production tariff (code `40010`) are auto-fetched and deducted from the export price.
- DSO is set in *Settings → Solar AI → Configure → Grid operator*. Dinel (Jutland/Fyn) is wired now; additional DSOs are added in `const.py`.

### Solar forecast

| Item | Detail |
|---|---|
| Sources | EVCC (Solcast under the hood), Solcast HA integration (today + tomorrow entities), Forecast.Solar HA integration, Auto (fallback chain) |
| Per-hour accuracy correction | 4-day rolling per-hour-of-day factor in [0.3, 1.5]. Applied inside the optimiser. |
| Intra-hour correction (v0.28.6) | Per-tick residual tracking; `_st_solar_factor = mean(actual / forecast over last 4 closed 15-min slots)`. Applied with linear decay over 2 h on top of the per-hour factor. |
| Net surplus | Predicted house load subtracted from forecast PV to compute available kWh for the battery. Grid charge skipped when solar will fill the battery. |

### House load model

| Item | Detail |
|---|---|
| Per-hour profile | 24 slots, ~8-day exponential moving average per slot |
| Short-term mean | 2-hour rolling average |
| Long-term mean | 28-day rolling average |
| Vacation detection | If load drops below 25% of 28-day baseline for ≥ 4 hours, the model switches to a conservative estimate. |
| Outlier guard | Two-layer: physical ceiling at `grid_max_kw`, soft cap at 5× current estimate once warm. |
| EV-subtracted (v0.28.0) | Active EV charge power is subtracted before learning, so leaving a car plugged in does not inflate the predicted 24-h house load. |

### EV-aware scheduling (requires EVCC live data mode)

EV-aware features run in EVCC and Hybrid live-data modes. In FoxESS-only mode they are inactive (probability stays at 0).

| Item | Detail |
|---|---|
| Charging detection | Based on actual EV charge power, configurable 500–10000 W (default > 3000 W). |
| Hourly probability | Exponential smoothing over ~8 days. Grid charging is blocked in hours where EV charges ≥ 70% of the time. |
| Max charge rate | ~20-sample EMA from full-speed sessions only (≥ 80% of current learned max). Solar-throttled sessions excluded. |
| Battery-bypass model | EVCC's setting "battery does not feed the EV" is honoured. Solar allocated to the EV is subtracted from battery-available kWh, not from battery discharge. |
| EVCC battery mode | Set to `hold` during arbitrage actions. Restored to `normal` when done. If EVCC has independently taken control, the integration backs off. |

### EV charge controller (OCPP, opt-in)

Optional active control of an OCPP 1.6 charger via the integration's embedded server. Disabled by default. Enable in *Settings → Solar AI → Configure → OCPP Settings*.

Four modes selectable from the dashboard:

| Mode | Behaviour |
|---|---|
| Locked | No charging. |
| Solar-only | Charge only from real-time PV surplus. Stops when surplus drops below the minimum amp setting. |
| Solar+Battery-to-minimum | Solar surplus first; house battery tops up to the minimum amp setting when surplus is insufficient. Stops at the battery floor. |
| Full power | Maximum charge rate from any source. House battery discharge is locked at 0 A while in this mode, so the EV's grid demand cannot be supplemented from the house battery. |

Control loop properties:

- Decoupled asyncio task at a configurable cadence (5–60 s, default 10 s), independent of the main coordinator fast-poll.
- Ramps the OCPP current setpoint between 6 A (4.14 kW) and 16 A (11 kW) at a maximum of 2 A per tick.
- Subtracts the EV's own current draw from house load when measuring surplus.
- Anti-flap windows: start window (default 60 s, range 10–600 s) and stop window (default 180 s, range 30–1800 s). After a stop, the start counter resets.
- Smart OCPP writes: `SetChargingProfile` is only sent on start, stop, or ≥ 1 A change.
- `sensor.solar_ai_ev_status` exposes the controller state machine (`IDLE` / `ARMING` / `CHARGING` / `COOLING`) and `arming_until` / `cooling_until` ISO timestamps for live per-second countdowns.

### Battery model

| Item | Detail |
|---|---|
| Round-trip efficiency | Auto-detected from FoxESS lifetime charge/discharge totals. Activates after 100 kWh cycled. Falls back to configured value until then. |
| Usable capacity | Learned during Force Charge cycles by measuring energy delivered vs SoC rise per tick. Activates after 20 samples. |
| Temperature-adaptive charge rate | 7 buckets: `< 0`, `0–5`, `6–15`, `16–21`, `21–35`, `35–50`, `> 50 °C`. Each bucket records actual charge power during Force Charge and updates the learned rate at the 90th percentile. Each bucket is also exposed as an editable number entity for manual override. |

### Seasonal mode

- 28-day rolling daily solar average switches between `summer` and `winter` mode at a threshold of 6 kWh/day.
- Defaults to `winter` (conservative) until at least 7 days of data are recorded.
- No hard-coded calendar dates.

### Grid overcurrent protection

- Every fast-poll tick reads live grid import power (from EVCC or directly from the FoxESS CT clamp).
- Available headroom = `breaker limit − 0.5 kW safety margin − current grid draw`.
- The battery charge rate is automatically capped to stay within the breaker limit.
- Grid charging is skipped entirely if headroom drops below 0.3 kW.
- Limit is configurable in the config flow (5–63 kW, default 17 kW).

### Savings tracker

- Actual savings: revenue from battery export plus the estimated value of cheap grid charging.
- Missed savings: estimated opportunity cost while the arbitrage switch is off.
- Reported for today, 7 days, and 30 days.
- Stored in a 90-day rolling log that survives HA restarts.
- Hours blocked by the minimum export price floor are excluded from both actual and missed calculations.

### Polling

- Live state (grid power, PV, EV status, battery mode) is fetched on every fast-poll tick.
- Price and tariff data is refreshed at most once per hour.
- Live data poll interval is configurable in *Configure* (10–300 s, default 30 s).

### Dashboard controls

All listed parameters are editable from the dashboard without restarting HA:

| Control | Range | Default |
|---|---|---|
| Battery floor SoC (export minimum) | 10–100% | 50% |
| Battery max SoC (grid charge ceiling) | 10–100% | 100% |
| Minimum arbitrage spread | 0.10–3.00 DKK/kWh | 1.00 |
| Minimum export price floor | 0.00–2.00 DKK/kWh | 0.00 |
| Export power cap | 0–10 kW | 0 (no cap) |
| Grid import limit | 5–63 kW | 17 kW |
| Buy-side VAT | 0–50% | 25% |
| Seller-side fee | 0.00–0.50 DKK/kWh | 0.00 |
| Spot price markup | 0.00–0.50 DKK/kWh | 0.00 |
| Elafgift | 0.00–3.00 DKK/kWh | 0.01 |
| Notifications | On / Off | Off |

---

## Prerequisites

### Live data mode

The integration supports three live-data modes. Pick one during setup:

| Mode | When to choose | Required components |
|---|---|---|
| EVCC | EVCC is running and EV-aware coordination is wanted | EVCC + Solcast (via EVCC) + FoxESS Modbus |
| Hybrid | EVCC handles the EV, but live grid and PV come directly from the inverter | EVCC + FoxESS Modbus + a solar forecast source |
| FoxESS only | No EV, or the EV does not draw from the house battery | FoxESS Modbus + a solar forecast source (Solcast direct or Forecast.Solar) |

Note on FoxESS-only mode: if there is an OCPP-connected EV charger, the embedded OCPP server (v0.27.0+) still detects EV charging directly via the charger. Grid-headroom protection caps battery charging based on live grid-import readings in all modes. EV-aware scheduling (skip grid charge during typical EV hours, hourly probability learning) requires EVCC live-data mode and is inactive in FoxESS-only mode.

### Component checklist

| Component | EVCC | Hybrid | FoxESS only | Link |
|---|:---:|:---:|:---:|---|
| FoxESS Modbus integration | Required | Required | Required | [GitHub](https://github.com/nathanmarlor/foxess_modbus) |
| EVCC | Required | Required | Not used | [evcc.io](https://evcc.io) |
| Solar forecast (one of: EVCC/Solcast, Solcast HA integration with both today + tomorrow entities, Forecast.Solar) | Required | Required | Required (excl. EVCC) | [Solcast](https://solcast.com) / [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) |
| Spot price entity (Strømligning, Tibber, etc.) | Optional | Optional | Optional | — |

If no spot price entity is configured, Solar AI reads spot prices directly from [Energi Data Service](https://api.energidataservice.dk).

### Solcast HA integration — two-entity wiring (v0.28.0+)

The Solcast HA integration creates one entity per forecast day (typically `sensor.solcast_pv_forecast_forecast_today` and `sensor.solcast_pv_forecast_forecast_tomorrow`). The integration reads both for a full 48-hour forecast. Set them in *Settings → Solar AI → Configure → Solar forecast source*:

| Field | Set to |
|---|---|
| Solar forecast source | `solcast` |
| Solcast (today) | `sensor.solcast_pv_forecast_forecast_today` |
| Solcast (tomorrow) | `sensor.solcast_pv_forecast_forecast_tomorrow` |

If the tomorrow field is left blank, the optimiser plans against a 24-h horizon (today only). With both wired, the optimiser plans against the full 48 h and avoids night-time grid charges when the next day is sunny.

### Feature availability by mode

| Feature | EVCC | Hybrid | FoxESS only |
|---|:---:|:---:|:---:|
| Day-ahead DP optimiser (15-min, 48-h) | Yes | Yes | Yes |
| Battery floor / max SoC enforcement | Yes | Yes | Yes |
| Minimum arbitrage spread + degradation cost | Yes | Yes | Yes |
| Solar export floor | Yes | Yes | Yes |
| Temperature-adaptive charge rate learning | Yes | Yes | Yes |
| Capacity + round-trip efficiency auto-detection | Yes | Yes | Yes |
| Solar forecast accuracy learning | Yes | Yes | Yes |
| House load profile learning | Yes | Yes | Yes |
| 30-day savings tracker | Yes | Yes | Yes |
| Session log (exports and charges) | Yes | Yes | Yes |
| Mode-change notifications | Yes | Yes | Yes |
| Live dashboard sliders / switches | Yes | Yes | Yes |
| Grid headroom overcurrent protection | Yes | Yes | Yes (FoxESS CT) |
| EV-aware optimiser scheduling | Yes | Yes | No |
| EV charge probability learning | Yes | Yes | No (stays at 0) |
| EVCC battery-mode coordination | Yes | Yes | n/a |

### Dashboard dependencies (HACS)

The bundled dashboard uses two custom Lovelace cards. Install both via HACS → Frontend before importing the dashboard:

| Card | Used by | Link |
|---|---|---|
| Mushroom Cards | Køb/Salg chips and tiles on Oversigt, section titles in Indstillinger, the Bil-tilsluttet status card on the EV / OCPP tab | [GitHub](https://github.com/piitaya/lovelace-mushroom) |
| ApexCharts Card | 24-h price overlay on Priser & Plan, 48-h Solcelleprognose chart on EV / OCPP (required since v0.28.2) | [GitHub](https://github.com/RomRider/apexcharts-card) |

After installing both, hard-refresh the browser (⌘+Shift+R on macOS, Ctrl+Shift+R elsewhere) before importing the dashboard YAML.

### FoxESS Modbus entity IDs

The setup wizard auto-detects these. Override them in the config flow if your names differ:

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

Copy the `custom_components/battery_arbitrage` folder into the HA config directory:

```
/homeassistant/custom_components/battery_arbitrage/
```

Via HACS: add this repository as a custom repository and install from there.

### 2. Restart Home Assistant

### 3. Add the integration

*Settings → Devices & Services → Add Integration → Solar AI*

The wizard covers:

1. Live data source (EVCC / Hybrid / FoxESS only).
2. EVCC URL (EVCC and Hybrid modes), e.g. `http://your-ha-ip:7070`.
3. FoxESS live sensor overrides (Hybrid and FoxESS-only modes).
4. No-EV acknowledgement (FoxESS-only mode).
5. FoxESS control entities: inverter ID, work-mode select, force-charge / force-discharge number entities.
6. Battery sensors: SoC, temperature, charge/discharge power, lifetime totals.
7. Spot price entity (optional). If blank, Energi Data Service is used directly.
8. Solar forecast source: EVCC / Solcast / Forecast.Solar / Auto, plus entity overrides.
9. Battery and trading parameters: capacity, efficiency, initial thresholds, DSO, currency.
10. Dashboard link (optional).

All of these can be changed later via *Settings → Devices & Services → Solar AI → Configure* without re-running the wizard.

### 4. Connect an EV charger (optional)

For an OCPP 1.6 charger driven by the integration's EV controller:

1. In *Solar AI → Configure → OCPP Settings*:
   - Enable the EV charge controller.
   - Use the embedded OCPP server (default).
   - Set the OCPP server port (default `9000`).
   - Set the Charge Point ID (CPID), e.g. `charger` or `foxess_l11pmc`.
2. On the charger:
   - OCPP backend URL: `ws://<ha-ip>:9000/`. Trailing slash, no CPID in the URL.
   - Charger ID field: the same string set as CPID in HA.
   - Some FoxESS firmware appends the Charger ID to the URL automatically. Verify the final URL the charger reports is `ws://<ha-ip>:9000/<cpid>/`.
   - Leave authentication blank (LAN-only, no auth).
   - Save and power-cycle the charger to force a fresh OCPP connection.
3. Verify within 30–60 s:
   - `sensor.solar_ai_lader_status` moves from `Unavailable` to `Available` (or `Preparing` if a vehicle is already plugged in).
   - `sensor.solar_ai_lader_info` populates with vendor, model, firmware, serial.
   - The EV / OCPP dashboard tab shows the OCPP-connected line.

The embedded server tolerates non-standard OCPP frames (empty-`[]` keepalives from the FoxESS L11PMC are silently ignored). Charger metadata is persisted to HA storage and `TriggerMessage` is sent on reconnect so sensors do not blank after an HA restart.

### 5. Import the dashboard

Two dashboard YAML files are included:

| File | Language |
|---|---|
| `dashboard/dashboard_da.yaml` | Danish |
| `dashboard/dashboard_en.yaml` | English |

Import via *Settings → Dashboards → Add Dashboard → From YAML*.

### 6. Set electricity cost parameters

In the dashboard *Priskonfiguration / Price Configuration* card, set the values from your electricity contract:

- Elafgift: Danish electricity duty (check your bill).
- Spot markup (handelstillæg): retailer's per-kWh add-on.
- VAT: 25% in Denmark.
- Seller-side fee: retailer's per-kWh cut on exports (if any).
- Min. export price: optional floor below which the integration will not export (default 0.00).

The indfødningstarif (DSO + Energinet feed-in production tariff) is fetched and deducted automatically.

### 7. Monitoring mode first

The system starts with the arbitrage switch off. The `Decision reason` sensor shows what the integration *would* do. Flip the switch on once the planned actions look reasonable for your setup.

---

## Decision loop

### Hourly — optimiser run

```
On spot price refresh (typically once per hour):

1. Fetch prices:
   - Energi Data Service Elspotprices (Nord Pool day-ahead, area DK2)
   - Falls back to EVCC /api/tariff/grid if EDS is unreachable
   - Buy-side: (spot + markup + DSO tariff + Energinet tariff + elafgift) × VAT
   - Sell-side: spot − seller-side fee − indfødningstarif (auto-fetched daily)

2. Run DP optimiser (backward induction):
   - State: battery SoC at 1% resolution (0–100% = 101 states)
   - Actions per slot: CHARGE | EXPORT | IDLE
   - Inputs: per-slot buy/sell prices, learned house load profile (24 slots),
             per-slot solar forecast (with per-hour + short-term correction),
             EV hourly probability × learned max rate, charge/discharge
             efficiency, floor SoC, max SoC
   - EXPORT allowed only when:
       sell_price > min_export_price floor
       AND sell_price − cheapest_recharge / efficiency ≥ min_spread
   - CHARGE blocked for hours where EV typically charges (≥ 70% probability)
   - Output: ordered plan {slot_start, action, expected SoC, buy, sell}

3. Plan is stored and drives decisions for the next 60 minutes.
```

### Fast tick — execution

```
1. Fetch EVCC state: grid power, solar, EV charge power, battery mode.
2. Read FoxESS: SoC, cell temp, charge/discharge power, work mode.
3. Update models: house load hourly profile, EV max rate, load history,
                  solar accuracy (long-term + short-term), EV hourly probability,
                  daily solar kWh.
4. Compute grid headroom: limit − 0.5 kW − current import.
5. Look up the plan for the current slot:

   EXPORT if      optimiser says EXPORT
              AND sell price > min export price floor
              AND exportable kWh ≥ 0.5
              AND SoC > floor SoC
              AND EV is not actively charging (now / minpv mode)
              AND EVCC is not managing the battery independently

   GRID CHARGE if optimiser says CHARGE
              AND solar will not fill the battery on its own
              AND importable kWh ≥ 0.5
              AND grid headroom ≥ 0.3 kW
              AND EV is not likely charging this hour

   FORCED CHARGE if buy price ≤ 0 (overrides all other checks)

   FALLBACK if no plan exists yet: reactive logic — export if sell ≥ p75,
   charge if buy ≤ p25.

6. Execute (if the master switch is on): set FoxESS work mode, capped
   charge power, EVCC mode. Optionally cap discharge to max_export_kw.
7. Write export limit register every tick:
     grid charging   → 0 W
     price ≤ floor   → 25 W (blocks solar + battery export)
     price > floor   → 10000 W
8. Send a persistent HA notification on mode transition (optional).
9. Accumulate actual / missed DKK into the daily log.
10. Persist learned state (rates, load history, EV probabilities, solar history).
```

---

## Sensor reference

### Decision and control

| Entity | Description |
|---|---|
| `switch.*_arbitrage_aktiv` | Master on/off switch |
| `switch.*_notifikationer_ved_tilstandsskift` | Mode-change notifications toggle |
| `sensor.*_driftstilstand` | Current mode: `normal` / `exporting` / `grid_charging` / `disabled` |
| `sensor.*_begrundelse_for_tilstand` | Plain-language reason for the current decision |

### Price

| Entity | Description |
|---|---|
| `sensor.*_eksportpris` | Current net export price (DKK/kWh). Never < 0. |
| `sensor.*_net_arbitrage_spread` | Export price minus 24-h minimum buy price |
| `sensor.*_24h_prisminimum/maksimum/gennemsnit` | 24-h price statistics |
| `sensor.*_24h_pris_25/75_percentil` | Quartile thresholds used for fallback decisions |
| `sensor.*_naeste_slots_pris` | Price for the next 30-minute slot |
| `sensor.*_nettarif_denne_time` | DSO + Energinet + elafgift for the current hour (DKK/kWh) |
| `sensor.*_indfodningstarif_dso_energinet` | Auto-fetched feed-in production tariff (DKK/kWh) |
| `sensor.*_minimum_eksportpris` | Configured export price floor |
| `sensor.*_24h_priskort` | 24-h price chart sensor; `slots` attribute = list of `{h, buy, sell}` |
| `sensor.*_dagens_plan` | Today's plan as plain text; `charge_hours` and `export_hours` attributes |

### Number entities (live-editable)

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

| Entity | Range | Description |
|---|---|---|
| `number.*_minimum_arbitrage_spread` | 0.00–3.00 DKK/kWh | Spread threshold before arbitrage triggers |
| `number.*_minimum_eksportpris_*` | 0.00–2.00 DKK/kWh | Minimum export price floor |
| `number.*_eksporteffekt_graense_*` | 0–10 kW | Max battery discharge power during export (0 = no cap) |
| `number.*_salgsgebyr_pr_kwh` | 0.00–0.50 DKK/kWh | Seller-side fee |
| `number.*_spotpris_tillaeg_*` | 0.00–0.50 DKK/kWh | Retailer spot markup |
| `number.*_elafgift_dkk_kwh` | 0.00–3.00 DKK/kWh | Elafgift |
| `number.*_moms_pa_kob` | 0–50% | VAT on purchases |
| `number.*_minimum_soc_eksport` | 10–100% | Battery floor SoC for export |
| `number.*_maksimum_soc_netopladning` | 10–100% | Battery max SoC for grid charging |
| `number.*_net_importgraense` | 5–63 kW | Circuit breaker capacity |

### Solar

| Entity | Description |
|---|---|
| `sensor.*_solcelleproduktion_live` | Real-time PV output (kW) |
| `sensor.*_solcelle_prognose_24h/6h` | Raw Solcast forecast (kWh) |
| `sensor.*_solcelle_prognose_24h/6h_justeret` | Accuracy-corrected forecast |
| `sensor.*_solcelle_prognose_nojagtighed` | Rolling accuracy factor (%) |
| `sensor.*_netto_sol_til_batteri_24h` | Net solar surplus after house load (kWh) |
| `sensor.*_sol_gennemsnit_28_dage` | 28-day average daily solar production (kWh) |
| `sensor.*_saesontilstand` | `summer` or `winter` |
| `sensor.*_solcelleprognose_48t_graf` | 48-h chart sensor; `slots` attribute = per-slot `{start, raw_kw, adj_kw, factor}` |
| `sensor.*_solcelleprognose_fejl_nu` | Short-term forecast deviation (%) over the last 4 closed 15-min slots |

### Battery

| Entity | Description |
|---|---|
| `sensor.*_eksporterbar_energi` | kWh available for export above floor SoC |
| `sensor.*_importerbar_energi` | kWh room to charge below max SoC |
| `sensor.*_tid_til_fuld_opladning` | Hours to reach max SoC at current rate |
| `sensor.*_batteritemperatur_laveste_celle` | Lowest cell temperature |
| `sensor.*_laert_opladningshastighed_*` | Learned charge rate per temperature bucket (kW) |
| `sensor.*_laert_batterikapacitet` | Learned usable capacity (kWh). Active after ~20 samples. |
| `sensor.*_auto_detekteret_effektivitet` | Measured round-trip efficiency from FoxESS lifetime totals (%) |
| `sensor.*_kapacitets_laeringseksempler` | Number of capacity learning samples collected |

### Grid

| Entity | Description |
|---|---|
| `sensor.*_net_importeffekt` | Live grid import power (kW) |
| `sensor.*_net_raaderum` | Headroom before breaker limit (kW) |

### EV and load

| Entity | Description |
|---|---|
| `sensor.*_ev_opladningssandsynlighed_denne_time` | Learned EV charge probability this hour (%) |
| `sensor.*_ev_maks_opladningshastighed_laert` | Learned EV peak AC charge rate (kW) |
| `sensor.*_husstand_forbrug_2h_gennemsnit` | 2-h average house load (kW) |
| `sensor.*_husstand_forbrug_28_dages_gennemsnit` | 28-day average house load (kW) |
| `sensor.*_huslast_laert_denne_time` | Learned house load for the current hour of day (kW); `profile_kw` attribute = 24-slot array |
| `sensor.*_forudsagt_husstand_forbrug_24h` | Predicted house consumption today (kWh) |
| `binary_sensor.*_ev_oplader_solenergi` | EV is charging on solar power (pv mode, > 3 kW) |

### EV controller

| Entity | Description |
|---|---|
| `sensor.*_ev_status` | State machine: `IDLE` / `ARMING` / `CHARGING` / `COOLING`. Attributes include `arming_until`, `cooling_until` (ISO timestamps for live countdown), `target_kw`, `target_amps`, `surplus_kw`. |
| `sensor.*_lader_status` | OCPP status from the charger |
| `sensor.*_lader_effekt` | Live charger power (kW) |
| `sensor.*_lader_info` | Vendor / model / firmware / serial of the charger |
| `sensor.*_lader_sessions_log` | Completed session list. `sessions` attribute = last 20 sessions newest-first with `energy_kwh`, `energy_kwh_solar`, `energy_kwh_grid`, `duration_min`, `start_ts`, `end_ts`. |

### Savings

| Entity | Description |
|---|---|
| `sensor.*_faktisk_besparelse_i_dag/7_dage/30_dage` | Actual savings earned (DKK) |
| `sensor.*_forpasset_besparelse_i_dag/7_dage/30_dage` | Missed savings while disabled (DKK) |

---

## Configuration reference

All settings are in *Settings → Devices & Services → Solar AI → Configure*, or live via dashboard number entities:

| Parameter | Default | Live | Description |
|---|---|---|---|
| Battery capacity | 11.52 kWh | No (config flow) | Fallback. Replaced by learned value after ~20 Force Charge samples. |
| Round-trip efficiency | 92% | No (config flow) | Fallback. Replaced by FoxESS lifetime totals after 100+ kWh cycled. |
| Forecast horizon | 24 h | No (config flow) | Hours of price data to analyse |
| Min SoC during export | 50% | Yes | Battery will not export below this SoC |
| Max SoC for grid charge | 100% | Yes | Battery will not grid-charge above this SoC |
| Min arbitrage spread | 1.00 DKK/kWh | Yes | Minimum sell − buy spread to trigger arbitrage |
| Min export price floor | 0.00 DKK/kWh | Yes | Floor below which the integration will not export |
| Export power cap | 0 kW | Yes | Max battery discharge power during export. 0 = no cap. |
| Grid import limit | 17 kW | Yes | Circuit breaker capacity for overcurrent protection |
| Buy-side VAT | 25% | Yes | VAT on grid electricity purchases |
| Seller-side fee | 0.00 DKK/kWh | Yes | Retailer's per-kWh cut on exports |
| Spot price markup | 0.00 DKK/kWh | Yes | Retailer's add-on to spot price |
| Elafgift | 0.01 DKK/kWh | Yes | Danish electricity duty |
| Indfødningstarif | Auto-fetched | Read-only sensor | Feed-in production tariff deducted from export price. Updated daily. |
| Notifications | Off | Yes | Persistent HA notification on every mode change |
| Grid operator (DSO) | Dinel (Jutland/Fyn) | Options flow | DSO for hourly network tariff and indfødningstarif data |
| Currency | DKK | Options flow | Price and savings sensor currency (DKK, EUR, SEK, NOK, GBP) |
| Live data poll interval | 30 s | Options flow | Fast-poll cadence (10–300 s) |
| Embedded OCPP server | On | Options flow → OCPP Settings | Integration hosts its own OCPP 1.6 server. Turn off to use `lbbrhzn/ocpp` instead. |
| Embedded OCPP port | 9000 | Options flow → OCPP Settings | TCP port the embedded server listens on |
| EV controller enabled | Off | Options flow → OCPP Settings | Master gate for the OCPP-driven EV charge controller |
| EV control loop interval | 10 s | Options flow → OCPP Settings | How often the EV controller re-evaluates surplus (5–60 s) |
| EV start window | 60 s | Options flow → OCPP Settings | Sustained-surplus seconds before charging starts (10–600 s) |
| EV stop window | 180 s | Options flow → OCPP Settings | Sustained-shortage seconds before charging stops (30–1800 s) |
| EV charging detection threshold | 3000 W | Options flow → OCPP Settings | Above this charge power, the EV is considered actually charging (500–10000 W) |
| EV default mode on plug-in | Locked | Options flow → OCPP Settings | Mode applied when a vehicle is freshly connected |
| EV min / max charge rate | 4.14 / 11.0 kW | Dashboard sliders | OCPP current setpoint range (6 A / 16 A on 3-phase) |
| Spot price area | DK2 | `CONF_PRICE_AREA` in `const.py` | Nord Pool price zone. `DK1` = Jutland/Fyn, `DK2` = Zealand/Copenhagen. Config-flow selection planned. |

---

## Services

| Service | Description |
|---|---|
| `battery_arbitrage.force_export` | Activate Feed-in First regardless of prices |
| `battery_arbitrage.force_grid_charge` | Start grid charging immediately |
| `battery_arbitrage.restore_normal` | Cancel active export or charging; return to Self-Use |
| `battery_arbitrage.reset_learning` | Clear all learned rates, load history, and solar samples |

---

## Known limitations

- **Denmark-focused.** The price model is built around DKK/kWh, Nord Pool Elspot via Energi Data Service, and the Danish DatahubPricelist tariff API. Tariff fetching is Danish-specific. The spot price area defaults to DK2; change `DEFAULT_PRICE_AREA` in `const.py` for DK1.
- **FoxESS Modbus required.** Work-mode control uses FoxESS-specific entities. Other inverters require code changes in `coordinator.py`.
- **EVCC required for EV-aware scheduling.** Solar forecasts, live grid power, and EV charge data come from EVCC's API in EVCC and Hybrid modes. FoxESS-only mode loses the EV-aware scheduling features (the OCPP controller still works).
- **DSO coverage.** Network tariff and indfødningstarif auto-fetch covers Dinel (Jutland/Fyn). Other Danish DSOs can be added in `const.py`; GLN numbers are available in the Energi Data Service DatahubPricelist.
- **Learning period.** The system reaches steady-state accuracy after 1–2 weeks of data. The first few days use conservative defaults for charge rates and EV patterns.
- **GBP installs still see some DKK labels.** UK users on Octopus (v0.30.0+) get correct numeric values, but six number-entity sliders (spot markup, elafgift, sell-side fee, min export price, battery degradation cost, min arbitrage spread), two savings sensors, mode-change notifications, and the "Elafgift" label all render hardcoded `DKK/kWh`. The math is unaffected. To be addressed in a follow-up release with template-substituted units.
- **15-second card refresh requires upstream sources to match (v0.36.0+).** The default fast-poll interval is now 15 s, so integration-driven sensors publish new values every 15 s and cards re-render at that cadence. PV / load / battery numbers read from the FoxESS Modbus integration are bounded by *its* poll interval, which is set independently (Settings → Devices & Services → FoxESS - Modbus → Configure). Drop FoxESS Modbus to 15 s if you want true end-to-end 15-s freshness. Same applies to Solcast (refresh cadence is per its own integration settings) and other HA-side data sources.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

---

## License

MIT.
