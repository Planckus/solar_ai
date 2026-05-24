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

## 6. Every card refresh every 15 seconds

Drop `DEFAULT_FAST_POLL_SECONDS` from 30 to 15 so the integration's coordinator publishes new state every 15 s and Lovelace cards re-render at that cadence.

Three options:
- **A** — change the default in `const.py` only (~1 line); upstream integrations like FoxESS Modbus and Solcast keep their own polls (separate concern).
- **B** — A plus a README paragraph telling the user to also drop FoxESS Modbus's poll interval for true end-to-end 15-s freshness.
- **C** — Introduce a "High freshness mode" toggle that bumps both the fast-poll AND the EV-control-loop to 15 s / 5 s with one switch.

Recommended: A or B. C is a separate feature.

---

## 7. Plan EV charging scheduling

Solar AI's EV controller is purely reactive today — no concept of charge windows, ready-by times, or weekday patterns. Users use the car's internal timer or manual mode-flipping.

**Phase A (small, ~3 h)** — Time-window schedules. Up to 4 schedules; each has start/end/days/mode-in-window/mode-out-window. New `EV_MODE_SCHEDULED` value. Config-flow step lets the user configure them. Coordinator checks the schedule at every tick and applies the correct mode.

**Phase B (larger, ~8–12 h)** — Optimizer-driven departure scheduling. Target SoC + by-time + day-of-week pattern. The DP optimizer plans EV charging slots alongside the existing CHARGE/EXPORT/IDLE actions. Needs: a fourth optimizer action, departure-time inputs in config-flow, new sensors for charge plan + remaining energy. Where the real value lives (matches EVCC's "Plan" feature).

**Phase C (future)** — Multi-vehicle, holiday calendar, cabin pre-conditioning. Not v0.36 scope; listed so the Phase A/B data model leaves room.

Recommended order: A first as a standalone release; B as its own release after A is verified.

Open design questions captured in the chat plan: schedule limit (4?), overlap resolution, car-SoC tracking strategy, cancel-a-plan UI.

---

## 5. Solar AI sometimes fails to start with HA — suspect OCPP

After rebooting HA today, anything OCPP (the charger) wasn't working at first; it started working a few hours later on its own. Solar AI also sometimes fails to start with HA, and the suspicion is that OCPP startup ordering / dependency is the cause.

Investigate:
- Solar AI's dependency on the OCPP integration at startup.
- Whether Solar AI is failing because OCPP entities don't exist yet, or because OCPP itself is in a retry loop.
- Whether a `wait_for_state` / retry / deferred-setup pattern would fix it.
- HA logs from the most recent reboot to confirm the root cause before changing anything.

Do not push a fix until the root cause is confirmed.
