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

**Phase B (deferred to a future release)** — optimiser-driven departure scheduling (target SoC by time, DP optimizer plans EV charging slots alongside existing CHARGE/EXPORT/IDLE actions). Matches EVCC's "Plan" feature. Estimated 8–12 h work. Worth shipping after Phase A is verified in real use.

**Phase C (future)** — multi-vehicle, holiday calendar, cabin pre-conditioning. Listed so Phase B's data model has room.

---

## 5. Solar AI sometimes fails to start with HA — suspect OCPP

After rebooting HA today, anything OCPP (the charger) wasn't working at first; it started working a few hours later on its own. Solar AI also sometimes fails to start with HA, and the suspicion is that OCPP startup ordering / dependency is the cause.

Investigate:
- Solar AI's dependency on the OCPP integration at startup.
- Whether Solar AI is failing because OCPP entities don't exist yet, or because OCPP itself is in a retry loop.
- Whether a `wait_for_state` / retry / deferred-setup pattern would fix it.
- HA logs from the most recent reboot to confirm the root cause before changing anything.

Do not push a fix until the root cause is confirmed.
