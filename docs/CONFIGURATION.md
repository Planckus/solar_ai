# Configuration reference

Every setup field, slider, and switch with its value range, effect, and when to change it. Use this as a lookup. For how the optimiser works internally, see the [README](../README.md) and [CHANGELOG](../CHANGELOG.md).

---

## Contents

- [Setup wizard](#setup-wizard)
- [Number entities](#number-entities)
  - [Battery thresholds](#battery-thresholds)
  - [Pricing parameters](#pricing-parameters)
  - [Optimiser parameters](#optimiser-parameters)
  - [Learned charge rates](#learned-charge-rates)
- [Switches](#switches)
  - [Master controls](#master-controls)
  - [Notification events](#notification-events)
  - [Notification devices](#notification-devices)
- [Changing settings after install](#changing-settings-after-install)
- [Storage layout](#storage-layout)

---

## Setup wizard

Most fields can be changed later in *Settings → Devices & Services → Solar AI → Configure*.

### Live data source

Where the integration reads live grid power, PV production, house load, and EV charging state from.

| Mode | Source | When to pick |
|---|---|---|
| EVCC (default) | Everything from EVCC | EV-aware coordination is wanted |
| Hybrid | FoxESS Modbus for grid / PV / load, EVCC for EV state | EVCC is installed but FoxESS-direct measurements are more accurate for your setup |
| FoxESS only | No EVCC. No EV-aware scheduling. Requires explicit acknowledgement. | No EVCC available |

### EVCC URL

The full URL of the EVCC instance, including port. Example: `http://your-ha-ip:7070` or `http://homeassistant.local:7070`. Asked only in EVCC and Hybrid modes.

### FoxESS live sensors

Auto-detected in Hybrid and FoxESS-only modes. Override only if FoxESS Modbus entity names differ from defaults.

| Field | Default | Sign convention |
|---|---|---|
| `foxess_grid_import_entity` | `sensor.foxessmodbus_grid_consumption` | Positive when importing from grid |
| `foxess_grid_export_entity` | `sensor.foxessmodbus_feed_in` | Positive when exporting to grid |
| `foxess_pv_power_entity` | `sensor.pv_power_foxessmodbus` | Combined PV1 + PV2 |
| `foxess_load_power_entity` | `sensor.foxessmodbus_load_power` | House consumption |

### Solar forecast source

Where the PV production forecast comes from.

| Source | Notes |
|---|---|
| EVCC (default if EVCC is present) | Solcast forecast via EVCC |
| Solcast | Solcast HA integration directly. Set both `today` and `tomorrow` entities for a 48-hour horizon. |
| Forecast.Solar | Forecast.Solar HA integration directly. Free tier works. |
| Auto | Try EVCC → Forecast.Solar → Solcast in order |

### Spot price entity (optional)

The HA sensor exposing the current spot price (excluding VAT, DKK/kWh). Works with Strømligning, Tibber, or any compatible source.

If left blank, the integration fetches the live spot price directly from Energi Data Service.

### FoxESS control entities

Auto-detected; override only if the inverter setup differs.

| Field | Description |
|---|---|
| `foxess_inverter_id` | Hex string ID of the FoxESS Modbus inverter |
| `foxess_work_mode_entity` | `select.foxessmodbus_work_mode`. Used to switch between Self-Use / Feed-in First / Force Charge. |
| `foxess_force_charge_entity` | `number.foxessmodbus_force_charge_power`. Sets Force Charge wattage. |
| `foxess_force_discharge_entity` | `number.foxessmodbus_force_discharge_power`. Sets Force Discharge wattage (export power cap). |

### Battery sensors

| Field | Used for |
|---|---|
| `battery_soc_entity` | Current SoC (%) |
| `cell_temp_entity` | Lowest cell temperature (°C). Drives temperature-adaptive charge rates. |
| `battery_charge_entity` | Instantaneous charge power (kW) |
| `battery_discharge_entity` | Instantaneous discharge power (kW) |
| `battery_charge_total_entity` | Lifetime charge total (kWh). Drives auto-detected round-trip efficiency. |
| `battery_discharge_total_entity` | Lifetime discharge total (kWh) |

### Battery capacity

Total usable battery capacity in kWh (e.g. `11.52`). Auto-detected from EVCC when available; otherwise enter manually. Change only when the battery is replaced or expanded.

### Battery thresholds at setup

These appear in the wizard but are also live-adjustable as number entities. See [Number entities](#number-entities) below.

- Minimum SoC (export)
- Maximum SoC (grid charge)
- Round-trip efficiency
- Forecast horizon (hours)
- Currency
- Live data poll interval (seconds)
- Grid operator (DSO)

### Dashboard (optional)

Linking the bundled Lovelace dashboard from the integration page. Leave blank to skip.

---

## Number entities

All number entities are editable from the *Indstillinger* tab. Changes apply on the next optimiser tick (within seconds). No restart needed.

### Battery thresholds

#### Minimum SoC (export) — `battery_floor_soc`

- Range: 10–90%
- Default: 50%
- Effect: the integration will not export battery energy below this SoC. Acts as a hard floor.
- Lower it: small battery, more arbitrage activity wanted.
- Raise it: keep a guaranteed reserve for outages or evening load.

#### Maximum SoC (grid charge) — `battery_max_soc`

- Range: 50–100%
- Default: 100%
- Effect: the integration will not grid-charge the battery above this SoC.
- Lower it: leave headroom for incoming solar so solar production is not wasted to the grid.

#### Export power cap — `max_export_kw`

- Range: 0–10 kW
- Default: 0 (no cap)
- Effect: maximum export power written to the inverter's Force Discharge register. 0 means use the inverter's own maximum.
- Change it: if the contract limits export, or to throttle export within other constraints.

#### Grid import limit — `grid_max_kw`

- Range: 5–63 kW
- Default: 17 kW
- Effect: breaker capacity. Used to cap battery grid-charge power so EV + battery + house combined never exceed the breaker.
- Change it: match the actual fuse rating. An incorrect value can trip the breaker.

### Pricing parameters

These feed into the buy-price and sell-price formulas the optimiser uses.

#### Buy-side VAT — `vat_pct`

- Range: 0–25%
- Default: 25% (Denmark)
- Effect: VAT percentage applied to the buy-side price total.

#### Spot price markup — `spot_markup`

- Range: 0.00–0.50 DKK/kWh
- Default: 0 DKK/kWh
- Effect: retailer's per-kWh fee added on top of the raw spot price. Raises the buy price the optimiser sees.

#### Elafgift — `elafgift`

- Range: 0.00–3.00 DKK/kWh
- Default: 0.01 DKK/kWh
- Effect: Danish electricity duty added to the buy-side cost. Change when the duty is updated (typically January).

#### Seller-side fee — `export_fee`

- Range: 0.00–0.50 DKK/kWh
- Default: 0 DKK/kWh
- Effect: per-kWh cut on export revenue. Reduces the sell price the optimiser sees.

#### Minimum export price — `min_export_price`

- Range: 0.00–2.00 DKK/kWh
- Default: 0.00 DKK/kWh
- Effect: hard floor on export. If the live sell price drops below this, the integration blocks both battery and solar export at the inverter (export limit register set to 25 W).
- 0.00 blocks only negative or zero prices. Raise it to keep solar self-consumed rather than sold cheaply.

### Optimiser parameters

#### Minimum arbitrage spread — `min_spread_arbitrage`

- Range: 0.00–3.00 DKK/kWh (0.05 steps)
- Default: 1.00 DKK/kWh
- Effect: hard gate on EXPORT decisions. The optimiser only sells from the battery if `(sell price after fees) − (recharge cost after losses)` is at least this much.
- Lower it: capture more legitimate arbitrage when the battery wear cost is doing the heavy lifting.
- Raise it: larger safety margin on top of the wear cost.

#### Battery degradation cost — `battery_degradation_cost`

- Range: 0.00–1.00 DKK/kWh (0.01 steps)
- Default: 0.10 DKK/kWh
- Effect: per-kWh cost added to both CHARGE and EXPORT decisions inside the optimiser. Models battery wear.
- Estimation: `(battery_cost_per_kWh) / (cycle_life × depth_of_discharge)`. For typical residential LFP at ~2000 DKK/kWh, 0.10–0.30 is reasonable. 0 = maximum activity, faster wear.

### Learned charge rates

These auto-calibrate from Force Charge sessions. Visible under *Indstillinger → Lærte opladningshastigheder*.

- Range: 0.00–10 kW per slider
- Defaults: 1 kW (warm bucket); 0.5–0.8 kW (cold buckets)
- Effect: the maximum charge rate written to the inverter, by temperature bucket. The integration learns the actual achievable rate per bucket from observed Force Charge data.
- Buckets: `< 0`, `0–5`, `6–15`, `16–21`, `21–35`, `35–50`, `> 50 °C`
- Override only if learning produced a clearly wrong value (e.g. inverter firmware quirk).

---

## Switches

### Master controls

#### Arbitrage active — `arbitrage_aktiv`

The master switch. When off, the integration keeps reading data and updating sensors but does not change the inverter work mode or EVCC battery mode. Decisions are still reported (`would export`, `would grid-charge`) but not executed.

Use off during testing, during initial learning, or for manual control.

#### Notifications on mode change — `notifications_enabled`

When on, a persistent HA notification fires on every transition between Self-Use, Exporting, and Grid Charging modes. This is independent of the mobile push notifications below.

#### 15-minute price resolution — `price_resolution_15min`

When on, the 24-h price chart sensor emits one row per native 15-minute slot. When off (default), it deduplicates to one row per hour. The optimiser always uses native resolution internally regardless of this toggle.

### Notification events

Six toggles. All default to off. Each controls whether the corresponding event fires a mobile push notification.

| Switch | Fires when |
|---|---|
| `notify_export_start` | The integration transitions into EXPORTING mode (battery starts selling to the grid). This is different from passive solar export. |
| `notify_export_stop` | The integration exits EXPORTING. Notification includes session summary (start/end SoC, kWh exported, DKK earned). |
| `notify_charge_start` | The integration transitions into GRID_CHARGING (battery starts charging from the grid). |
| `notify_charge_stop` | The integration exits GRID_CHARGING. Includes session summary. |
| `notify_solar_floor_blocked` | Live sell price drops below `min_export_price`; export limit register flips from 10000 W to 25 W. |
| `notify_solar_floor_resumed` | Sell price recovers above the floor; export limit register flips back to 10000 W. |

### Notification devices

One toggle per registered HA Companion mobile device (auto-discovered from `notify.mobile_app_*` services). All default to off.

These select which devices receive the notifications enabled above. If no device is toggled on, no notification is sent regardless of the event switches.

---

## Changing settings after install

### Number entities and switches

All number entities and switches are on the *Indstillinger* tab of the bundled dashboard. Changes are saved instantly and apply on the next optimiser tick (within seconds for fast-loop parameters, within an hour for parameters that only affect the day-ahead plan).

### Setup-wizard fields (entity mappings, EVCC URL, source pickers, etc.)

*Settings → Devices & Services → Solar AI → Configure*. The Options form covers every wizard field. Save triggers an automatic reload — no HA restart needed.

### Battery thresholds at first startup

The first time the integration runs, battery thresholds (floor SoC, max SoC, etc.) are seeded from the wizard values. After that, the number-entity values take over and the wizard values are no longer consulted. To reset, use the Options form.

---

## Storage layout

Two distinct stores, for two distinct kinds of value:

| Stored in | Contents | Survives restart |
|---|---|---|
| `entry.data` (HA config entry) | One-time setup choices: EVCC URL, FoxESS entity IDs, currency, DSO, live-data source, solar forecast source | Yes |
| `_stored` (local JSON in HA storage) | Live-adjustable values: number entities, switches, learning models (charge rates, capacity samples, savings log, action log) | Yes |

Uninstalling and reinstalling the integration without removing the config entry preserves the learning models.

---

*Last updated for v0.28.x. If a setting is missing, file an issue.*
