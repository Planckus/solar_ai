# Solar AI — Configuration Reference

Every slider, switch, and setup field explained in plain English. Use this as a lookup when you're configuring or tweaking the integration.

This reference assumes you know what a battery SoC is and that electricity has a price. It does **not** explain how the optimizer works internally — that's covered in the [README](../README.md) and [CHANGELOG](../CHANGELOG.md).

---

## Table of contents

- [Setup wizard fields](#setup-wizard-fields)
- [Number sliders](#number-sliders)
  - [Battery thresholds](#battery-thresholds)
  - [Pricing parameters](#pricing-parameters)
  - [Optimizer parameters](#optimizer-parameters)
  - [Learned charge rates](#learned-charge-rates)
- [Switches](#switches)
  - [Master controls](#master-controls)
  - [Notification events](#notification-events)
  - [Notification devices](#notification-devices)
- [How to change settings after install](#how-to-change-settings-after-install)

---

## Setup wizard fields

These are asked once during installation. Most can be changed later in **Settings → Devices & Services → Solar AI → Configure**.

### Live data source

**What it controls:** Where Solar AI reads live grid power, PV production, house load, and EV charging state from.

- **EVCC** *(default)* — Everything from EVCC. Required if you want EV-aware coordination.
- **Hybrid** — FoxESS Modbus for grid / PV / load (more accurate), EVCC for EV state.
- **FoxESS only** — No EVCC. No EV detection. Requires explicit acknowledgement.

**When to change:** Switch to Hybrid if you have EVCC but want better live grid/PV measurement. Switch to FoxESS-only if you don't have EVCC at all.

### EVCC URL

**What it controls:** The full URL of your EVCC instance, including port (e.g. `http://192.168.1.50:7070`).

**When asked:** Only in EVCC and Hybrid modes.

### FoxESS live sensors

**Auto-detected sensors** for live grid / PV / load when in Hybrid or FoxESS-only mode:

- `foxess_grid_import_entity` — defaults to `sensor.foxessmodbus_grid_consumption`. Always positive when importing from the grid.
- `foxess_grid_export_entity` — defaults to `sensor.foxessmodbus_feed_in`. Always positive when exporting to the grid.
- `foxess_pv_power_entity` — defaults to `sensor.pv_power_foxessmodbus`. Combined PV1 + PV2 production.
- `foxess_load_power_entity` — defaults to `sensor.foxessmodbus_load_power`. House consumption.

**When to change:** Only if your FoxESS Modbus integration uses non-default entity names.

### Solar forecast source

**What it controls:** Where the day's PV production forecast comes from.

- **EVCC** *(default if you have EVCC)* — Solcast forecast via EVCC.
- **Solcast** — Solcast HA integration directly (no EVCC needed).
- **Forecast.Solar** — Forecast.Solar HA integration directly (free tier OK).
- **Auto** — Try EVCC → Forecast.Solar → Solcast in order.

**When to change:** Pick Solcast or Forecast.Solar if you want to drop the EVCC middleman. Pick Auto for resilience against any single source going down.

### Spot price entity *(optional)*

**What it controls:** The HA sensor Solar AI reads to get the current spot price (excluding VAT, in DKK/kWh). Works with Strømligning, Tibber, or any compatible source.

**When to change / Leave blank:** Leave blank and Solar AI fetches the live spot price directly from Energi Data Service — the same feed the optimizer uses internally.

### FoxESS control entities

The select / number entities Solar AI uses to drive the inverter:

- `foxess_inverter_id` — the hex string ID of your FoxESS Modbus inverter
- `foxess_work_mode_entity` — `select.foxessmodbus_work_mode`, used to switch between Self Use / Feed-in First / Force Charge
- `foxess_force_charge_entity` — `number.foxessmodbus_force_charge_power`, sets the Force Charge wattage
- `foxess_force_discharge_entity` — `number.foxessmodbus_force_discharge_power`, sets the Force Discharge wattage (export power cap)

**When to change:** Only if your inverter setup differs from the FoxESS Modbus defaults.

### Battery sensors

Sensors Solar AI reads to monitor the battery:

- `battery_soc_entity` — current SoC (%)
- `cell_temp_entity` — lowest cell temperature (°C), used for temperature-adaptive charge rates
- `battery_charge_entity` — instantaneous charge power (kW)
- `battery_discharge_entity` — instantaneous discharge power (kW)
- `battery_charge_total_entity` — lifetime charge total (kWh), used to auto-detect round-trip efficiency
- `battery_discharge_total_entity` — lifetime discharge total (kWh), same purpose

**When to change:** Only if your FoxESS Modbus entity names differ from the defaults.

### Battery capacity

**What it controls:** Total usable battery capacity in kWh (e.g. `2.9` for a 2.9 kWh pack). Auto-detected from EVCC when available; otherwise enter manually.

**When to change:** Only if you replace or expand your battery.

### Battery thresholds & trading parameters (asked at setup)

These appear in the setup wizard but are also live-adjustable as sliders. See the [Number sliders](#number-sliders) section below for full explanations.

- Minimum SoC (export) — `battery_floor_soc`
- Maximum SoC (grid charge) — `battery_max_soc`
- Round-trip efficiency
- Forecast horizon (hours)
- Currency
- Live data poll interval (seconds)
- Grid operator (DSO)

### Dashboard *(optional)*

**What it controls:** If you import the bundled Lovelace dashboard, Solar AI can link to it from the integration page.

**When to change:** Leave blank if you don't want a quick-link in the integration UI, or set it after importing the dashboard.

---

## Number sliders

All sliders are live-configurable from the dashboard's **Indstillinger** tab. Changes apply on the next optimizer tick (within seconds) — no restart needed.

### Battery thresholds

#### Minimum SoC (export) — `battery_floor_soc`

- **Range:** 10–90 %
- **Default:** 50 %
- **What it controls:** Solar AI will never export battery energy below this SoC. Acts as a hard floor.
- **When to lower:** If you have a small battery and want to extract more value from arbitrage.
- **When to raise:** If you want a guaranteed reserve for outages or evening house load.

#### Maximum SoC (grid charge) — `battery_max_soc`

- **Range:** 50–100 %
- **Default:** 100 %
- **What it controls:** Solar AI will never grid-charge the battery above this SoC. Caps how full it'll pull the battery from cheap grid hours.
- **When to lower:** If you want to leave headroom for incoming solar production (so solar doesn't get wasted to the grid).

#### Export power cap (0 = no cap) — `max_export_kw`

- **Range:** 0–10 kW
- **Default:** 0 (no cap)
- **What it controls:** Maximum export power Solar AI will write to the inverter's Force Discharge register. 0 means use the inverter's own maximum.
- **When to change:** If your contract limits export, or you want to throttle export to fit within other constraints.

#### Grid import limit — `grid_max_kw`

- **Range:** 5–63 kW
- **Default:** 17 kW
- **What it controls:** Your main breaker's capacity. Used to cap battery grid-charge power so EV + battery + house combined never exceed the breaker.
- **When to change:** Match your actual fuse rating. Get it wrong and you might trip the breaker.

### Pricing parameters

These all feed into the buy-price and sell-price formulas the optimizer uses.

#### Buy-side VAT — `vat_pct`

- **Range:** 0–25 %
- **Default:** 25 % (Danish standard)
- **What it controls:** VAT percentage applied to the buy-side price total. Affects every CHARGE decision.
- **When to change:** Match your local VAT rate.

#### Spot price markup — `spot_markup`

- **Range:** 0.00–0.50 DKK/kWh
- **Default:** 0 DKK/kWh
- **What it controls:** Your electricity retailer's per-kWh fee added on top of the raw spot price. Effectively raises the buy price the optimizer sees.
- **When to change:** Whenever your retailer changes their markup.

#### Electricity duty (elafgift) — `elafgift`

- **Range:** 0.00–1.00 DKK/kWh
- **Default:** 0.95 DKK/kWh (Danish 2024–2025 rate)
- **What it controls:** Government electricity duty added to buy-side cost.
- **When to change:** When the government changes the duty (typically January each year).

#### Sell-side fee — `export_fee`

- **Range:** 0.00–0.10 DKK/kWh
- **Default:** 0 DKK/kWh
- **What it controls:** Per-kWh cut your grid company takes from your export revenue. Reduces the sell price the optimizer sees.
- **When to change:** If your retailer or DSO levies an export fee.

#### Minimum export price (0 = allow negative) — `min_export_price`

- **Range:** 0.00–2.00 DKK/kWh
- **Default:** 0.05 DKK/kWh
- **What it controls:** Hard floor on solar export. If the live sell price drops below this, Solar AI blocks solar export at the inverter (sets export limit to 25 W). Prevents giving solar away during very low-price hours.
- **When to lower / raise:** Set to 0 if you don't mind exporting at any positive price. Raise if you'd rather store/throttle solar than sell it cheaply.

### Optimizer parameters

#### Minimum gevinst pr. kWh — `min_spread_arbitrage`

- **Range:** 0.00–3.00 DKK/kWh (0.05 steps)
- **Default:** 0.30 DKK/kWh
- **What it controls:** Hard gate on EXPORT decisions. The optimizer only sells from the battery if `(sell price after fees) − (recharge cost after losses)` is at least this much. Higher = more conservative.
- **When to lower:** If you're missing legitimate arbitrage opportunities — useful when the battery wear cost is doing the heavy lifting.
- **When to raise:** If you want a larger safety margin on top of the wear cost.

#### Batteri-slidomkostning — `battery_degradation_cost`

- **Range:** 0.00–1.00 DKK/kWh (0.01 steps)
- **Default:** 0.10 DKK/kWh
- **What it controls:** Per-kWh cost added to both CHARGE and EXPORT decisions inside the optimizer. Models the wear-and-tear of cycling the battery. Higher = the optimizer takes fewer cycles.
- **How to set it:** Roughly `(battery_cost_per_kWh) / (cycle_life × depth_of_discharge)`. For typical residential LFP at ~2 000 DKK/kWh: ~0.10–0.30 is reasonable. Set to 0 for maximum activity (and faster wear).

### Learned charge rates

These auto-calibrate as your battery runs Force Charge sessions. You can see them under **Indstillinger → Lærte opladningshastigheder**.

- **Range:** 0.00–10 kW per slider
- **Defaults:** 1 kW (warm bucket); ~0.5–0.8 kW (cold buckets)
- **What they control:** The maximum charge rate Solar AI tells the inverter to use, by temperature bucket. Cold cells charge slower than warm ones — Solar AI learns the actual achievable rate per bucket from real Force Charge data.
- **Buckets:** under 0 °C / 0–5 °C / 6–15 °C / 16–21 °C / 21–35 °C / 35–50 °C / over 50 °C
- **When to override manually:** Only if the learning produced an obviously wrong value (e.g. due to an inverter firmware quirk). Normally let it self-calibrate.

---

## Switches

### Master controls

#### Solar AI on/off — `arbitrage_aktiv`

- **What it controls:** The integration's master switch. When OFF, Solar AI keeps reading data and updating sensors but **does not change the inverter work mode or EVCC battery mode**. All decisions are shown ("would export" / "would grid-charge") but never executed.
- **When to use:** Turn off during testing, when you want manual control, or during initial learning periods.

#### Notifikationer ved tilstandsskift — `notifications_enabled`

- **What it controls:** When ON, Solar AI fires a **persistent HA notification** (the bell icon in HA, not a mobile push) whenever it transitions between Self-use, Exporting, and Grid Charging modes.
- **When to enable:** If you want a visible HA-internal record of mode changes. Independent from the mobile push notifications below.

#### 15-minutters prisopløsning — `price_resolution_15min`

- **What it controls:** When ON, the 24h price chart sensor emits one row per native 15-minute slot. When OFF (default), it deduplicates to one row per hour.
- **When to enable:** If your dashboard's price card supports finer resolution. The optimizer always uses native resolution internally regardless of this toggle.

### Notification events

Six toggles controlling which events trigger a mobile push notification. All default to OFF.

#### Eksport startet — `notify_export_start`

Fires when Solar AI transitions **into** EXPORTING mode (i.e. the battery starts selling to the grid for arbitrage). Note: this is **not** the same as solar surplus exporting passively — only when Solar AI's optimizer actively decides to discharge the battery.

#### Eksport stoppet — `notify_export_stop`

Fires when Solar AI transitions **out of** EXPORTING mode. Notification includes the session summary (start/end SoC, kWh exported, DKK earned).

#### Opladning startet — `notify_charge_start`

Fires when Solar AI transitions **into** GRID_CHARGING mode (i.e. the battery starts charging from the grid at a cheap-price hour).

#### Opladning stoppet — `notify_charge_stop`

Fires when Solar AI exits GRID_CHARGING. Includes session summary.

#### Solareksport blokeret (prisgulv) — `notify_solar_floor_blocked`

Fires when the live sell price drops **below** your `min_export_price` floor and Solar AI blocks solar export at the inverter (export limit register flips from 10 000 W → 25 W).

#### Solareksport genoptaget — `notify_solar_floor_resumed`

Fires on the reverse transition: live sell price rises above the floor, solar export is re-enabled (25 W → 10 000 W).

### Notification devices

One toggle per registered HA Companion mobile device (auto-discovered from your `notify.mobile_app_*` services). All default to OFF.

- **What they control:** Which devices receive the push notifications you enabled above. Toggle on the devices you want notifications on. If no devices are toggled on, no notification is sent regardless of event toggles.
- **Example:** If you want your phone to get notifications, toggle **Notifikation: My Phone**. If you also want another device's, toggle that too.

---

## How to change settings after install

### Sliders & switches

All sliders and switches are available on the **Indstillinger** tab of the bundled dashboard. Changes are saved instantly and applied on the next optimizer tick (within seconds for the fast loop, within an hour for parameters that only affect the day-ahead plan).

### Setup-wizard fields (entity mappings, EVCC URL, source pickers, etc.)

Open **Settings → Devices & Services → Solar AI → Configure**. The Options form lets you change any of the wizard fields. Save triggers an automatic reload — no HA restart needed.

### Battery thresholds at startup

The first time the integration starts, the battery thresholds (floor SoC, max SoC, etc.) are seeded from the values entered in the setup wizard. After that, the slider values take over — the wizard values are no longer consulted. To reset, use the Options form.

---

## Where the values are stored

Two distinct stores, for two distinct kinds of value:

| Stored where | What's there | Survives restart? |
|---|---|---|
| `entry.data` (HA config entry) | One-time setup choices: EVCC URL, FoxESS entity IDs, currency, DSO, live-data source, solar source, etc. | ✅ |
| `_stored` (local JSON in HA storage) | Live-adjustable values: all sliders, switches, learning models (charge rates, capacity samples, savings log, action log, etc.) | ✅ |

If you ever uninstall and reinstall the integration without removing the config entry, the learning models persist across the reinstall.

---

*Last updated for v0.24.0. If a setting is missing from this doc, file an issue.*
