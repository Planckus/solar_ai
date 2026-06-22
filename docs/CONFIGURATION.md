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
- [EV charging settings](#ev-charging-settings)
  - [Mode](#mode)
  - [Charge rate and priority](#charge-rate-and-priority)
  - [FoxESS Modbus tuning](#foxess-modbus-tuning-modbus-backend-only)
  - [Backend and connection](#backend-and-connection)
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

### EV charger backend

Set in *Configure → OCPP Settings*, also on the dashboard's **Advanced setup** page. The EV controller is opt-in (`ev_controller_enabled`, default off).

| Field | Description |
|---|---|
| `ev_charger_backend` | `ocpp` (default) or `foxess_modbus`. Which transport the EV controller uses to drive the charger. OCPP and Modbus are mutually exclusive at the charger — the mode is set in the FoxESS app. |
| `foxess_charger_host` | FoxESS charger IP/hostname (Modbus backend only), e.g. `192.168.x.x`. |
| `foxess_charger_port` | Modbus TCP port. Default `502`. |
| `foxess_charger_unit` | Modbus unit id. Default `1`. |
| `ocpp_embedded` | Whether the embedded OCPP server runs. Default on. It is the path for OCPP 1.6 chargers of any brand and stays available regardless of `ev_charger_backend`; toggling it reloads the integration. |

**Phases.** The OCPP backend is three-phase only, with a 4.14 kW minimum (6 A × 3) — the charger does not expose phase switching over OCPP. **Single-phase charging (down to ~1.4 kW) is only available on the `foxess_modbus` backend**, which selects single vs three-phase from the solar surplus by hysteresis (up ≥ 4.5 kW, down < 4.0 kW), gated by the charger's 5-minute suspend interval. The `ev_min_charge_kw` / `ev_max_charge_kw` dropdowns bound the per-phase current (6–16 A) within whichever phase is active.

**Control interval.** `ev_control_interval_seconds` (5–60 s, default 10) sets how often the controller re-evaluates and writes the charger setpoint. It is editable live from the Advanced setup page. On the Modbus backend it is the effective write/heartbeat cadence and must stay well under the charger's ~180 s setpoint-expiry window — any value in range is safe; lower is more responsive, higher means fewer Modbus writes.

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

## EV charging settings

These control solar-following EV charging. They apply on the next control cycle — no restart. Several are specific to the **FoxESS Modbus** charger backend and are greyed out on the OCPP backend.

### Mode

#### EV charging mode — `ev_active_mode`

- Options: **Locked** (no charging) · **Solar only** (charge from solar surplus) · **Solar + battery** (surplus, plus the house battery if needed) · **Full power** (charge at maximum, from the grid if the sun is short) · **Scheduled** (follow the schedule slots)
- Effect: the live charging mode. Resets to the *default mode on connect* each time a car is plugged in.

#### Default mode on connect — `ev_default_mode`

- Options: as above
- Default: Locked — safe; won't charge until you pick a mode
- Effect: the mode applied automatically when a car is plugged in.

### Charge rate and priority

#### Minimum / maximum charge rate — `ev_min_charge_kw` / `ev_max_charge_kw`

- Range: 6–16 A per phase
- Defaults: 6 A minimum, 16 A maximum
- Effect: bounds the per-phase current. On single-phase that is ~1.4–3.7 kW; on three-phase ~4.1–11 kW. Lower the maximum to cap how much the car ever draws.

#### Battery-first threshold — `ev_battery_priority_soc`

- Range: 50–100%
- Default: 80%
- Effect: in solar modes the car waits until the house battery reaches this SoC before taking solar surplus; above it, the car is prioritised over topping the battery further.
- Lower it: let the car start sooner. Raise it: fill the house battery first.

#### EV control interval — `ev_control_interval_seconds`

- Range: 5–60 s
- Default: 10 s
- Effect: how often the controller re-evaluates and re-asserts the charger setpoint.

### FoxESS Modbus tuning (Modbus backend only)

#### Three-phase switch threshold — `ev_modbus_upshift_kw`

- Range: 4.3–8.0 kW
- Default: 5.0 kW
- Effect: the rolling-average solar surplus at which the car switches to three-phase. Higher = commit to three-phase only on strong, steady sun (fewer switches); lower = engage three-phase at more modest surplus. It cannot go below 4.3 kW because three-phase needs 4.14 kW (6 A × 3) to run.

#### Charging current step — `ev_modbus_current_step`

- Options: 1.0 / 0.5 / 0.1 A
- Default: 1.0 A
- Effect: the resolution at which the per-phase current is set. Finer steps track the solar surplus more closely (less spilled to the grid), subject to whether the car's onboard charger follows sub-amp setpoints — some round to whole amps.

#### Phase-switch interval — `ev_modbus_suspend_interval_min`

- Range: 1–30 min
- Default: 1 min
- Effect: minimum time between phase switches (single ↔ three-phase). Lower = snappier phase response to changing sun; higher = calmer switching on broken-cloud days.

#### Override ramp step — `ev_override_ramp_interval_s`

- Range: 3–60 s
- Default: 12 s
- Effect: how fast the battery-full override ramps the car up toward the available curtailed-PV ceiling (when export is blocked and the house battery is full). Lower = reaches the ceiling faster, but probes the grid more aggressively.

### Backend and connection

#### Charger backend — `ev_charger_backend`

- Options: **OCPP** (embedded server, any OCPP charger) · **FoxESS Modbus TCP** (direct control, single- and three-phase solar following)
- Effect: which charger-control path is used.

#### Charger host — `foxess_charger_host`

- The FoxESS Modbus charger's IP address. Used only on the Modbus backend.

#### Embedded OCPP server — `ocpp_embedded`

- On/off. Runs the built-in OCPP server for OCPP chargers (Easee, Zaptec, Wallbox, etc.). Leave on for the OCPP backend.

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
