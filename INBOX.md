# Solar AI — inbox

Items queued from a global Claude session on 2026-05-23. Triage in the Solar AI project session (which has full project memory loaded).

---

## ~~1. Document gaps, defer fix~~ (resolved 2026-05-23)

Was the UK currency cleanup deferral. CHANGELOG + README updated with the known-limitation note. No code change.

---

## ~~2. Make DatahubPricelist tariff API configurable~~ (resolved 2026-05-22 in v0.30.1)

CONF_PRICE_AREA dropdown (DK1/DK2) and CONF_TARIFF_FETCH_ENABLED toggle added to OptionsFlow. Coordinator skips the daily DatahubPricelist fetch block when disabled.

---

## ~~3. Replace "fuld kraft" battery lock with actual-charge-window lock~~ (resolved 2026-05-22 in v0.30.1)

Picked the "trigger from observed charger power draw" option. Lock condition in `_run_ev_controller` changed from `final_amps > 0` (controller intent) to `ev_current_kw > EV_BATTERY_LOCK_POWER_THRESHOLD_KW` (actual draw, 0.3 kW threshold). No extra config or hardware needed.

---

## ~~4. Solar visibility when battery is price-blocked~~ (resolved 2026-05-22 in v0.30.1)

Two parts:
- EV controller substitutes the forecast PV value into the surplus calc when the floor is active AND battery near max SoC AND forecast indicates clear curtailment (>1 kW forecast vs <50% actual). Once the EV starts pulling, panels MPPT up to match.
- `_update_solar_accuracy` now drops samples taken while the floor is active so curtailed production doesn't poison the per-hour learning factor.

---

## ~~6. Every card refresh every 15 seconds~~ (resolved 2026-05-24 in v0.36.0)

DEFAULT_FAST_POLL_SECONDS dropped 30 → 15 with migration. README note about FoxESS Modbus's own poll cadence. Live on HA + GitHub.

---

## ~~7. EV charging scheduling — Phase A~~ (resolved 2026-05-24 in v0.36.0)

Phase A shipped. New EV mode `Scheduled` + up to four `(HA schedule helper → EV mode)` links + fallback mode. Users create schedule entities at Settings → Helpers → Schedule (HA's native per-weekday time-range UI), then link them in Configure → EV charge schedules. Coordinator's `_resolve_effective_ev_mode()` walks links every tick, first link with schedule `on` wins.

**Updated 2026-05-26 (v0.38.0 + v0.39.7):** the workflow above is no longer current. v0.38.0 moved schedules into the dashboard — 4 native slots per install via `select.solar_ai_skema_N_tilstand`, `switch.solar_ai_skema_N_aktiveret`, `time.solar_ai_skema_N_starttid/sluttid`, `sensor.solar_ai_skema_N`. v0.39.7 removed the now-redundant `Configure → EV charge schedules` OptionsFlow step. Set the EV mode select to `Scheduled` and edit the 4 slot rows on the EV / OCPP tab. Coordinator's `_resolve_effective_ev_mode()` still walks them every tick. Pre-v0.38.0 installs are migrated once on coordinator setup (coordinator.py:604-662 reads any legacy `CONF_EV_SCHEDULE_LINKS` data).

**Phase B (deferred to a future release)** — optimiser-driven departure scheduling (target SoC by time, DP optimizer plans EV charging slots alongside existing CHARGE/EXPORT/IDLE actions). Matches EVCC's "Plan" feature. Estimated 8–12 h work. Worth shipping after Phase A is verified in real use.

**Phase C (future)** — multi-vehicle, holiday calendar, cabin pre-conditioning. Listed so Phase B's data model has room.

---

## 8. Stale "EVCC" reference in the mode-reason sensor on non-EVCC setups

Screenshot from a live FoxESS-only install (`select.solar_ai_live_data_source = foxess`, no EVCC involved) shows the reason line: **"EV actively charging (now/minpv) — holding battery for EVCC"**. Misleading — the battery-hold logic itself is correct (don't sell the battery while the EV controller is drawing from it), but the wording attributes it to EVCC even when EVCC isn't configured at all. This is Solar AI's own native EV controller (OCPP or FoxESS-Modbus backend) doing the holding.

Source: `coordinator.py:2812` — `reason = "EV actively charging (now/minpv) — holding battery for EVCC"`, set whenever `ev_charging_now` is true, with no check on `live_data_source`. Sibling string at `coordinator.py:2814` (`f"EVCC managing battery ({evcc_battery_mode}) — not overriding"`) is genuinely EVCC-specific (fires only when `evcc_managing_battery` is true) and is fine as-is.

Also noticed while reading this: the whole mode-reason block (`coordinator.py` ~2794-2820, feeds `sensor.battery_arbitrage_begrundelse_for_tilstand` / "Driftstilstand") is English-only — it doesn't use the bilingual `self._msg(en, da)` pattern the EV-tab reason strings use elsewhere. Worth doing in the same pass if fixing the wording anyway, but not required to fix the EVCC reference itself.

Fix sketch (not yet designed/approved): reword the string to be source-agnostic (e.g. "EV charging — holding battery for it") since it's true regardless of which EV backend caused `ev_charging_now`, or gate the current wording on `live_data_source in ("evcc", "hybrid")` and give the FoxESS/OCPP-native case its own string. Confirm which with the user before implementing — do not guess.

**Full sweep done 2026-08-16** (all `EVCC` references across coordinator.py, sensor.py, config_flow.py, strings.json, translations/*.json). Two more confirmed, logged as items 9 and 10 below. Everything else — config-flow EVCC options, EVCC-specific entities/services, internal `_evcc_post`/log-line mentions — is correctly gated on `live_data_source` or is backend-internal (not GUI-facing). No further items found.

---

## 9. `evcc_battery_mode` sensor is created on every install, not just EVCC/Hybrid ones

`sensor.py:205-209` registers `sensor.solar_ai_evcc_batteritilstand` (translation key `evcc_battery_mode`) unconditionally in the sensor description list — no check against `live_data_source`. `value_fn=lambda d: d.get("evcc_battery_mode", "normal")` means on a FoxESS-only install (where the `evcc_battery_mode` key is never written into the coordinator's data dict) it permanently reads the hardcoded fallback `"normal"`. Dead entity: exists, shows a value, never means anything, for every FoxESS-only user.

Fix sketch (not yet approved): filter the sensor description out at `async_setup_entry` time when `live_data_source == "foxess"`, matching however other source-conditional entities in this file are already excluded (check if a precedent pattern exists before inventing one).

---

## 10. `force_grid_charge` service description is factually wrong — the real mechanism is FoxESS Work Mode, not EVCC

`strings.json` / `translations/en.json` / `translations/da.json`: *"Immediately activate grid charging via EVCC."* / *"Aktiverer øjeblikkeligt netopladning via EVCC."*

Traced the handler: `__init__.py:485 handle_force_grid_charge` → `coordinator._transition_to("grid_charging")` → `coordinator.py:2864`, which sets the FoxESS Work Mode select to Force Charge. That is the actual, always-used actuator — regardless of `live_data_source`. EVCC is only sent a courtesy `batteryMode=hold` notification, and only when `live_data_source in (EVCC, Hybrid)` (`coordinator.py:2843`). The description misrepresents the mechanism for **every** install, including EVCC-mode ones — it's not a "missing gate" bug like items 8/9, it's just wrong.

Fix sketch (not yet approved): reword to something like "Immediately activate grid charging (Force Charge)." — drop the EVCC framing entirely since EVCC was never the actuator.

---

## 5. Solar AI sometimes fails to start with HA — suspect OCPP

After rebooting HA today, anything OCPP (the charger) wasn't working at first; it started working a few hours later on its own. Solar AI also sometimes fails to start with HA, and the suspicion is that OCPP startup ordering / dependency is the cause.

Investigate:
- Solar AI's dependency on the OCPP integration at startup.
- Whether Solar AI is failing because OCPP entities don't exist yet, or because OCPP itself is in a retry loop.
- Whether a `wait_for_state` / retry / deferred-setup pattern would fix it.
- HA logs from the most recent reboot to confirm the root cause before changing anything.

Do not push a fix until the root cause is confirmed.
