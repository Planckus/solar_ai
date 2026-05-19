# Changelog

All notable changes to **Solar AI** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [0.27.5] — 2026-05-19

UX fix to the "Overskud" value shown on the EV-styring dashboard card. Previously it showed the **physical** solar surplus (PV − non-EV house load), which is misleading when the house battery is below its priority threshold and absorbing the entire surplus — the card would say *"Overskud: 0.4 kW"* even though the EV has zero kW available.

### Fixed

- `ev_surplus_kw` in the EV-status telemetry now represents the **net surplus available to the EV** = `max(0, physical_surplus − battery_charge_now)`.
  - When the house battery is below the priority threshold (PV mode) and actively charging from solar surplus → `battery_charge_now` consumes everything, `ev_surplus_kw` reports `0`.
  - When the battery is at/above threshold (no longer charging) → `battery_charge_now` ≈ 0, `ev_surplus_kw` reports the full physical surplus.
  - When the battery is discharging (e.g. PV+battery mode feeding the EV) → `battery_charge_now` is clamped to 0, so `ev_surplus_kw` shows the full physical surplus.
- Live battery-charge reading comes from `CONF_BATTERY_CHARGE_ENTITY` (default `sensor.foxessmodbus_battery_charge`), so the value is real-time.
- **Controller logic untouched** — `_compute_ev_target_kw` still uses the physical surplus to make its decisions. Only the display value is corrected.

### Files touched

`coordinator.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.27.4] — 2026-05-19

Two real bugs found during the first live FULL-mode test: (a) the v0.27.2 battery-lock didn't actually engage — house battery drained while EV charged from grid, and (b) the v0.26.0 stop-window blocked mode changes for 180 s, making mode switches feel broken.

### Fixed — Battery lock actually works now

- v0.27.2's lock called `hass.services.async_call(..., blocking=False)` which silently swallowed any failure. If the entity didn't exist, the inverter ignored `0`, or the service call was malformed — we'd never know. Battery kept discharging through the EV's grid demand and drained.
- v0.27.4 rewrites `_set_battery_lock`:
  - **`blocking=True`** — failures raise, get logged at WARNING level, surface in system_log
  - **Entity-existence check** — log a clear error if `number.foxessmodbus_max_discharge_current` is missing
  - **Defence-in-depth** — additionally POSTs `batteryMode=hold` to EVCC's `/api/batterymode` endpoint when on EVCC live-data source. EVCC controls the inverter's battery mode via its own Modbus integration, so this is a redundant path that should work even if the direct number entity write fails.
  - **Detailed lock/unlock logging** — INFO-level message lists which mechanism(s) succeeded and which failed, e.g. *"battery LOCKED via [max_discharge_current 0 A (was 50.0); EVCC batteryMode=hold]"*

### Fixed — Time-windows only apply to PV mode

- v0.26.0's `start_window` (60 s) and `stop_window` (180 s) anti-flap windows existed solely to absorb cloud flicker on the solar surplus signal. But they fired on ALL transitions — including user-initiated mode changes via the dashboard. Result: user switches from Fuld kraft to Låst, expects immediate stop, instead waits 3 minutes while the car keeps charging.
- v0.27.4 narrows the windows to **PV mode only**. LOCKED / FULL / PV+battery modes now respond immediately to mode changes — no `ARMING` / `COOLING` state, no delay. Time-windows still apply within PV mode (their original intended scope).
- `ev_telemetry`'s `state` field only shows `ARMING` / `COOLING` when in PV mode now. Other modes show `IDLE` / `CHARGING` directly.

### Files touched

`coordinator.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.27.3] — 2026-05-19

Fixes the "after HA restart, charger data goes blank until the charger is power-cycled" problem. Most OCPP 1.6 chargers don't re-send `BootNotification` or `StatusNotification` on a plain WebSocket reconnect — they just resume `Heartbeat` messages. So after every HA restart, Solar AI's `sensor.solar_ai_lader_status` would sit at `Unknown` and vendor/model/serial would be empty, even though the WebSocket connection was healthy.

Two complementary fixes, layered.

### Added — `TriggerMessage` on charger (re)connect

- New `ChargePoint.request_status_refresh()` outbound method: sends OCPP `TriggerMessage` for `StatusNotification` and `BootNotification` immediately after a charger connects, asking the charger to re-emit those messages on demand.
- The `OcppServer` schedules this via `asyncio.create_task` 2 seconds after each connection arrives — long enough for the read loop to come up so `route_message` can dispatch the responses.
- Chargers that don't implement `TriggerMessage` are handled gracefully (DEBUG log, no error spam).

### Added — Persisted charger metadata across restarts

- New `_persist_charger_metadata()` coordinator method runs every main update tick, snapshotting each connected charger's `vendor`, `model`, `firmware`, `serial`, and `last_energy_wh_total` into `_stored["charger_metadata"][cpid]`.
- The dict is **shared by reference** with `OcppServer.persisted_metadata`, so updates from either side propagate without an explicit write.
- When a charger (re)connects, `OcppServer._handle_connection` pre-populates the new `ChargePoint` instance from this dict — so sensors light up *immediately* with the last-known identity, instead of waiting for the next status-changing event from the charger.
- `get_charger_telemetry()` falls back to persisted values when a field on the live `ChargePoint` is empty (i.e. the charger hasn't yet re-sent that data).
- Also captures metadata from a previous `ChargePoint` instance when the same CPID reconnects mid-session (so even an intra-session reconnect doesn't lose state).

### Combined behaviour after HA restart

```
T+0s   HA starts                                Solar AI sets up
T+1s   OcppServer.persisted_metadata loaded     md = {"charger": {vendor:"EV Charger", model:"L11P", ...}}
T+5s   Charger reconnects                       cp.vendor/model/serial pre-populated from md
                                                sensor.solar_ai_lader_status: "Unknown" (not blank!)
                                                sensor.solar_ai_lader_info: shows charger model + serial immediately
T+7s   TriggerMessage(StatusNotification)       Charger replies "Available"
                                                sensor.solar_ai_lader_status: "Available" (fresh!)
```

If the charger doesn't support `TriggerMessage`, the persisted snapshot keeps the dashboard sane until the next natural status change.

### Files touched

`ocpp_server.py`, `coordinator.py`, `__init__.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.27.2] — 2026-05-18

Two PV-mode behaviour fixes discovered during the user's first live charging test.

### Fixed — Battery-priority gate scope

The v0.26.4 battery-priority gate held the EV off whenever the house battery was below the threshold AND the mode was either `pv` OR `pv_battery`. The PV+battery case was wrong: the whole point of that mode is that the user has explicitly opted in to using the house battery to top the EV up to its minimum charge rate — gating that on "battery must be full first" contradicts the mode's intent.

- **Gate now only applies to `pv` mode** (Kun solenergi). Logic for `pv_battery` (use battery to fill the gap to min, but never below the floor SoC) is unaffected.

### Fixed — PV-mode fractional-surplus handling (floor-amps + excess-to-battery)

Previously `_kw_to_amps` rounded to the *nearest* whole amp. In PV mode that could overshoot the available surplus and silently pull the difference from grid or battery — defeating the "solar only" intent.

- **PV mode now floors to the next-lower whole amp**, so when surplus falls between two amp steps the fractional difference flows into the house battery instead of being grid-drawn.
- Example: 5.4 kW surplus → 7 A (4.83 kW) to EV, 0.57 kW to battery. Old behaviour: 8 A (5.52 kW) to EV, 0.12 kW drawn from grid.
- FULL mode and PV+battery mode keep nearest-rounding (FULL deliberately maxes out; PV+battery has its own battery-fallback logic).
- The reason string on `sensor.solar_ai_ev_status` now shows the excess flowing to the battery, e.g. *"PV: 5.40 kW overskud → 4.83 kW (7 A), 0.57 kW til batteri"*.

### Added — House-battery lock during EV grid-charging

Previously, in `Fuld kraft` mode the EV would happily pull max power from a mix of solar + grid + **house battery** (because Self Use mode lets the battery discharge to cover any load it sees). That contradicts user intent: when picking Fuld kraft, the user wants grid + solar, NOT to drain their house battery into the EV.

- **New**: when the EV controller is actively charging (`final_amps > 0`) AND the active mode is `Fuld kraft`, Solar AI writes **`0` A to `number.foxessmodbus_max_discharge_current`** — effectively blocking the house battery from discharging. The battery may still *charge* from solar surplus; only the discharge path is closed.
- **Released** automatically when the EV stops charging, the mode changes away from Fuld kraft, the EV disconnects, OR the integration is unloaded (so a HA restart mid-FULL-charge doesn't leave the battery stuck locked).
- Previous max_discharge_current value is captured and restored on release (defaults to 50 A if nothing was observed).
- New telemetry field: `battery_locked` on `sensor.solar_ai_ev_status` (attribute, surfaced for the dashboard).

### Files touched

`coordinator.py`, `__init__.py`, `sensor.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.27.1] — 2026-05-18

Hotfix to v0.27.0 — chargers that don't auto-start sessions (FoxESS L11PMC included) now actually charge. Discovered during the user's first live test with the EV plugged in and mode set to Fuld kraft: Solar AI correctly commanded `SetChargingProfile @ 16 A`, but the charger sat in `Preparing` status with 0.0 kW flowing. Root cause: in OCPP 1.6, `SetChargingProfile` only sets the upper limit for a transaction — to actually deliver power the CSMS must initiate the transaction via `RemoteStartTransaction`. Some chargers (Easee, KEBA) auto-start on plug-in; others (the L11PMC) wait for the CSMS.

### Added

- **`ChargePoint.remote_start_transaction(id_tag, connector_id)`** — sends OCPP `RemoteStartTransaction` to begin a charging session. 30-second cooldown to prevent spamming if the charger keeps responding without entering a `Charging` state. Returns `True` if charger replies `Accepted`.
- **`ChargePoint.remote_stop_transaction(transaction_id)`** — sends OCPP `RemoteStopTransaction` to end the current session. Used when the EV controller wants to stop charging while a transaction is active.

### Changed

- **EV controller's OCPP write logic** now goes beyond `SetChargingProfile`:
  - When the controller wants to charge (`final_amps > 0`) AND the charger is in `Preparing` / `SuspendedEV` / `SuspendedEVSE` AND no session is active → send `RemoteStartTransaction(idTag="solar_ai")`.
  - When the controller wants to stop (`final_amps == 0`) AND a session IS active → send `RemoteStopTransaction(transaction_id)`.
- Logic is **state-based**, not transition-based — survives HA restarts and integration reloads cleanly. If the controller is restarted mid-cycle with a plugged-in car and FULL mode, the next tick re-detects the missing transaction and sends RemoteStartTransaction.

### Files touched

`ocpp_server.py`, `coordinator.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.27.0] — 2026-05-18

**Major release. Solar AI now ships its own embedded OCPP 1.6 server** — no separate HACS integration required for OCPP-connected EV chargers. This eliminates an entire class of compatibility bugs (the v0.10.12 `lbbrhzn/ocpp` integration's `vol.Match` schema serializer crash, the duplicate-cpid registration mess, the strict-validation rejection of the FoxESS L11PMC's slightly off-spec frames) and brings EV control fully inside Solar AI's surface.

### ⚠️ Breaking change — uninstall lbbrhzn/ocpp first

If you previously installed the `lbbrhzn/ocpp` HACS integration to drive an OCPP charger from Solar AI, **uninstall it before upgrading**:

1. Settings → Devices & Services → OCPP → 3-dots → **Delete**
2. HACS → Integrations → **Open Charge Point Protocol (OCPP)** → Remove
3. Restart Home Assistant
4. Upgrade Solar AI to v0.27.0 (this release)
5. Solar AI's embedded OCPP server starts on port 9000 (configurable)
6. The L11PMC continues pointing at `ws://<ha-ip>:9000/<cpid>/` — no charger-side change needed

If you skip steps 1–3, Solar AI's embedded server will fail to bind port 9000 and log a clear "port in use, did you uninstall lbbrhzn/ocpp?" message. EV controller stays inactive until the conflict is resolved.

If you prefer to keep `lbbrhzn/ocpp` for some reason, toggle **"Use Solar AI's embedded OCPP server"** OFF in Step 2 of the OptionsFlow. Solar AI then falls back to reading lbbrhzn/ocpp's HA entities (same behaviour as v0.26.x).

### Added

- **`ocpp_server.py`** — new file (~460 LOC) hosting an embedded OCPP 1.6 server with:
  - `OcppServer` class managing the WebSocket lifecycle (start/stop, port binding)
  - `ChargePoint` class per connected charger with permissive parsing (skips schema validation, catches protocol errors, ignores malformed `'[]'` keepalive frames the L11PMC sends, doesn't tear down the connection on bad frames)
  - **Inbound handlers**: `BootNotification`, `Heartbeat`, `StatusNotification`, `MeterValues`, `Authorize` (accept-all on LAN), `StartTransaction`, `StopTransaction`, `DataTransfer`
  - **Outbound**: `SetChargingProfile` (sets connector max current; called by EV controller)
  - **5-minute disconnect grace period** — `effective_status()` reports `Disconnected` only when no contact in 300 s. Survives Wi-Fi router reboots, charger power-cycles, brief network glitches without flapping the sensor state.
- **7 new charger sensors** (Solar AI's namespace, replacing `lbbrhzn/ocpp`'s entities):
  - `sensor.solar_ai_charger_status` — Available / Preparing / Charging / Finishing / Faulted / Disconnected
  - `sensor.solar_ai_charger_power` — live charge power (kW)
  - `sensor.solar_ai_charger_session_energy` — kWh delivered this session
  - `sensor.solar_ai_charger_session_duration` — minutes since session start
  - `sensor.solar_ai_charger_lifetime_energy` — total kWh (TOTAL_INCREASING, eligible for HA Energy dashboard)
  - `sensor.solar_ai_charger_info` — vendor/model/firmware/serial + last-heartbeat timestamp
  - `sensor.solar_ai_charger_session_log` — state = total sessions count; attribute = last 20 paired start/end with energy, duration, avg power
- **Permissive parsing** — catches python-ocpp's `ProtocolError` exceptions on each inbound frame and continues the loop. Counts errors in `cp.protocol_errors` for diagnostic visibility without log noise.
- **Configurable port** — `CONF_OCPP_PORT` (default 9000, range 1024–65535) in the OCPP Settings step.
- **Embedded toggle** — `CONF_OCPP_EMBEDDED` (default `True`) in the OCPP Settings step. Lets advanced users opt out and use `lbbrhzn/ocpp` instead (the existing entity-override fields then come back into play).
- **3 new select entities** on the EV / OCPP dashboard tab:
  - `select.solar_ai_ev_minimum_opladningshastighed` — minimum charge rate as whole-amp dropdown (6 A through 16 A). Replaces the previous kW slider with cleaner amp-based selection. Display labels show both A and kW: *"6 A (4.14 kW)"*, *"7 A (4.83 kW)"*, etc.
  - `select.solar_ai_ev_maksimum_opladningshastighed` — maximum charge rate, same widget type.
  - `select.solar_ai_standard_ev_tilstand_ved_tilslutning` — default EV mode applied when a vehicle plugs in fresh (Låst / Kun solenergi / Min via sol + batteri / Fuld kraft). Live-changeable from the dashboard instead of buried in the OptionsFlow's OCPP Settings step. Stored in `_stored["ev_default_mode"]` with fallback to the config-entry value.
  - The legacy `number.*_opladningshastighed_kw` slider entities remain in place for backward compatibility (any automation that referenced them keeps working) but are no longer shown on the dashboard.

### Changed

- `coordinator.py`:
  - `_get_ocpp_status()` / `_get_ocpp_power_kw()` now read from the embedded server's `ChargePoint.effective_status()` / `power_w` when the embedded toggle is on; legacy HA-entity path retained for users on lbbrhzn/ocpp.
  - `_set_ocpp_charge_rate()` calls `ChargePoint.set_current()` directly via WebSocket instead of going through the `ocpp.set_charge_rate` HA service.
  - New `get_charger_telemetry()` builds a dict of `charger_*` fields merged into the result dict for the new sensors.
  - New `_harvest_ocpp_sessions()` picks up completed sessions from each ChargePoint and appends them to a 500-cap session log in storage. Same pattern as `solar_floor_log`.

### Migration

- **v14 → v15** — seeds `ocpp_embedded = True` and `ocpp_port = 9000` for existing installs. EV controller's existing behaviour is preserved otherwise.

### Files touched

`ocpp_server.py` (new), `coordinator.py`, `sensor.py`, `config_flow.py`, `__init__.py`, `const.py`, `translations/en.json`, `translations/da.json`, `strings.json`, `manifest.json` (new requirement: `ocpp>=2.1.0`), `CHANGELOG.md`, `README.md`.

---

## [0.26.4] — 2026-05-18

User-facing feature add: a **battery-priority threshold** that lets the user say "fill the house battery first up to X %, then divert solar surplus to the EV". Standalone slider, no other behaviour changes.

### Added

- **`number.solar_ai_ev_batteri_forst_taerskel`** (Battery-first threshold) — new live slider on the EV / OCPP dashboard tab. Range 50–100 %, default 80 %.
  - In **PV** and **PV+battery** modes, the EV controller returns `target_kw = 0` while `battery_soc < threshold` and reports reason *"Batteri prioriteret: 60% / 80% — EV venter til batteri er fyldt"*. The inverter naturally diverts solar surplus into the house battery during this hold.
  - Once `battery_soc ≥ threshold`, the controller resumes normal surplus tracking and the EV starts charging.
  - **FULL** mode ignores the threshold (user wants max charge regardless of battery state).
  - **Låst** mode unaffected (already 0 by definition).
  - Persisted via the coordinator's `_stored` dict (live-adjustable, survives HA restart).
- New coordinator method `set_ev_battery_priority_soc(value)` for the slider entity to call.

### Migration

- **v13 → v14** — seeds `ev_battery_priority_soc = 80` for existing installs. Behaviour change is opt-in: users who want the old "EV competes with battery immediately" behaviour can drag the slider down to their floor SoC (e.g. 50 %).

### Files touched

`const.py`, `coordinator.py`, `number.py`, `__init__.py`, `config_flow.py`, `translations/en.json`, `translations/da.json`, `strings.json`, `manifest.json`, `CHANGELOG.md`.

---

## [0.26.3] — 2026-05-18

Self-healing patch for the OCPP entity override fields. Discovered during the first live EV-controller test session: when the user changed the CPID, the auto-derived status/power entity overrides (e.g. `sensor.<your-cpid>_status`) became stale and pointed at entities that no longer exist. Clearing them via OptionsFlow didn't actually remove them from the saved config (a separate OptionsFlow bug yet to be addressed). End result: Solar AI's EV controller reported "Unavailable" forever, even after the charger reconnected.

### Fixed

- **Self-healing OCPP entity override**. New helper `_resolve_ocpp_entity()` is used by both `_get_ocpp_status()` and `_get_ocpp_power_kw()`. If the user-set override points to an entity that doesn't exist in HA's state registry, the override is silently ignored and the coordinator falls back to the auto-derived name (`sensor.<cpid-lowercase>_status` / `sensor.<cpid-lowercase>_power_active_import`). Logs a debug line so the behaviour is traceable. This makes stale override values harmless — users no longer need to manually clear override fields after changing CPID.
- Translation label for `ev_ocpp_charge_point_id` still misleading (says "what the charger announces, e.g. <your-charger-serial>"). Should be re-worded to clarify it's the **CPID configured in the OCPP integration**, not the charger's announced serial. Deferred to a future patch — not strictly blocking.

### Files touched

`coordinator.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.26.2] — 2026-05-18

Patch follow-up to v0.26.1 fixing a startup-phase warning that v0.26.0 introduced when the decoupled EV control loop was added.

### Fixed

- **EV control loop no longer blocks HA's startup phase.** The previous implementation registered the loop via `hass.async_create_task`, which HA's bootstrap waits for during the startup phase — and an `await asyncio.sleep` inside a `while True:` loop never completes, so HA logged *"Something is blocking Home Assistant from wrapping up the start up phase"* every restart. Switched to `hass.async_create_background_task` (with a name argument) which is the supported way to register long-running tasks that the bootstrap should not wait on. No functional change; cleaner logs and faster startup.

### Files touched

`coordinator.py`, `manifest.json`, `CHANGELOG.md`.

---

## [0.26.1] — 2026-05-18

Follow-up to v0.26.0 that surfaces the new time-based hysteresis to the user. The controller had been computing `ev_state`, `ev_arming_seconds_left`, and `ev_cooling_seconds_left` since v0.26.0 but no sensor exposed them — so the dashboard could not show *why* the controller was being patient during cloud-flicker. This release wires those fields into a dedicated sensor and adds a Mushroom card to the EV / OCPP dashboard tab.

### Added

- **`sensor.solar_ai_ev_status`** — primary state machine indicator (IDLE / ARMING / CHARGING / COOLING) with the following attributes:
  - `arming_seconds_left` — countdown until charging starts (during ARMING)
  - `cooling_seconds_left` — countdown until charging stops (during COOLING)
  - `active_mode`, `target_kw`, `target_amps`, `surplus_kw`, `last_commanded_amps`, `reason`, `enabled`
- Translations (en, da, strings) for the new sensor name.

### Changed

- **Dashboard tab order**: the EV / OCPP tab moves from position 6 (rightmost) to position 2 (second from the left). New order: Oversigt / EV / OCPP / Priser & Plan / Historik / Indstillinger / Logs.
- **EV / OCPP dashboard tab** gains a Mushroom template card rendering the new sensor — *"Starter om 23 sek"* during ARMING, *"Stopper om 142 sek"* during COOLING, *"Oplader: 4.2 kW"* during CHARGING.

### Files touched

`sensor.py`, `translations/en.json`, `translations/da.json`, `strings.json`, `manifest.json`, `CHANGELOG.md`, plus the live Lovelace dashboard via WebSocket.

---

## [0.26.0] — 2026-05-18

This release reworks the EV charge controller so behaviour can be tuned to match any OCPP charger's response time, and so the start/stop anti-flap windows are configurable in seconds (not coordinator ticks). The controller now runs in its own asyncio task at a user-set cadence, decoupled from the main fast-poll. The EV "really charging" power threshold also becomes user-configurable. README polish: the inaccurate "every 5 minutes" claim is corrected to the actual 30 s default (10–300 s range).

### Added — Configurable EV control loop (time-based hysteresis)

- New **OCPP Settings** fields:
  - **Control loop interval** (5–60 s, default 10 s) — how often the EV controller re-evaluates surplus and adjusts the charge rate. Independent of the main coordinator fast-poll, so you can pick a cadence that matches your charger's OCPP write tolerance.
  - **Start window** (10–600 s, default 60 s) — solar surplus must hold ≥ minimum charge rate for this long before charging starts. Stops a passing cloud from triggering a stuttering session.
  - **Stop window** (30–1800 s, default 180 s) — solar surplus must stay below the minimum for this long before charging stops. After stop, a new start requires another full start-window of sustained surplus.
  - **EV charging detection threshold** (500–10 000 W, default 3 000 W) — above this power level, Solar AI treats the EV as truly charging (used by the grid-charge gating, hourly-pattern learner, and max-kW learner).
- **Decoupled control loop**: a dedicated `asyncio.Task` calls `_run_ev_controller` at the configured cadence; the main coordinator update only caches inputs. The loop is started in `async_setup_entry` and cancelled in `async_unload_entry`.
- **Time-based hysteresis** (`_apply_ev_time_window`) replaces the previous 2-tick counter. Timestamps mark when surplus crossed above/below the minimum-charge threshold; transitions fire only after the elapsed seconds exceed `start_window` / `stop_window`. Cancelling the opposite-side timer on each crossing prevents start/stop oscillation.
- **New telemetry**:
  - `ev_state` — `IDLE` / `ARMING` / `CHARGING` / `COOLING`
  - `ev_arming_seconds_left` — countdown until charging starts
  - `ev_cooling_seconds_left` — countdown until charging stops
  - Lets the dashboard render *"Starter om 23 sek"* or *"Stopper om 142 sek"* instead of just the binary state.

### Changed

- The 3 hard-coded `EV_CHARGE_THRESHOLD_W = 3000` references in `coordinator.py` are now read via `self._ev_charge_threshold_w()`, which honours the user-set value with the 3 000 W default as fallback.
- Plug-in event and `set_ev_mode` now reset the new timestamp-based timers, not just the legacy tick counters.
- README: "Every 5 minutes (configurable)" → **"Every 30 seconds (configurable, 10–300 s)"**. The actual default has always been 30 s; the README's claim of 5 minutes confused the max with the default.
- README: "Real charging detection" + "EV on Solar sensor" lines updated to call out that the 3 000 W threshold is now configurable.

### Migration

- **v12 → v13** — seeds the four new EV control settings with their defaults for existing installs. Existing behaviour is preserved: 60 s start window matches the previous *2-tick × 30 s* hysteresis exactly, and 180 s stop window is a slight relaxation (was 60 s) that gives passing-cloud tolerance. Users who want the old aggressive stop behaviour can dial the stop window back to 60 s.

### Files touched

`const.py`, `coordinator.py`, `config_flow.py`, `__init__.py`, `translations/en.json`, `translations/da.json`, `strings.json`, `manifest.json`, `README.md`, `CHANGELOG.md`.

---

## [0.25.5] — 2026-05-17

This release bundles several layers of new functionality: Phase B1 (the EV charge controller), adaptive solar learning, two new persistent logs, a redesigned 3-step OptionsFlow, and device-registry-aware entity discovery. The intermediate v0.25.1–v0.25.4 versions are folded into this release because they were all bug-fixes/iteration on top of v0.25.0 features and never shipped externally.

### Added — Phase B1: OCPP-driven EV charge controller (opt-in)

- **4 charging modes** selectable via `select.solar_ai_ev_mode`:
  - **Låst** — no charging
  - **Kun solenergi** — solar surplus only; stops below minimum
  - **Min via sol+batteri** — tops up to minimum with battery; never grid
  - **Fuld kraft** — max charge rate from any source
- **Dynamic surplus tracker** — ramps the OCPP current setpoint between 4.14 kW (3-phase 6 A) and 11 kW (3-phase 16 A) every coordinator tick, adapting in real-time to solar variation
- **Anti-flap hysteresis** — 2-tick (60 s) confirmation window before start/stop transitions; 2 A max ramp per tick; 1 A minimum change to trigger an OCPP write
- **User-pickable default mode** that takes effect when a vehicle plugs in fresh
- **Min/max charge rate sliders** (defaults: 4.14 / 11.0 kW for 3-phase 16 A)
- **5 visibility sensors**: `ev_target_kw`, `ev_target_amps`, `ev_surplus_kw`, `ev_active_mode`, `ev_reason`
- **Opt-in toggle** — feature is OFF by default. Existing installs see no behaviour change until the user explicitly flips `Enable EV charge controller (OCPP)` in Options.

### Added — Dedicated OCPP Settings pane in OptionsFlow

OptionsFlow restructured into 3 steps: Parameters → **OCPP Settings** (new) → Entity Mapping. The new pane consolidates everything Solar AI needs to drive an OCPP-connected charger:

- Master enable toggle (off by default)
- OCPP charge point ID (what the charger announces, e.g. `<your-charger-serial>`)
- Optional status / power sensor entity overrides (auto-derived from the charge point ID)
- Default EV mode on plug-in

### Added — Adaptive per-hour solar forecast correction

- **24 hour-of-day accuracy buckets** — Solar AI now learns a separate forecast→actual ratio for each hour, instead of one global ratio. Captures the shape difference between forecast and reality (e.g. east panels under-shoot afternoon forecasts) **without the user telling Solar AI anything about panel count, orientation, tilt, or shading**.
- Optimizer applies hour-specific factor per slot when building DP input; falls back to the global ratio for hours with fewer than 8 daylight samples.
- **Self-tuning** — ~7 days of daylight observations to fully populate the buckets. No configuration required.
- **`sensor.solar_ai_solar_hourly_learning`** exposes the 24 learned factors + sample counts as attributes. State = number of hours warmed up (0–24).

### Added — Solar floor event log

- **`sensor.solar_ai_solgulv_log_blokering`** — persistent record of every time the solar export floor activated and resumed. Paired block→resume sessions with `start_ts`, `end_ts`, `duration_min`, `price_at_start`, `price_at_end`, `floor`. State = total event count; last 20 events as the `events` attribute. Up to 500 entries retained.

### Added — Device-registry-aware entity discovery

- **New `discovery.py` module** finds FoxESS Modbus entities by their stable `unique_id` suffix rather than hard-coded `entity_id` strings. Survives entity renames, multi-inverter installs, language packs, and integration version changes.
- Setup wizard now uses discovery to pre-fill every FoxESS entity field. New users with a default FoxESS Modbus install go from "12 manual entity dropdowns" to "all fields pre-filled correctly".

### Added — Configuration reference doc

- **`docs/CONFIGURATION.md`** — every slider, switch, and setup-wizard field explained in plain English: what it controls, its range and default, and concrete advice on when to change it. Linked from the README.

### Added — Dashboard

- **New "EV / OCPP" tab** on the dashboard exposing the mode selector, live target / surplus values, min/max sliders, EV-connection status, and a pointer to the OCPP Settings pane.
- **New "Logs" tab** consolidating the Session log, Solar floor block log, and Savings totals in a single place.

### Fixed

- **Solar floor log missed blocks that were active at HA startup.** Original logic only opened a block on a `10000 → 25` transition, but in-memory state resets to `-1` on every restart. Fixed to track any entry/exit of the floor-active state (limit == 25), regardless of where it transitions from. Notifications still only fire on direct `10000 ↔ 25` to avoid noise during grid-charge transitions.
- **OptionsFlow refused to submit when Forecast.Solar / Solcast entity fields were left blank.** The schema's `default=""` was being validated by the EntitySelector as "neither valid entity ID nor valid UUID". A new `_entity_optional` helper omits the default when no value is saved; combined with HA's frontend treating null/empty as absent for `vol.Optional`, the form now submits cleanly. Same fix applied to the setup-wizard solar source step and the OCPP Settings step's status/power entity overrides.

### Migrations

- **v9 → v10** seeds `live_data_source = "evcc"` for existing installs (v0.24.0 carry-over)
- **v10 → v11** seeds `ev_default_mode = "locked"`
- **v11 → v12** seeds `ev_controller_enabled = false`

### Setup requirements (one-time, only when EV controller is enabled)

- Requires the [lbbrhzn/ocpp](https://github.com/lbbrhzn/ocpp) HA integration installed
- L11PMC's OCPP backend must be repointed from EVCC to `ws://<ha-ip>:9000/<charger-id>/`
- EVCC must release the OCPP socket (stop the loadpoint or stop EVCC entirely)

---

## [0.24.0] — 2026-05-16

### Added — Phase A: EVCC becomes optional

The integration can now run without EVCC. A new first step in the setup wizard (and a new field in the Options menu for existing installs) lets you pick the **live data source**:

- **EVCC** — everything from EVCC (default; behaviour unchanged for existing installs)
- **Hybrid** — FoxESS sensors for live grid/PV/load, EVCC for EV state (loadpoints + battery mode)
- **FoxESS only** — no EVCC at all. Solar AI reads grid/PV/load from FoxESS Modbus sensors. No EV detection, no EVCC battery-mode coordination.

#### Solar forecast source expanded

Solcast HA integration is now supported as a direct source (in addition to EVCC and Forecast.Solar). The Auto fallback chain becomes EVCC → Forecast.Solar → Solcast. FoxESS-only installs see only the non-EVCC options in the dropdown.

#### Hard safety check for FoxESS-only mode

Selecting FoxESS-only forces the user to read a clear warning and tick a hard acknowledgement: *"I have no EV, or my EV charger is configured to avoid the house battery."* This is non-skippable because without EV charge detection the battery could grid-charge concurrently with EV charging, potentially overloading the mains breaker.

#### Hybrid mode resilience

When in Hybrid mode, if EVCC is unreachable on a tick, the integration logs a warning and continues with the FoxESS-derived live state and empty loadpoints — instead of dropping the whole entity. EVCC-only mode keeps its existing hard-fail behaviour.

#### v9 → v10 schema migration

Existing installs are automatically migrated with `live_data_source = "evcc"` so behaviour is unchanged unless explicitly switched.

---

## [0.23.0] — 2026-05-16

### Added

- **Solar forecast source picker** — the integration no longer has to read the solar forecast from EVCC/Solcast. A new config-flow step lets you choose between:
  - **EVCC** (default — unchanged behaviour, Solcast under the hood)
  - **Forecast.Solar** — the native HA integration. Solar AI reads the per-hour `watts` attribute from a user-picked sensor (typically `sensor.energy_production_today`) and converts it to the same internal format.
  - **Auto** — try EVCC first; fall back to Forecast.Solar if EVCC fails or returns empty.

  Existing installs are migrated automatically to source = EVCC, so behaviour is unchanged unless you explicitly change it. The new option is also available in the integration's Options menu (Settings → Devices & Services → Solar AI → Configure).

- **Solar export floor notifications** — two new mobile push toggles for when the integration blocks solar export (because the live sell price has dropped below your `min_export_price` floor) and when it resumes:
  - "Notifikation: solareksport blokeret (prisgulv)"
  - "Notifikation: solareksport genoptaget"

  These cover a behaviour that was previously silent — the export-limit register would flip between 25 W and 10 000 W based on price, with no log entry or notification. Both toggles default to off; enable per device in the Notifikationer card.

### Fixed

- **OptionsFlow now actually applies changes.** Before this release, the Options form saved values to `entry.options` but the coordinator only read from `entry.data`, so OptionsFlow edits to floor/max SoC, efficiency, currency, polling interval, and DSO were silently ignored. The OptionsFlow now writes back to `entry.data` directly so changes take effect after the automatic reload. If you've ever changed something in the Options menu and noticed it didn't apply — it will now.

### Removed

- **Dead config field `min_solar_export_price`** — defined in `const.py` and seeded into `entry.data` by the migration, but never read anywhere. The actual minimum export price floor is and remains controlled by the `min_export_price` slider, which is wired up correctly. Removing the dead constant is a no-op for behaviour.

---

## [0.22.1]

### Changed

- **Minimum gevinst pr. kWh slider range widened back to 0.00–3.00 DKK/kWh** (was 0.00–0.50 in v0.22.0). The tighter v0.22.0 range turned out to be too restrictive for setups that want a higher safety margin. The previous one-time migration that clamped stored values above 0.50 has been removed; existing values are now preserved as-is.
- **Dashboard restructured into 4 tabs** — Oversigt / Priser & Plan / Historik / Indstillinger. All 82 existing entities preserved, just reorganised so the daily-use overview is clean and configuration/diagnostics are tucked under the Indstillinger tab. No code changes; the dashboard YAML in `dashboard/dashboard_da.yaml` has been updated and the live Lovelace config on HA was updated via the WebSocket API.
- **Mushroom Cards added as an optional dashboard dependency** ([github.com/piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom)) — used for the status chips and large tiles on the Oversigt tab. Install via HACS → Frontend before importing the dashboard.

---

## [0.22.0] — 2026-05-16

### Changed — Optimizer rewrite (more accurate, more far-sighted)

This is a meaningful upgrade to the day-ahead DP optimizer. The decision quality should improve noticeably on days with large price spreads and especially in the last few hours of each day. Five things changed:

1. **Native 15-minute resolution** — the optimizer now solves directly at the Nord Pool day-ahead grid (15-min slots) instead of averaging 4 slots into an hourly bucket. Short evening price spikes that only last 15–30 minutes are now visible to the planner. Solving time is still well under 100 ms even at the longer 48-h horizon.
2. **48-hour horizon when available** — once tomorrow's day-ahead prices are published (around 13:00 CET each day), the optimizer plans across the full ~48-hour window instead of cutting off at hour 24. This lets it pre-charge tonight for tomorrow's morning peak, etc.
3. **Terminal value at horizon end** — previously the model assigned zero value to whatever SoC remained at the end of the planning window. That caused unnecessary discharge in the last few slots. The new terminal value `(remaining usable kWh) × discharge_eff × expected_sell_price` ensures the battery preserves usable charge into the next day.
4. **Forward-only spread check** — the "is this export profitable?" gate previously used the cheapest buy price *anywhere* in the planning window, which was overly optimistic for late-day exports (no cheap recharge available after them). The check now uses the cheapest buy *after* the candidate export slot only.
5. **Battery degradation cost** — every CHARGE and EXPORT decision now pays a small per-kWh cycle cost (default **0.10 DKK/kWh**, configurable via a new number entity). This stops the model from approving thin arbitrage that doesn't cover the wear it causes. Calibrated for residential LFP at ~2000 DKK/kWh installed cost using marginal-wear literature.
6. **Solar accuracy correction applied to optimizer input** — previously the learned solar accuracy factor (rolling median of actual/forecast ratio) was used only on display sensors. The DP planned against raw Solcast forecasts, which meant a systematic 20–30 % overshoot would lead the optimizer to assume more solar coverage than would actually arrive. The factor is now applied per slot inside the DP.
7. **House grid-import cost at floor** — when battery SoC sits at floor and house load exceeds solar, the deficit is imported from the grid at the current buy price. Previously the DP didn't see this cost and effectively treated it as free. The new model adds it explicitly, making strategic CHARGE actions more attractive when high-buy hours are expected later in the day.
8. **Solar overflow export revenue when full** — symmetric fix: when SoC sits at max and solar exceeds house load, the surplus is exported at the current sell price. The DP now counts this revenue, which makes strategic pre-emptive EXPORT (to make room for incoming solar) more attractive.

### Added

- **Battery wear cost setting** — new number entity `Batteri-slidomkostning` lets you tune the per-kWh degradation cost between 0.00 and 1.00 DKK/kWh. Default 0.10. Increase if you want the system to take fewer cycles; decrease (or set to 0) for maximum arbitrage activity.

### Changed

- **Minimum arbitrage spread slider** retuned for the new economic model. Range is now **0.00–0.50 DKK/kWh** in 0.05 steps (was 0.10–3.00), default lowered to **0.30**. With explicit degradation cost and efficiency losses now priced inside the DP, the old 1.0 default was effectively double-counting and blocking legitimate multi-cycle days. Existing installs with stored values above 0.50 are migrated down to 0.50 to keep the slider and the optimizer in sync.

---

## [0.21.5] — 2026-05-16

### Added

- **Configurable push notifications** — four new toggle switches let you choose exactly which events trigger a push notification on your iPhones (via the HA Companion app): export started, export stopped, charging started, charging stopped. Each toggle is independent — enable only the events you care about. A separate toggle is created automatically for every registered HA Companion device (iPhone, iPad, etc.) so you can pick exactly which devices receive the notifications.
- **Session log end time** — the Sessionslog dashboard card now shows both the start time and end time ("Slut") for each session, making it easier to see how long each export or charge window ran.

---

## [0.21.4] — 2026-05-16

### Added

- **Session log** — Solar AI now records every export and grid-charge session with a full summary: start and end time (Copenhagen local), SoC range (start → end %), duration in minutes, estimated kWh moved, and revenue/savings in DKK. Sessions are logged on each mode transition and stored persistently across restarts (up to 500 entries). A new `sensor.solar_ai_session_log` entity exposes the count of total logged sessions as its state and the 20 most recent sessions as a `sessions` attribute. A dashboard markdown card shows the last 15 sessions in a table.

---

## [0.21.3] — 2026-05-16

### Fixed

- **Integration fails to start when EVCC solar forecast endpoint is unavailable** — if EVCC's `/api/tariff/solar` returns 404 or any error on the first coordinator run, the integration entered `setup_retry` and all entities became unavailable. Solar forecast data is now fetched with independent error handling: a failure logs a warning and falls back to cached/empty data, without blocking the price fetch or startup. EDS spot prices and the optimizer continue to work normally.

---

## [0.21.2] — 2026-05-16

### Fixed

- **Sensor device class warning** — removed `device_class=ENERGY` from 10 forecast and snapshot sensors that represent estimated or available kWh values rather than cumulative energy meter readings (`solar_forecast_24h`, `solar_forecast_6h`, `solar_forecast_24h_adjusted`, `solar_forecast_6h_adjusted`, `predicted_load_24h`, `exportable_kwh`, `importable_kwh`, `net_solar_for_battery`, `solar_28d_avg`, `learned_capacity`). HA requires `state_class=total` or `total_increasing` when `device_class=energy` is used; since these sensors are not energy meters, the correct fix is to drop the device class. Units (`kWh`) and `state_class=measurement` are unchanged.

---

## [0.21.1] — 2026-05-16

### Fixed

- **EDS price source** — switched from the discontinued `Elspotprices` dataset (last updated 2025-09-30) to the current `DayAheadPrices` dataset. Field names updated: `TimeDK` (was `HourDK`) and `DayAheadPriceDKK` (was `SpotPriceDKK`). The new dataset has 15-minute resolution; the optimizer already averages slots within each hour so behaviour is unchanged. Fetch limit increased to 192 slots (4 × 48 hours) to cover today + tomorrow. This was the cause of the "no records returned" warning seen immediately after v0.21.0 was deployed.

---

## [0.21.0] — 2026-05-15

### Added

- **Day-ahead dynamic programming optimizer** — the core decision engine has been rebuilt. Instead of comparing the current price to a 24-hour percentile and acting reactively, Solar AI now runs a backward-induction DP over all 24 future hourly slots every time prices refresh. The state is battery SoC at 1 % resolution (101 states) and the actions are CHARGE, EXPORT, or IDLE. The optimizer finds the globally optimal multi-cycle sequence — e.g. "charge at 02h and 03h, export at 11h and 17h" — by accounting for round-trip efficiency, house load, solar forecast, EV charging likelihood, and all pricing costs in one computation. The resulting plan drives `should_export` and `should_grid_charge`; all existing safety guards (SoC bounds, EV active-charging lock, EVCC override, minimum export price floor, grid headroom cap) remain as hard constraints on top.

- **Per-hour house load profile learning** — alongside the existing 2h/28d rolling averages, Solar AI now maintains a 24-slot daily load profile: one learned kW value per hour of day, updated via exponential moving average with ~8-day memory per slot. The optimizer uses this profile to estimate per-slot battery drain from house load instead of a flat 24h estimate, significantly improving the accuracy of multi-cycle charge/export planning (e.g. correctly accounting for morning and evening demand peaks). Two-layer outlier guard: hard ceiling at `grid_max_kw` (physical limit) + soft ceiling at 5× the current estimate once the model is warm (rejects sensor spikes without blocking genuine large loads). Exposed as the **"House load — learned (this hour)"** sensor; full 24-slot profile is in the sensor's `profile_kw` attribute.

- **EV max charge rate learning** — a new season-independent single-value model learns the car's maximum AC charge rate (~20-sample EMA). Only full-speed sessions (≥ 80 % of current learned max) are included, so summer solar-throttled sessions do not drag the estimate down. The learned value is used by the optimizer to estimate how much solar the EV will consume per hour, giving the battery an accurate picture of net solar surplus. Exposed as the **"EV max charge rate (learned)"** sensor.

- **Energi Data Service spot price source** — spot prices are now fetched directly from the [Energi Data Service](https://api.energidataservice.dk) `DayAheadPrices` dataset (Nord Pool day-ahead, 15-min resolution, DKK/MWh → DKK/kWh) instead of EVCC's `/api/tariff/grid` endpoint. This removes the dependency on EVCC for price data and resolves the issue where EVCC returned zero rates. Copenhagen CET/CEST timezone conversion is handled correctly year-round. Today + tomorrow (up to 192 slots) are fetched in one call. EVCC grid tariff is kept as an automatic fallback if EDS is unreachable. Price zone defaults to DK2 (eastern Denmark); change via `CONF_PRICE_AREA` in `const.py` for DK1.

### Changed

- **Decision logic driven by optimizer plan** — `should_export` now requires the optimizer to have recommended EXPORT for the current hour (instead of checking `price ≥ p75` reactively). `should_grid_charge` now requires the optimizer to recommend CHARGE (instead of checking `buy price ≤ p25`). The reactive thresholds remain as a fallback before the first optimizer run (first hour after startup). All physical and EVCC safety guards are unchanged.

- **"Today's plan" sensor updated** — charge and export hours now come directly from the optimizer's output plan rather than a simple sorted-price greedy heuristic. The plan correctly accounts for multi-cycle scenarios where the cheapest charge slot is not necessarily the first slot of the day.

- **Minimum spread check in optimizer** — the DP EXPORT action is only allowed when `sell_price − best_24h_buy / efficiency ≥ min_spread`. This ensures the user-configured minimum spread threshold is respected in the plan, not just at execution time.

- **Outlier protection on both learning models** — house load profile and EV max rate both apply a two-layer guard on every learning tick: (1) hard physical ceiling at `grid_max_kw` — no real load can exceed the breaker; (2) soft ceiling at 5× the current estimate once the model is warm — rejects measurement spikes while allowing genuine large loads through.

---

## [0.20.1] — 2026-05-15

### Fixed
- **Dashboard switch entity ID** — the 15-minute price resolution toggle in the dashboard templates (`dashboard_da.yaml`, `dashboard_en.yaml`) referenced the wrong entity ID (`switch.battery_arbitrage_price_resolution_15min`). Corrected to the actual entity ID assigned by HA (`switch.solar_ai_15_minutters_prisoplosning`). The live dashboard was also patched with this fix and the 24h price chart section that was missing from it.

---

## [0.20.0] — 2026-05-15

### Added
- **15-minute price resolution** — a new switch entity "15-minute price resolution" controls the granularity of the 24h price chart. When on, the chart emits one row per native DSO slot (typically 15 minutes, showing HH:MM timestamps and up to 48 rows for the next 12 hours). When off (default), the chart shows one row per hour as before. The toggle appears directly above the price chart on the dashboard.

### Changed
- **Arbitrage model uses native slot resolution throughout** — the house drag cost and solar offset calculations now operate on the actual DSO slot granularity (15-min or hourly, whatever EVCC provides). Previously all calculations assumed 1-hour slots, which underestimated drag in 15-minute markets. Slot durations are derived automatically from the gap between consecutive EVCC forecast slots.
- **Per-slot solar forecast in drag model** — the house load drag calculation now uses the actual per-slot solar forecast (Watts from EVCC) to offset house load for each individual slot, rather than a flat `solar_kwh / 24` average. This means drag cost is lower during daylight hours (solar covers the house) and correctly zero-adjusted at night.

---

## [0.19.0] — 2026-05-15

### Changed
- **Arbitrage spread model now accounts for house load drag and round-trip efficiency**

  Previously the spread was simply `export_price − buy_price_min`, which ignored two real costs:

  1. **Round-trip losses on the recharge**: to restore what we sold we must buy more kWh than we exported. The recharge cost is now `buy_price_min ÷ round_trip_efficiency` instead of `buy_price_min` flat.

  2. **House load drag**: while the battery is depleted (from now until the cheapest recharge slot), the house must buy from the grid instead of drawing from the battery. The model now calculates this cost hour by hour using the actual forecast buy prices for each hour in the drag window, offset by expected solar production (`solar_forecast_24h ÷ 24` per hour). The drag cost is divided by the exportable kWh to get a per-kWh penalty that is subtracted from the spread.

  The temperature-adaptive learned charge rate determines how quickly the battery can recover once charging starts, and the drag window ends precisely when the cheapest charge slot begins.

  Net effect: the model will be more conservative — it will decline exports whose headline spread looked attractive but whose actual net profit (after recharge cost and grid house load during depletion) is below the minimum spread threshold.

---

## [0.18.3] — 2026-05-15

### Changed
- **Removed minimum spread and minimum solar export price from setup wizard and options flow** — both values are controlled exclusively via number entities on the dashboard and were redundant in the config flow. Existing values are preserved; the number entities remain the single source of truth.

---

## [0.18.2] — 2026-05-15

### Fixed
- **Options flow description clarified** — page 1 now reads "Press Submit to map your inverter and battery sensor entities on the next page." so users know exactly what to do to reach the entity mapping step.

---

## [0.18.1] — 2026-05-15

### Fixed
- **Options flow — entity mapping now discoverable** — the Parameters page (step 1 of 2) now shows a description: "Step 1 of 2 — Submit to continue to entity mapping →". Previously users had no indication a second page existed.

---

## [0.18.0] — 2026-05-15

### Added
- **Configurable entity mapping** — Solar AI no longer requires FoxESS Modbus entity IDs to be hardcoded. All six battery sensor entities (SoC, cell temperature, charge power, discharge power, lifetime charge total, lifetime discharge total) can now be mapped to any HA sensor during setup or changed later via the integration's Options flow. The setup wizard now has a dedicated "Battery Sensor Entities" step with HA entity pickers for each sensor. The three inverter control entities (work mode, force charge power, force discharge power) likewise now use entity pickers instead of plain text fields. Existing installs are automatically migrated at startup — they receive the FoxESS Modbus defaults and work without any manual intervention. This is the foundation for using Solar AI with non-FoxESS inverters or custom sensor naming.

### Changed
- Config entry schema version bumped 7 → 8 to accommodate the new sensor entity keys.
- Setup flow: "FoxESS Inverter Entities" step retitled to "Inverter Control Entities"; inverter control fields now use HA entity pickers (select/number domain filters). A new "Battery Sensor Entities" step follows it with sensor entity pickers.
- Options flow: a second page ("Entity Mapping") is now reachable from the options menu, listing all 10 entity fields (inverter ID + 3 control + 6 sensors) for post-install changes.

---

## [0.17.0] — 2026-05-15

### Changed
- **Solar export blocked below minimum export price floor** — Solar AI now writes the FoxESS export limit register (46616) directly on every poll tick, not just on mode transitions. When the net export price is at or below your configured floor, the limit is set to 25 W — effectively blocking solar panel export as well as battery export. When above the floor it is set to 10 000 W. During grid charging it is always set to 0 W (unchanged behaviour). This matches the behaviour of the legacy `FoxESS - Export Limit by Spotprice` automation that Solar AI was previously disabling. The floor is enforced even when Solar AI's arbitrage switch is off. The register is only written when the limit value actually changes, to avoid unnecessary wear.
- **README updated** — export floor section and decision loop updated to reflect the 25 W solar blocking behaviour.

---

## [0.16.2] — 2026-05-15

### Changed
- **README fully updated** — documents all features added since v0.11.2: negative price guard, 24h price chart, tonight's plan, generic spot price source, export power cap, mode-change notifications, minimum export price floor, auto-fetched indfødningstarif, feed-in tariff sensor, mirror display sensor, and Price Breakdown floor indicator. Updated sell-side price formula, decision loop, sensors reference, configuration table, dashboard section, prerequisites, and known limitations.

---

## [0.16.1] — 2026-05-15

### Changed
- **Price Breakdown card — export floor indicator** — the Arbitrage-spread section now shows a second status line when a minimum export price floor is configured (> 0): it displays the current net export price and a ✅/⛔ indicator showing whether it is above or below the floor. When the floor is 0.00 (default) the line is hidden to avoid clutter.

---

## [0.16.0] — 2026-05-15

### Added
- **Min. export price display sensor** — a new read-only sensor (`min_export_price_display`) mirrors the minimum export price setting and displays it with two decimal places (e.g. `0,10`). HA only applies `minimumFractionDigits` to number entities when the entity registry `dp` field is present, which is hardcoded to sensor-domain entities only. The mirror sensor is the correct fix: it gets `dp` via `suggested_display_precision=2` and the dashboard can show it in place of the raw number entity value. The number entity itself remains available for editing.

---

## [0.15.3] — 2026-05-15

### Changed
- Reverted display-precision workarounds from v0.15.1–v0.15.2 (entity registry options, `extra_state_attributes`). After tracing HA's source, the compact `dp` field that `getNumberFormatOptions` reads is hardcoded to `domain == "sensor"` entities only — there is no mechanism to force trailing zeros for number entities from outside HA. Code cleaned up and limitation documented in a comment.

---

## [0.15.2] — 2026-05-15

### Fixed
- **Minimum export price now displays with two decimal places** — HA's Lovelace number formatter checks `stateObj.attributes.display_precision` when determining how many fractional digits to show. The entity now exposes `display_precision: 2` in its state attributes, so the frontend applies `{minimumFractionDigits: 2}` and the card shows `0,10` instead of `0,1`. (Previous attempts via entity registry options didn't work because HA only computes the compact `dp` field for sensor entities, not number entities.)

---

## [0.15.1] — 2026-05-15

### Fixed
- Number entity `async_added_to_hass` now writes `display_precision` (not `suggested_display_precision`) into the entity registry options — the key the frontend reads for user-set precision on number entities.

---

## [0.15.0] — 2026-05-15

### Added
- **Auto-fetched indfødningstarif** — Solar AI now automatically retrieves the DSO and Energinet feed-in tariffs from Energi Data Service and deducts them from the export price. For DINEL customers this covers "Nettarif indfødning C" (code `TC_IND_03`, currently 0.0063 DKK/kWh) and the Energinet "Indfødningstarif produktion" (code `40010`, currently 0.005 DKK/kWh) — a combined 0.0113 DKK/kWh that was previously missing from the sell-side calculation. Works for any DSO whose indfødningstarif record Note contains "indfødning c". Refreshed on the same daily cycle as the import tariff schedule.
- **Feed-in tariff sensor** — new sensor `feed_in_tariff` shows the total auto-fetched indfødningstarif (DSO + Energinet) in DKK/kWh.

### Changed
- Export price formula updated: `net_export = spot_ex_vat − retailer_fee − feed_in_tariff_total`. The `export_fee` number entity now covers only the retailer/trading fee; the indfødningstarif is no longer something users need to enter manually.
- **Today's plan now respects the minimum export price floor** — export hours shown in the plan card only include hours where the net sell price exceeds your configured minimum. Hours that would be blocked at runtime no longer appear as planned export hours.
- **Minimum export price displays at two decimal places** — the number entity now shows and accepts values like `0.00`, `0.10` etc. (step 0.01, two-decimal display).

---

## [0.14.0] — 2026-05-15

### Added
- **Configurable minimum export price** — a new number entity (`min_export_price`, 0.00–2.00 DKK/kWh, step 0.01) lets you set a floor below which Solar AI will not export. At the default of 0.00 the behaviour is identical to before (only blocks when price is actually negative). Raise it to e.g. 0.50 DKK/kWh to avoid selling at times you consider unprofitable.

---

## [0.13.0] — 2026-05-15

### Added
- **24h price chart sensor** — a new sensor (`price_chart`) carries the buy and sell price for every hour in the 24h forecast window as extra attributes (`slots`). Each slot contains `h` (hour of day), `buy` (full buy price incl. tariffs + VAT), and `sell` (net export price). A dashboard card can now read these attributes to render a visual price overview.
- **Tonight's plan sensor** — a new sensor (`todays_plan`) summarises the three cheapest hours to charge and the three most valuable hours to export in plain text (e.g. `Charge: 23h, 00h, 01h  ·  Export: 08h, 09h, 10h`). Also exposed as `charge_hours` and `export_hours` attributes for automation use.
- **Negative spot price handling** — Solar AI now reacts correctly when spot prices go negative. It will never export when the export price is ≤ 0 (you would be paying the grid to take your energy). When the full buy price (incl. tariffs + VAT) reaches ≤ 0, it activates grid charging immediately regardless of the spread threshold — the grid is paying you to consume.
- **Generic spot price source** — the spot price entity is no longer tied to Strømligning. Any HA sensor that reports the current spot price excl. VAT in your local currency works: Strømligning, Tibber, or a custom template sensor. The config flow step is relabelled accordingly. `stromligning` removed from `after_dependencies` in manifest.json.
- **Export power cap** — a new number entity (`max_export_kw`, 0–10 kW, step 0.5 kW) lets you cap how much power the inverter pushes to the grid during export sessions. Set to 0 (default) for uncapped operation. When set, Solar AI writes the value to the FoxESS force-discharge-power entity on every export activation.
- **Mode-change notifications** — a new switch entity (`notifications_enabled`) enables Home Assistant persistent notifications whenever Solar AI transitions between operating modes. Each notification shows the new mode and the reason for the change. Off by default.

### Changed
- Config entry schema bumped to **v7**. Existing installs migrate automatically on restart: `stromligning_entity` is renamed to `spot_price_entity` preserving your current selection.
- `strings.json` kept in sync with `en.json` (language fallback for unsupported HA languages).
- **Dashboard — 24h price chart redesigned** — merged the colour, bar, and time into a single column, reducing from 5 columns to 3 (`Time | Buy | Sell`). Columns now align properly and the card is less cramped.
- **Dashboard — today's plan redesigned** — replaced the plain-text entity card with a markdown card showing a two-column summary (⚡ charge hours vs 💰 export hours) plus a full 24h visual timeline grid so you can see at a glance when the battery plans to charge and export.

---

## [0.12.2] — 2026-05-15

### Fixed
- **Dashboard markdown tables broken** — the YAML `>` (folding) block scalar was used for the markdown card content in both dashboard files, which collapses all newlines into spaces. Markdown tables require real newlines to render. Changed to `|` (literal) block scalar in `dashboard_da.yaml`, `dashboard_en.yaml`, and `battery_arbitrage_dashboard.yaml`.

---

## [0.12.1] — 2026-05-15

### Fixed
- **Language fallback broken** — `strings.json` (HA's fallback for unsupported languages) was out of sync with `en.json`, missing every entity and string added from v0.8.0 onwards. Any user with a non-Danish, non-English HA language would have seen missing or incorrect labels. `strings.json` is now identical to `en.json` and will be kept in sync going forward.

---

## [0.12.0] — 2026-05-15

### Added
- **Full language support** — Solar AI now ships complete English (`en`) and Danish (`da`) language packs covering every user-visible string: entity names, config flow labels, options flow labels, service descriptions, sensor state values, and binary sensor state labels.
- **Translated sensor states** — the *Operating mode* sensor now displays human-readable translated states (`Self-use` / `Exporting` / `Grid charging` / `Disabled` in English; `Selvforbrug` / `Eksporterer` / `Netopladning` / `Deaktiveret` in Danish). The *Season mode* sensor shows `Summer` / `Winter` (or `Sommer` / `Vinter`). All state values follow HA's configured language automatically.
- **Two dashboard files** — `dashboard/dashboard_en.yaml` (English) and `dashboard/dashboard_da.yaml` (Danish). Every card title, entity label override, and markdown card is fully consistent within each file. Import the one matching your language. `battery_arbitrage_dashboard.yaml` is kept for backwards compatibility and mirrors the Danish version.

### Changed
- Language follows Home Assistant's own language setting — no separate Solar AI language selector needed. Entity names and state labels switch automatically when HA's language is changed.

---

## [0.11.2] — 2026-05-14

### Fixed
- **DSO tariff double-counted** — Dinel publishes the same nettarif C time under two codes: `TCL<100_02` (residential, < 100 kWh/h) and `TCL>100_02` (large consumer, > 100 kWh/h) with identical 24-hour prices. Both passed the varying-prices filter and were summed, doubling the tariff (e.g. 2 × 0.24 = 0.48 DKK/kWh at peak instead of 0.24). Tariff records with identical 24-hour price profiles are now deduplicated — only the first match is included.

---

## [0.11.1] — 2026-05-14

### Fixed
- **Nettarif C time still showed 0 after 0.10.2 fix** — Dinel (and similar DSOs) pre-publish hundreds of future daily records.  The API returns results sorted alphabetically by `ChargeTypeCode`, so codes like `TAH`, `TAL`, `TBH` fill the first 500 positions and push `TCL<100_02` (the nettarif C time) beyond the fetch limit.  Both queries now include `end=tomorrow` which trims all future pre-published records from the response.  With that filter the daily `start=today&end=tomorrow` query returns only 7 records — and the correct nettarif C time is among them.

---

## [0.11.0] — 2026-05-14

### Added
- **DSO dropdown** — the DSO GLN field in *Settings → Integrations → Solar AI → Configure* is now a dropdown menu showing your grid operator by name instead of a raw GLN number. Dinel (Jutland/Fyn) is the first entry; more DSOs will be added over time.
- **Spot price markup entity** — new live box-input entity (0–0.50 DKK/kWh) for the per-kWh add-on that your electricity retailer charges on top of the raw spot price (handelstillæg / abonnementstillæg). Defaults to 0.00. Takes effect immediately on the next 5-minute tick. Added to the buy-side price formula: `(spot + markup + network tariff + elafgift) × VAT`.

### Fixed
- Config entry migrated to v6: existing installs with the old Dinel capacity-charge GLN (`5790000610976`) are automatically corrected to the nettarif C time GLN (`5790000610099`) on restart.

---

## [0.10.2] — 2026-05-14

### Fixed
- **Daily-updated DSO records now found** — DSOs like Dinel publish one tariff record per day (`ValidFrom=today`, `ValidTo=tomorrow`). The previous `start=2022-01-01&limit=500` query sorted oldest-first and never reached today's record (1 278+ records exist for Dinel going back to 2022). The tariff fetch now issues **two parallel queries**: one from today (catches daily records at position 0) and one from 2022 (catches seasonal/annual records from Energinet and other DSOs), then merges and deduplicates the results.
- **Default DSO GLN corrected** — changed from `5790000610976` (Dinel capacity/power charges only — no hourly nettarif) to `5790000610099` (Dinel nettarif C time — the correct hourly time-of-use tariff). Existing installs: update the **DSO GLN** field in *Settings → Integrations → Solar AI → Configure* to `5790000610099` if you are on Dinel.

---

## [0.10.1] — 2026-05-14

### Fixed
- **Tariff API query returned zero results** — the `start=today` date filter in the DatahubPricelist query meant only tariffs starting *in the future* were returned. Changed to a fixed lookback of 2022-01-01 so all currently-valid tariff records are captured.
- **Wrong Energinet GLN** — GLN `5790001102620` has no records in the datahub; corrected to `5790000432752` (Energinet transmission/system tariffs).
- **Energinet tariff over-counted non-residential charges** — the query now only includes charge code `40000` (Transmissions nettarif, 0.043 DKK/kWh), excluding `40010` (Indfødningstarif produktion — applies to large producers, not residential), `40020` (132/150 kV HV tariff), and TSO-connected industrial tariffs. No indfødningstarif is included on either the buy or sell side.
- **DSO query included capacity charges** — added a `require_all_prices` filter so only D03 records with a full 24-hour price profile are summed. This correctly excludes Effektbetaling (power/capacity charges that store only Price1) and keeps only the hourly time-variable nettarif C.
- **Default elafgift corrected** — changed default from 0.977 to 0.01 DKK/kWh. Existing installs: update the **Elafgift** entity value in the dashboard to match your actual electricity duty.

---

## [0.10.0] — 2026-05-14

### Added
- **Hourly DSO tariff integration** — Solar AI now fetches your grid operator's hourly network tariffs (nettarif C) from Energi Data Service (DatahubPricelist API), combined with Energinet's system/transmission tariffs. The tariff schedule is refreshed once per day and cached; on failure the previous schedule is kept.
- **Elafgift number entity** — A live box-input entity (0–3.00 DKK/kWh, default 0.977) lets you set the Danish government electricity duty. Takes effect immediately on the next 5-minute tick.
- **Grid tariff this hour sensor** — Shows the total network tariff (DSO + Energinet + elafgift) for the current local hour in DKK/kWh.
- **DSO GLN field** — The config / options flow now includes a text field for your DSO's GLN number (default: `5790000610976` — Dinel/Radius). Change it in *Settings → Integrations → Solar AI → Configure* if your DSO is different.

### Changed
- **Buy-side price now includes full tariff stack** — Grid-charge decisions use `(spot + DSO tariff + Energinet tariff + elafgift) × VAT` as the true buy cost. Previously only spot × VAT was used. Percentile comparisons for grid-charge thresholds are computed over these full buy-side costs, correctly accounting for which hours of the day are cheapest to charge.

---

## [0.9.0] — 2026-05-14

### Changed
- **Split-rate polling** — EVCC live state (`pvPower`, `gridPower`, EV status, battery mode) is now fetched on every fast tick. Price/tariff data (`/api/tariff/solar`, `/api/tariff/grid`) is refreshed at most once per hour, matching the rate at which DSO price data actually changes. This eliminates the unnecessary hourly hammering of the tariff endpoint while keeping live sensors fresh.
- **Configurable live-data poll interval** — new integer field in the config / options flow (10–300 seconds, default 30 s). Change it in *Settings → Integrations → Solar AI → Configure* and the integration reloads with the new interval.
- All learning models (load history, EV pattern, capacity sampling, savings, solar accuracy) continue to run every 5 minutes regardless of the fast poll rate, preserving the statistical validity of their rolling windows.
- Storage is only flushed to disk on 5-minute learning ticks, reducing I/O on flash-based HA installs.

---

## [0.8.0] — 2026-05-14

### Added
- **Configurable buy-side VAT** — a live number entity (0–50 %, box input) lets you enter the VAT percentage applied to your electricity purchase price. Replaces the hardcoded 25 % Danish rate. The arbitrage spread calculation and grid-charge decisions update on the next 5-minute tick.
- **Sell-side fee** — a live number entity (0–0.50 DKK/kWh, slider) lets you enter the per-kWh cut taken by your electricity seller when exporting. Defaults to 0.00. Previously this was hardcoded at 0.01 DKK/kWh.
- **Live solar production sensor** — exposes EVCC's `pvPower` as a proper power sensor (kW). Shows what the solar panels are producing right now.
- **Currency selector** — choose DKK, EUR, SEK, NOK, or GBP in the config / options flow. All price and savings sensor units (e.g. "DKK/kWh", "DKK") update automatically when the integration reloads. Existing installs default to DKK.

---

## [0.7.5] — 2026-05-14

### Added
- EV on Solar and EV on grid power tiles now show live charge power (e.g. "6.5 kW") directly on the tile. The active mode shows the actual kW; the inactive one shows "—". The `charge_kw` attribute is also available on both binary sensors for use in automations.

---

## [0.7.3] — 2026-05-14

### Changed
- Dashboard: EV Status is now a proper titled card (heading + three tiles) using a vertical-stack with a heading card.

---

## [0.7.2] — 2026-05-14

### Changed
- Dashboard: EV connection status, EV on Solar, and EV on grid power are now combined into a single three-tile row. All three turn green when active. Removed the standalone EV entry from the Conditions glance.

---

## [0.7.1] — 2026-05-14

### Changed
- Dashboard: *EV on grid power* and *EV on Solar* are now displayed as side-by-side tile cards that turn green when active. Removed the duplicate EV on grid power row from the Conditions glance.

---

## [0.7.0] — 2026-05-14

### Added
- **EV on Solar sensor** — new binary sensor that turns `on` when the EV is actively charging in EVCC's `pv` mode with real charge power flowing (> 3 000 W). Complements the existing *EV on grid power* sensor, which only triggers for `now`/`minpv` modes that compete for grid capacity.
- **Dashboard: colour-coded EV charging tiles** — the *EV on grid power* and *EV on Solar* sensors are now displayed as two side-by-side tile cards that turn green when active, making it immediately obvious which charging mode is in use.

---

## [0.6.0] — 2026-05-14

### Added
- **Automatic config migration** — Solar AI now migrates existing config entries when updating to a new version. Missing fields are filled in with sensible defaults automatically. Users never need to reconfigure the integration after an update.
- **Auto-detected round-trip efficiency** — Solar AI reads the FoxESS inverter's lifetime charge and discharge energy totals and computes the actual round-trip efficiency automatically (`discharge_total ÷ charge_total`). The manually configured value is used as a fallback for new installs with less than 100 kWh of lifetime data.
- **Learned battery capacity** — During Force Charge cycles, Solar AI measures energy put into the battery against the observed SoC rise to learn the true usable capacity over time. After 20 samples (typically a few charge cycles), the learned value replaces the manually configured one. The manually configured capacity remains the fallback until enough data is collected.
- **Three new sensors**: *Learned battery capacity* (kWh), *Auto-detected efficiency* (%), and *Capacity learning samples* (count) — track calibration progress directly in HA.

---

## [0.5.0] — 2026-05-14

### Added
- **Grid overcurrent protection** — Solar AI now reads the live grid import power from EVCC and calculates available headroom before starting battery charging. The force-charge rate is automatically capped to keep total grid draw below your circuit breaker limit (default 17 kW, with a 0.5 kW safety margin). If headroom drops below 0.3 kW, grid charging is skipped entirely for that tick.
- **Grid import limit input field** — New number entity lets you enter your circuit breaker capacity (5–63 kW, step 0.5 kW) directly from the dashboard. Persisted in storage, takes effect on the next 5-minute tick.
- **Two new sensors**: *Grid import power* (live kW from grid) and *Grid headroom* (kW remaining before the breaker limit). Both visible in the new Grid card on the dashboard.
- **Minimum arbitrage spread slider** — Live number entity (0.10–3.00 DKK/kWh, step 0.05) lets you tune the spread threshold without going through the config flow. Persisted in storage and takes effect on the next 5-minute tick.
- Refactored internal config-number class to be generic (supports both slider and box input modes), shared by all live-adjustable settings.

### Fixed
- **Buy-side VAT correction** — Grid charging decisions and spread calculations now use the electricity price including 25% Danish VAT (what you actually pay), while the sell side correctly continues to use the excl. VAT spot price (what you receive). Previously both sides used the excl. VAT price, which made the spread appear wider than it really is and could trigger grid charging that wasn't truly profitable.

---

## [0.4.0] — 2026-05-13

### Added
- **EV charge pattern learning** — Solar AI now learns, hour-by-hour, when your EV is actually charging (using real charge power > 3 000 W, not just "connected"). Grid charging is automatically skipped during hours where the EV typically charges, avoiding competition for cheap overnight electricity. The probability is learned via exponential smoothing (~8-day memory per hour of the day).
- **Seasonal mode detection** — A 28-day rolling average of daily solar production determines whether the system is in *summer* or *winter* mode (threshold: 6 kWh/day). This gradually adapts without hard-coded calendar dates. Defaults to *winter* (conservative) until 7 days of data are available.
- **Peak-price reservation for battery export** — The battery now only exports to the grid when the current export price is at or above the 75th-percentile price for the day. This reserves stored energy for true evening peak hours instead of selling too early at mediocre prices. Solar surplus still exports automatically in Self-Use mode.
- **3 new sensors**: `season_mode` (summer/winter), `solar_28d_avg` (kWh/day), `ev_charge_probability` (% this hour).

### Fixed
- `solar_will_fill` logic was too optimistic — it previously used raw 6 h gross solar production. It now uses the full 24 h accuracy-corrected solar forecast *minus* the predicted house consumption, giving the true net surplus available for battery charging.

---

## [0.3.0] — 2026-05-12

### Added
- **Live SoC threshold sliders** — Two number entities (sliders) in the dashboard let you adjust the battery floor SoC (minimum during export, 10–100 %) and maximum SoC (grid-charge ceiling, 10–100 %) at any time without restarting HA. Changes take effect on the next 5-minute tick and are persisted across restarts.
- **Actual & missed savings tracker** — Six new sensors track how much money Solar AI has saved (or would have saved if disabled):
  - *Actual savings*: revenue from battery export + cheap grid charging, per day / 7 days / 30 days.
  - *Missed savings*: estimated opportunity cost when the system is switched off, per day / 7 days / 30 days.
  - Values are stored in a 90-day rolling log that survives HA restarts.

---

## [0.2.0] — 2026-05-09

### Added
- **7-bucket temperature-based charge rate control** — Learned charge rates are now tracked across seven temperature bands (< 0 °C, 0–5 °C, 6–15 °C, 16–21 °C, 21–35 °C, 35–50 °C, > 50 °C) instead of five. This gives finer control at the critical low-temperature range where lithium batteries charge significantly more slowly.
- **Solar forecast accuracy factor** — Solar AI tracks actual PV production vs. Solcast forecasts over a 4-day rolling window (576 × 5-min samples) and applies a learned correction factor (0.3–1.5×) to all forecasts. This makes the self-use, export, and grid-charge decisions more realistic when Solcast consistently over- or under-estimates.
- **Net solar for battery sensor** — Shows how many kWh of solar are available for the battery after the house load is subtracted (24 h horizon, accuracy-corrected).
- **EVCC battery-mode awareness** — Solar AI now checks whether EVCC has independently taken control of the battery (hold/charge mode set by something other than Solar AI). If so, it does not override EVCC's decision. When Solar AI itself sets EVCC to hold/charge, it tracks that and restores *normal* mode when done.
- **Vacation / low-load detection** — If house load drops below 25 % of the 28-day baseline for 4+ hours, Solar AI flags vacation mode. Predicted house load uses a more conservative (1.5× short-term average) estimate during vacation to avoid unnecessary grid charging.

### Fixed
- System now defaults to **OFF** on first install — the user must consciously enable the arbitrage switch after a learning period, rather than starting in an active state.
- Metrics (prices, forecasts, learned rates) are always collected even when the switch is off, so data is ready when the user turns it on.

---

## [0.1.0] — 2026-05-07

### Added
- Initial release: **Battery Arbitrage** (later renamed Solar AI).
- Core arbitrage engine: buy cheap grid electricity, sell at peak prices using FoxESS Force Charge / Feed-in First work modes.
- Strømligning spot-price integration (excl. VAT) for sell-side pricing.
- EVCC integration for grid charging via EV charger infrastructure.
- 5-bucket temperature-based charge rate learning (calibrated during Force Charge cycles at 90th-percentile power).
- 28-day rolling house load model with 2 h short-term average for load prediction.
- Lovelace dashboard with price chart, battery status, load model, and arbitrage controls.
- Config flow with auto-detection of FoxESS Modbus entities.
- Services: `force_export`, `force_grid_charge`, `restore_normal`, `reset_learning`.
- Full Danish (da) and English (en) translations.
