# Changelog

All notable changes to **Solar AI** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [0.51.0] — 2026-06-03

### Added — automatic dashboard setup

- The dashboard YAML now ships **inside** the integration (`custom_components/battery_arbitrage/dashboards/`), so it is included in a HACS install. The setup wizard's Dashboard step has a **"Create the Solar AI dashboard for me"** option (on by default) that registers the dashboard automatically at `/solar-ai`, in your Home Assistant language — no manual raw-config paste. It is created once and never re-creates a dashboard you later delete.
- New `battery_arbitrage.create_dashboard` service for existing installs (and for refreshing after an update): `force: true` overwrites an existing Solar AI dashboard with the bundled layout.
- The custom Lovelace cards (Mushroom, ApexCharts, Power Flow Card Plus, card-mod, button-card) still need a one-time HACS Frontend install — HACS does not chain-install frontend plugins from an integration, and bundling third-party cards would be improper. To make that obvious, the integration now raises a **Repairs** issue listing exactly which of those cards are missing (with links), instead of leaving cryptic "Custom element doesn't exist" errors on the dashboard. The issue clears automatically once they're installed. (Only shown for installs using the bundled dashboard.)
- A **sell-price matrix** card on the Prices page, directly below the buy-price matrix: the hourly export (sell) price for today and tomorrow, from the same `price_forecast` sensor. Colour-coding is inverted versus the buy matrix — green = a high (good) sell price, red = low — so green always means "good for you".

### Changed

- Canonical dashboards moved from the repo-root `dashboard/` folder to `custom_components/battery_arbitrage/dashboards/`. `deploy.py` and the README import paths updated accordingly.

---

## [0.50.1] — 2026-06-03

### Fixed — EV page rendering full-width

- After v0.50.0 added the 28 weekday toggles, the EV / OCPP page rendered edge-to-edge instead of the centred ~1000 px width used by the other pages. The page wraps its content in a single `vertical-stack` whose width is capped by a card-mod `:host` style; the larger view tripped card-mod's timing so the style stopped applying. The EV view now wraps its content in a `custom:mod-card`, which applies the same max-width deterministically. Dashboard-only — no integration or restart needed.

### Docs

- README install instructions moved to the top and clarified: electricity prices are fetched automatically from Energi Data Service by choosing a country, price area (DK1/DK2) and grid company (DSO) — no separate price integration required. Added v0.50.0/v0.50.1 release notes.

---

## [0.50.0] — 2026-06-02

### Added — per-schedule weekday selection in the GUI

- Each EV charge schedule (1–4) now has **seven weekday on/off toggles** (Mon–Sun), so you can pick exactly which days a plan runs — e.g. charge 02:00–05:00 on Monday, Tuesday and Friday only — entirely from the dashboard. Backed by the schedule slot's existing `days` list and a new `set_schedule_slot_day()` coordinator method; the resolver already honours per-day activation (including windows that wrap past midnight). New slots still default to Mon–Fri. The toggles are grouped under each Skema / Schedule card on the EV page.

---

## [0.49.1] — 2026-06-02

### Fixed — feed-in tariff dropping to 0

- The grid feed-in tariff (DSO indfødning C + Energinet production tariff, deducted from the export price) could fall to **0 DKK/kWh** after a restart or whenever Energi Data Service rate-limited the tariff fetch (HTTP 429). The daily refresh fires several D03 queries near-simultaneously; when the consumption-tariff queries succeeded but the feed-in queries were 429'd, `fetch_feed_in_tariff` returned `0.0` and the old commit guard (which only checked the consumption schedules) overwrote the previously-good feed-in value with zero, locking it for up to an hour. The values were also not persisted, so every restart started at 0 until the next successful fetch.
- Three changes:
  - `fetch_feed_in_tariff` now returns `None` (not `0.0`) when a lookup fails or finds no valid record; the coordinator commits the new value only when it is a real number, otherwise keeping the last good cached value.
  - The feed-in tariff is now persisted to storage and restored on startup, so the export price is correct immediately after a restart.
  - The daily tariff refresh now issues its Energi Data Service queries sequentially instead of firing all six at once, which was reliably tripping the rate limit; `DatahubPricelist` requests also retry HTTP 429 and transient errors with a short, jittered backoff.

---

## [0.49.0] — 2026-06-02

### Changed — clearer "no-trade day" wording

- When the optimiser runs and finds nothing worth doing (prices too flat to clear the spread, battery already covered by solar), the daily plan now reads **"No trades today — prices too flat to arbitrage (running on self-use)"** / **"Ingen handler i dag — priserne er for flade til arbitrage (kører på selvforbrug)"** instead of a bare "Charge: none · Export: none", which looked like an error or a failed calculation. Display only — no change to optimiser logic.

### Added — disk-space alarm

- **`sensor.solar_ai_disk_free`** (diagnostic) — free space (GB) on the partition Home Assistant runs on, with `pct_free`, total/used, the probe path, and the alarm threshold as attributes. This watches the actual disk that fills up on a Pi/SD-card install (where the recorder DB and `.storage` live).
- **`binary_sensor.solar_ai_disk_low`** (device class `problem`) — turns on when free space drops below the configured threshold. Use it in your own automations.
- **Configurable threshold** — a number entity in the settings panel sets the alarm at a chosen **% free** (default 10%, range 1–50).
- **Mobile push** — fires once when free space first crosses below the threshold, with a recovery hysteresis so a borderline reading doesn't repeat. Gated by a new `notify_disk_low` switch (default on) and the master notifications toggle + targets.

---

## [0.48.1] — 2026-06-02

### Added — buy-price forecast + price matrix

- New `price_forecast` sensor exposing an **hourly, timestamped buy/sell price forecast over the full horizon** (today + tomorrow once the day-ahead prices publish ~13:00), as a `slots` attribute of `{iso, buy, sell}`. The existing 24h price-chart sensor only covered today and carried no dates; this one is date-aware and spans the whole horizon. A **price matrix** card on the Prices page lays the upcoming buy prices out as a two-row grid (today / tomorrow × hour), colour-coded green = cheap → red = pricey, with 1-decimal prices, pinned row labels and horizontal scroll for mobile.

---

## [0.48.0] — 2026-06-01

### Added — grid import cost + net grid balance

- **Import cost tracking.** A new `import_cost` sensor (DKK, `total_increasing` + `monetary`) accumulates the cost of **all** grid import — house load *and* battery grid-charging — as `import_kWh × full buy price` each tick, with today / 7d / 30d / month / year attributes and a daily series.
- **Net grid balance.** A new `net_grid_balance` sensor shows **export income − import cost** (true net cash flow with the grid; can be negative if you're a net buyer), with the same period rollups and a daily net series. The existing `export_income` figure remains **gross export revenue** — `net_grid_balance` is the figure that nets the import against it.
- The Prices/Priser dashboard page gains a net-balance card beside the export-income card.

---

## [0.47.7] — 2026-06-01

### Fixed — cold all-IDLE plan cached for ~15 min after a restart

- After a restart the optimiser ran on the first tick before the price cache and live SoC had loaded, producing a degenerate all-IDLE plan. Because that plan is non-empty it was cached until the next scheduled re-solve (`PLAN_REFRESH_SECONDS`, 15 min), so no charge/export executed for that whole window. The optimiser now only solves when its inputs are ready (`grid_slot_data` populated and `battery_soc > 0`); until then the plan stays empty and the reactive fallback covers the gap, then the first *real* plan is cached. This stops a restart from silently disabling trading for up to 15 minutes.

---

## [0.47.6] — 2026-06-01

### Fixed — battery arbitrage export now actually discharges to the grid

- **Export used the wrong work mode.** `MODE_EXPORTING` set FoxESS **"Feed-in First"**, which only re-routes *solar* surplus to the grid — it does **not** discharge the battery at night. So even when the optimiser decided to export (and switched the mode), no battery power flowed to the grid. It now uses **"Force Discharge"** and sets the discharge power, so the battery is actually pushed to the grid.
- **Power setpoints wrote the wrong unit.** `_set_charge_power` and `_set_discharge_power` did `int(kw * 1000)`, writing **watts** into the FoxESS force-charge/-discharge number entities, which are in **kW** (range 0–10). The out-of-range write silently failed, leaving the power at its default maximum (10 kW) — so grid-charging ran at full power **ignoring the grid-headroom cap** (an overcurrent risk) and any export cap was never applied. Both now write kW, clamped to the entity's range. Export with no cap defaults to the entity's max (full rate).

---

## [0.47.5] — 2026-06-01

### Fixed — optimiser never executed charge/export under receding-horizon (regression)

- **The planned charge/export action was rarely executed.** The plan was built from `_forecast_slots(..., now, ...)`, which kept only slots with `start >= now` — dropping the **in-progress** 15-minute slot. The decision logic matches the *current* (hour, minute-bucket) to a plan slot, so once the plan was (re)built mid-slot the current interval had no slot to act on and fell through to IDLE. With the v0.47.0 receding-horizon replan (every 15 min, almost always mid-slot) this happened nearly every cycle, so the battery sat in Self Use and missed export/charge windows — e.g. it failed to sell into a 3+ DKK/kWh evening price spike despite a full battery. `_forecast_slots` now includes the in-progress slot (kept if its end is after `now`), so plan slot 0 covers "now" and the match — and execution — work. Pre-0.47.0 (a once-daily plan built in the morning) included every slot, which is why this only surfaced after receding-horizon shipped.

### Fixed — house-load 24 h projection over-extrapolated short-term spikes

- `predicted_house_load_24h` was `max(load_2h × 1.1, load_28d × 0.5) × 24` — it multiplied the trailing **2-hour** average across the whole day, so a brief evening peak (e.g. 0.83 kW) projected to ~22 kWh when the real day is ~11 kWh. It now projects from the learned **weekday/weekend hourly profile** (correct daily shape) with a bounded recent-activity scaler (0.8–1.4×), so genuine busy days still register but a transient spike can't run away. This value feeds the reactive `truly_exportable` and `solar_will_fill` guards; the old over-projection made them needlessly conservative (reserving phantom house load against exportable energy and mis-judging whether solar would refill).

---

## [0.47.4] — 2026-06-01

### Documentation

- The README Settings reference now lists each control in **both English and Danish** (the GUI shows Danish labels on a Danish Home Assistant and English elsewhere), so users on either language can map the docs to what they see.

---

## [0.47.3] — 2026-06-01

### Documentation

- Added a complete **Settings reference** to the README, grouped to match the Settings (Indstillinger) dashboard page: master controls, battery limits, price parameters, optimizer, EV charge controller, temperature-banded charge rates, and notifications. Each setting lists its range, default, and a plain-English description. Corrected a stale value (the minimum-arbitrage-spread default is 0.30 DKK/kWh, not 1.00).

---

## [0.47.2] — 2026-06-01

### Changed

- **`Today's plan` sensor is now date-aware and bilingual.** It previously listed bare hour numbers (`Charge: 10h, 11h`), which made tomorrow's hours indistinguishable from today's. It now groups by day and tags them — e.g. `Køb: i dag 23h  ·  Salg: i morgen 10h, 11h, 14h` — using the resolved HA language.
- **Prediction-scorecard warm-up lengthened** from 15 → 30 minutes (`PREDICTION_WARMUP_SECONDS`), so the rolling SoC-MAE isn't inflated by the optimiser plan still settling shortly after a restart.

### Notes

- Verified the full buy/sell/charge pipeline runs at **native 15-minute price resolution**: EDS DayAheadPrices is fetched at 15-min (limit=192 = 4×48 h), every quarter-hour becomes a rate with no hourly aggregation, and the DP solves per-15-min slot with decisions matched on 15-min buckets. The hourly elements (DSO tariff, house-load and EV models) are hourly by nature. The `15-min price resolution` switch only affects the price *chart* density, not the calculations. Corrected a stale docstring that claimed the optimizer averages slots to hourly.

---

## [0.47.1] — 2026-06-01

### Fixed — dynamic discharge floor reserved for "now" instead of the night

- The dynamic discharge floor computed the reserve as the house load from *now* until the next refill. During the day (and before sunset in summer) the next refill is essentially now, so the reserve collapsed to ~0 and the floor clamped to the 20 % minimum — *below* a typical static floor, which would let the pre-sunset export over-deplete the battery before the night began (the opposite of the feature's intent). The floor is now computed for the **next dark bridge** — the upcoming stretch where neither solar covers the house nor a cheap grid window exists — from its start (e.g. tonight's sunset) through to its refill (sunrise / cheap window). So the reserve reflects the real overnight need regardless of the current time of day. The reserve is also added **on top of the hardware minimum SoC** (`DYNAMIC_FLOOR_MIN_SOC`, 20 %), since the battery only delivers down to that floor — so the export floor is `hardware_floor + bridge_reserve`, leaving the full bridge energy actually usable overnight. Also includes the dashboard control (switch + `effective_floor` sensor) added under Indstillinger → Batteri-grænser.

---

## [0.47.0] — 2026-06-01

### Changed — receding-horizon planning (A)

- **The DP plan now re-solves every 15 minutes** (plus on restart and the daily tariff refresh) instead of only once per day. Previously a plan computed in the morning was locked in for ~24 hours, so it never incorporated tomorrow's day-ahead prices when they publish (~13:00) and didn't adapt to the live SoC or to solar over/under-delivery. The plan now tracks current conditions and folds in new prices within 15 minutes (`PLAN_REFRESH_SECONDS`). The solver is unchanged — only the re-solve cadence.

### Added — dynamic self-learning discharge floor (C)

- **New `Dynamic discharge floor` switch (default OFF).** When on, the export floor is no longer a fixed SoC. Each cycle it is computed as the SoC needed to run the house (projected load, weekday/weekend-aware) until the next *refill* — whichever comes first of sunrise solar covering the house, or a cheap grid window (buy price within 10 % of the horizon minimum) — multiplied by a self-learned safety margin. Clamped to a battery-health band (`DYNAMIC_FLOOR_MIN_SOC` 20 %…`DYNAMIC_FLOOR_MAX_SOC` 85 %).
  - Effect: a short bridge (sun or a cheap window soon) lowers the floor so more can be exported at the peak; a long winter night with no cheap window raises it so enough is held to avoid expensive overnight imports.
  - **Self-learning margin**: once per day the margin nudges up if the reserve ran down to the hard floor (under-reserved → import risk) and slowly relaxes down if it never came close (over-reserved → missed arbitrage). Bounded 0.80–1.60.
  - New `effective_floor` sensor shows the floor actually in effect, with `dynamic_active`, `dynamic_floor_soc`, and `reserve_margin` attributes. When the switch is off, behaviour is unchanged (static floor slider).

---

## [0.46.1] — 2026-05-31

### Fixed — prediction scorecard restart artifacts

- The scorecard logged garbage predicted-SoC samples in the first minutes after a restart, when the optimiser plan is still cold (e.g. `pred_soc 0 / 45` while the battery was actually ~98 %). A few of these inflated the rolling SoC-MAE for the whole 7-day window. The scorecard now skips logging for a `PREDICTION_WARMUP_SECONDS` (15 min) warm-up after each (re)start — a restart is an operational event, not a prediction to grade. A one-time reset clears the already-contaminated early log for a clean baseline; the warm-up guard prevents recurrence.

---

## [0.46.0] — 2026-05-31

### Added — weekday/weekend house-load split (L1)

- **Separate weekday and weekend load profiles.** The learned 24-hour house-load curve is now split into Mon–Fri and Sat/Sun profiles (`house_load_weekday`, `house_load_weekend`), each learned with the same EMA. The optimiser picks the right curve per slot by the slot's own date, so a 48-hour horizon spanning into the weekend uses the correct shape. On upgrade both profiles are seeded from the previous combined curve, and each hour falls back (own value → legacy combined → other day type → rolling mean) so nothing goes cold. Weekends typically have later mornings and more daytime presence — a single blended curve smeared that out, mis-estimating idle SoC drift and house-deficit costs.

Tariff correctness (P1) was reviewed and is already handled: the DSO + Energinet schedule is fetched from EDS DatahubPricelist for the current date (seasonally correct) with time-of-day variation, and applied per hour-of-day across the horizon. No change needed.

---

## [0.45.0] — 2026-05-31

### Added — session-aware EV demand in the optimiser (E1)

- **Live EV session feeds the DP.** Previously the optimiser modelled EV load purely as an hour-of-day *probability* (`ev_charge_hourly[h] × ev_max_kw`). When the car is plugged in and in a forced-draw situation — actively charging, or the controller's effective mode is pv+battery / full (fast), or the requested EVCC mode is now/minpv — the optimiser now treats the next `EV_SESSION_DP_HORIZON_H` hours (default 2 h) of EV demand as near-certain (the live charge power, else the learned max) and blocks battery grid-charging across that window so the two draws don't stack against the grid-import limit. Beyond the horizon the learned hourly model resumes.
- Pure-PV charging is unchanged — it's already captured by the solar→EV idle dynamics, so it does not trigger a forced session.
- The reserved demand is surfaced as the `dp_session_demand_kw` attribute on the `ev_target_kw` sensor (0 = no live session, using the learned model).

Without the car's state of charge the full session length is unknown, so the certain window is capped at 2 h; extending it to the exact remaining-kWh is future work (E3, car-SoC integration).

---

## [0.44.0] — 2026-05-31

### Added — probabilistic solar in the optimiser (S1)

- **Solar confidence knob.** The DP optimiser now plans against a configurable percentile of each hour's observed forecast/actual ratio instead of the fixed median. New `Solar confidence` number entity (`solar_confidence_pct`, 10–90 %, default **50**). At 50 the percentile equals the median, so the default is numerically identical to 0.43.0 — **no behaviour change until you lower it**. Lowering it makes the planner assume more conservative solar (plan against e.g. the P35 outcome), so it grid-charges more readily in cheap windows and is less likely to over-export battery it will need on a cloudy day. Cold hours still fall back to the global rolling factor exactly as before. The active percentile is surfaced on the `solar_hourly_accuracy` sensor (`confidence_pct`).

This builds directly on the 0.43.0 P10/P50/P90 groundwork. Recommended workflow: leave it at 50 until the `prediction_accuracy` scorecard has a week of baseline, then lower it and watch the SoC-MAE / solar-MAPE for the effect.

---

## [0.43.0] — 2026-05-31

### Added — prediction scorecard + solar-forecast percentiles (observability)

Groundwork for measurably more precise buy/sell/charge decisions. Both additions are pure observability — no decision logic changes in this release, so behaviour is identical to 0.42.0. They establish a baseline so a later release can prove (on real data) that a logic change improved precision rather than assuming it.

- **Prediction scorecard (M1).** On each 15-minute slot rollover the optimiser's predicted battery SoC for the slot is logged against the realised SoC (`prediction_log`, 30-day cap). New sensor `prediction_accuracy` reports the rolling 7-day SoC mean-absolute-error (% points) as state, with attributes for 30-day MAE, solar-forecast MAPE (from the per-hour buckets), sample count, the predicted-action mix, and the last 24 h of slot records for charting.
- **Solar-forecast percentiles (S1 groundwork).** The per-hour `(forecast, actual)` buckets already collected are now also exposed as P10/P50/P90 of the actual/forecast ratio (`get_solar_hour_percentile`, surfaced on the `solar_hourly_accuracy` sensor). The optimiser still uses the median factor — the percentiles are visibility only, so a later release can switch export/charge sizing to a conservative percentile once the scorecard confirms the spread is real.

---

## [0.42.0] — 2026-05-31

### Added — export-income tracking

- **New sensor `export_income`** (DKK, `total_increasing` + `monetary`) — accumulates income from *all* exported energy (solar excess + battery-to-grid), `feed_in × interval × net export price`, on each learning tick. Being `total_increasing` + `monetary`, Home Assistant records long-term statistics, so income can be summed over any range via the **Energy dashboard's date picker** or a statistics card. Attributes expose at-a-glance period totals (`today`, `last_7_days`, `last_30_days`, `this_month`, `this_year`) and a `daily` series for charting. Backed by a daily log (`export_income_log`, ~13 months retained).
- **Dashboard (Prices/Priser section)** — an export-income panel with the period totals and a daily-income chart. For arbitrary from/to financial totals, add the export to HA's Energy dashboard (feed-in kWh + export-price entity) — see README.

---

## [0.41.0] — 2026-05-31

### Added — bilingual user-facing text (English / Danish)

The EV-controller status `reason` strings and the push notifications now render in English or Danish based on Home Assistant's configured language (Danish HA → Danish, anything else → English). Previously they were always Danish, so they showed Danish on the English dashboard. Display/notification text only — no behavioural change.

- New `_msg(en, da)` coordinator helper keyed off `hass.config.language` (resolved once at setup).
- ~13 EV reason strings (PV, PV+battery, priority gate, override ramp, cool-down, locked, full) and the 6 push notifications (export/charge start/stop, solar-export blocked/resumed) are now bilingual.
- Arbitrage mode reasons were already English; sensor states and entity names localise via the existing translation files. Added a `_msg` unit test.

---

## [0.40.7] — 2026-05-31

### Fixed

- **PV mode held the last charge rate during the cool-down instead of the minimum.** When solar surplus dropped below the minimum, the EV controller kept charging at the *last-commanded* rate (e.g. 8 A / 5.5 kW) through the stop-window — so the deficit (~3.7 kW) was pulled from the house battery/grid. It now eases to the configured minimum (e.g. 6 A / 4.14 kW) for the cool-down hold, minimising non-solar draw. (The telemetry already called this "minimum"; now it actually is.) Affects PV mode only — other modes are unchanged.

### Added

- **Dashboard:** a stop-window countdown chip ("EV stopper om X s — lav sol") under the energy-flow card, shown only while the EV is in the COOLING hold (PV surplus below minimum, counting down to stop).
- **English dashboard (`dashboard_en.yaml`) rebuilt to match the Danish one** — same single-screen layout, with all display text translated to English. Entity IDs are unchanged (identical to the Danish dashboard). Dynamic text generated by the integration (sensor `reason` strings, operating-mode states) still renders in Danish.

---

## [0.40.6] — 2026-05-30

### Added — OCPP reliability, part 3 (event log, read-back, tests)

- **Rolling OCPP event log.** The embedded server keeps the last 50 events (boot, status changes, SetChargingProfile / RemoteStart / ChangeAvailability results, transaction start/stop, watchdog actions) and surfaces them on the `ocpp_diagnostics` sensor as `recent_events` — a queryable history without a file log.
- **GetCompositeSchedule read-back.** `verify_applied_limit()` reads the charger's applied current limit and logs it (applied vs commanded) so a charger silently ignoring SetChargingProfile becomes visible. Self-disables after one NotSupported/error reply (many OCPP 1.6 chargers don't implement it); the periodic re-assert stays the primary safety net. Invoked during the watchdog's Stage-1 re-sync.
- **Unit tests** (`tests/test_ocpp_server.py`) covering SetChargingProfile verify/retry + dedupe/force, `session_active` reset on boot and on Available/Preparing, and the event-log cap. `ocpp` added to `requirements_test.txt`.

### Changed

- **Dashboard:** battery temperature (lowest cell) is shown as a chip under the energy-flow diagram (green normally, blue below 10 °C, red above 40 °C).

Note: cross-restart session-state persistence — the remaining Tier 3 item — was already provided by the shared `charger_metadata` snapshot, so no change was needed there.

---

## [0.40.5] — 2026-05-30

### Added — OCPP reliability, part 2 (desync watchdog / auto-heal)

When the controller wants the EV charging (commanded > 0) but the charger isn't actually delivering power, the controller now escalates recovery automatically instead of leaving it to a manual replug/reboot:

- **Stage 1 (≥ 60 s not delivering):** re-sync charger state via `TriggerMessage` (StatusNotification + MeterValues), rate-limited to once/60 s. Low-risk; also unfreezes stale power telemetry.
- **Stage 2 (≥ 180 s, once per 10 min):** cycle connector availability (`ChangeAvailability` Inoperative → Operative) to force a charger wedged in Preparing/SuspendedEVSE/Finishing to drop the stuck state and re-handshake, after which the normal RemoteStart begins a clean session. Standard OCPP op — does **not** reboot the charger. Deliberately never applied to a live `Charging` session or a car-side `SuspendedEV` (cycling wouldn't help there).

The watchdog state is exposed on the `ocpp_diagnostics` sensor (`stuck_seconds`, `last_recovery_action`, `last_recovery_age_s`). New `ChargePoint.change_availability()` method; tunables `EV_STUCK_RESYNC_SECONDS` (60), `EV_STUCK_RECOVER_SECONDS` (180), `EV_STUCK_RECOVER_COOLDOWN_SECONDS` (600).

---

## [0.40.4] — 2026-05-30

### Added — OCPP reliability, part 1 (observability + command verification)

First of a planned hardening pass on the embedded OCPP server.

- **OCPP diagnostics sensor** (`ocpp_diagnostics`) exposes the server's internal state as attributes — `session_active`, transaction id, commanded amps, last `SetChargingProfile` status + age, last `RemoteStartTransaction` status + age, MeterValues age, seconds-since-seen, protocol errors. Charge-rate / transaction desyncs (the kind that caused the 16 A free-run and the stuck-in-Preparing issues) are now visible at a glance instead of requiring a file log this HA doesn't keep.
- **`SetChargingProfile` is verified and retried.** `set_current` checks the charger's reply and only caches `last_commanded_amps` on an **Accepted** response; on Rejected/timeout/exception it retries up to twice with backoff. A rejected write is no longer treated as applied, so the periodic re-assert keeps correcting it. RemoteStart and SetChargingProfile outcomes are recorded for the diagnostics sensor.

---

## [0.40.3] — 2026-05-30

### Fixed

- **Charger wedged in "Preparing" — no charging started — after a reconnect/reboot.** A stale `session_active` flag (left True when a closing `StopTransaction` was missed across a charger reconnect or reboot) blocked `RemoteStartTransaction`, which only fires when no session is active. The controller kept commanding charge while the charger sat in Preparing at 0 W. The OCPP server now clears `session_active` whenever the charger reports **Available** or **Preparing** (states that definitionally have no active transaction) and on **BootNotification**, so a fresh session can be started.

---

## [0.40.2] — 2026-05-30

### Fixed

- **EV charged at full current, ignoring the commanded rate, after a charger reconnect.** When the charger reconnected or began a new transaction it cleared its charging profile and reverted to its built-in default (full current), but the cached commanded-amps value was unchanged — so neither the controller's change-gate nor the OCPP `set_current` dedupe re-sent the limit. The EV free-ran at max, drawing from the house battery in PV / PV+battery modes (observed: controller commanded 6 A while the charger pulled ~16 A / 10.9 kW from the battery). Two fixes:
  - The OCPP server resets its cached commanded-amps on `BootNotification` and `StartTransaction`, so the limit is always re-sent for a fresh session.
  - The controller re-asserts the active limit at least every 60 s (`EV_RATE_REASSERT_SECONDS`, forced past both dedupe layers), pulling a charger that silently dropped its profile back to the commanded rate within ~1 minute.

---

## [0.40.1] — 2026-05-30

Dashboard-only patch fixing the new energy-flow card.

### Fixed

- **Battery flow direction reversed.** `power-flow-card-plus` uses home-perspective naming (like the grid): `consumption` = energy into the home, `production` = energy out. The battery was wired `consumption: battery_charge / production: battery_discharge`, so a discharge was read as charging — producing a phantom solar→battery flow and a house reading 0 W. Corrected to `consumption: battery_discharge / production: battery_charge`.
- **Køb nu / Salg nu tiles showed "–".** They matched the current hour against `sensor.solar_ai_24h_priskort`'s `slots`, but that sensor prunes past 15-min slots, so the current hour was usually absent. Repointed to the dedicated current-price sensors that always hold the live value: `sensor.solar_ai_indkobspris_opdeling` (buy) and `sensor.battery_arbitrage_eksportpris` (sell).

### Changed

- Slowed the flow-dot animation (`min_flow_rate` 0.5 → 2, `max_flow_rate` 6 → 10).
- EV charger ("Bil") branch now always visible (`display_zero: true`), showing 0.00 kW when idle instead of disappearing.

Minor release. Bundles the v0.39.20 and v0.39.21 work (not previously released on GitHub) plus a full dashboard redesign.

### Added — redesigned Danish dashboard (EVCC-style single screen)

The dashboard (`dashboard/dashboard_da.yaml`) was rebuilt from a six-tab layout into a single cohesive screen modelled on the EVCC UI:

- **Home** is now one centered panel-mode column (max-width 1000 px on desktop, full width on mobile) instead of scattered tabs. Top to bottom: status + master on/off, current buy/sell price, EV charge status, a centered **Charge mode** selector (Fra · Sol · Sol+Bat · Hurtig · Planlagt), an animated energy-flow diagram, the 24 h price/SoC chart, and a bottom navigation row.
- **Energy flow** uses `power-flow-card-plus` — a single animated PV · battery · grid · house · car diagram — replacing the old markdown flow tables. The car is shown as its own branch and subtracted from house load.
- The five detail pages (EV/OCPP, Priser & Plan, Historik, Indstillinger, Logs) are now **subviews** reached from the bottom navigation, each rendered in the same centered panel style with a back button — they no longer clutter a tab bar.
- **EV mode selector** gains a **Planlagt** (Scheduled) option so the schedules can be activated from the dashboard.

**New dashboard prerequisites (HACS frontend):** `power-flow-card-plus`, `button-card`, `card-mod`, in addition to the existing `mushroom` and `apexcharts-card`.

### Added — schedule safeguard

The EV subview shows a banner ("Skemaer er inaktive lige nu") whenever the master mode is not `Planlagt`, making clear that editing a schedule's mode does not affect live charging unless Scheduled mode is selected. (Investigation confirmed the schedule resolver already ignores disabled slots and inactive modes; the banner removes the ambiguity.)

### Changed

- Removed install-specific per-device notification switches from the distributed dashboard template; two generic examples (Telefon, Tablet) remain.

### Included from v0.39.21

- **Battery capacity auto-detected from the BMS** — `Σ bms_kwh_remaining / (SoC/100)` sampled in the 15–85 % mid-range, fed into the rolling-median capacity learner. Warms up from normal cycling without needing a grid-charge cycle.
- **Active ramp during the battery-full override** — the EV steps up 1 A / 30 s while grid import stays ≤ 0.3 kW, backing off and freezing 120 s when it doesn't, so the charger finds the real PV ceiling instead of staying pinned at minimum.

### Included from v0.39.20

- Priority-SOC gate now only blocks the EV from *starting* (`ev_last_amps == 0`), fixing the export-consumption thrashing where an already-charging EV cycled on/off every ~4 minutes.

### Tooling

- `deploy.py --files-only` — deploy integration files + restart without touching the dashboard.

---

## [0.40.0] — 2026-05-29

Minor release. Bundles the v0.39.20 and v0.39.21 work (not previously released on GitHub) plus a full dashboard redesign.

### Added — redesigned Danish dashboard (EVCC-style single screen)

The dashboard (`dashboard/dashboard_da.yaml`) was rebuilt from a six-tab layout into a single cohesive screen modelled on the EVCC UI:

- **Home** is now one centered panel-mode column (max-width 1000 px on desktop, full width on mobile) instead of scattered tabs. Top to bottom: status + master on/off, current buy/sell price, EV charge status, a centered **Charge mode** selector (Fra · Sol · Sol+Bat · Hurtig · Planlagt), an animated energy-flow diagram, the 24 h price/SoC chart, and a bottom navigation row.
- **Energy flow** uses `power-flow-card-plus` — a single animated PV · battery · grid · house · car diagram — replacing the old markdown flow tables. The car is shown as its own branch and subtracted from house load.
- The five detail pages (EV/OCPP, Priser & Plan, Historik, Indstillinger, Logs) are now **subviews** reached from the bottom navigation, each rendered in the same centered panel style with a back button — they no longer clutter a tab bar.
- **EV mode selector** gains a **Planlagt** (Scheduled) option so the schedules can be activated from the dashboard.

**New dashboard prerequisites (HACS frontend):** `power-flow-card-plus`, `button-card`, `card-mod`, in addition to the existing `mushroom` and `apexcharts-card`.

### Added — schedule safeguard

The EV subview shows a banner ("Skemaer er inaktive lige nu") whenever the master mode is not `Planlagt`, making clear that editing a schedule's mode does not affect live charging unless Scheduled mode is selected. (Investigation confirmed the schedule resolver already ignores disabled slots and inactive modes; the banner removes the ambiguity.)

### Changed

- Removed install-specific per-device notification switches from the distributed dashboard template; two generic examples (Telefon, Tablet) remain.

### Included from v0.39.21

- **Battery capacity auto-detected from the BMS** — `Σ bms_kwh_remaining / (SoC/100)` sampled in the 15–85 % mid-range, fed into the rolling-median capacity learner. Warms up from normal cycling without needing a grid-charge cycle.
- **Active ramp during the battery-full override** — the EV steps up 1 A / 30 s while grid import stays ≤ 0.3 kW, backing off and freezing 120 s when it doesn't, so the charger finds the real PV ceiling instead of staying pinned at minimum.

### Included from v0.39.20

- Priority-SOC gate now only blocks the EV from *starting* (`ev_last_amps == 0`), fixing the export-consumption thrashing where an already-charging EV cycled on/off every ~4 minutes.

### Tooling

- `deploy.py --files-only` — deploy integration files + restart without touching the dashboard.

---

## [0.39.21] — 2026-05-29

### Added — battery capacity auto-detected from the BMS

The integration now learns usable pack capacity directly from the FoxESS BMS `kWh remaining` registers instead of relying on the configured value or a grid-charge cycle:

```
capacity = Σ kwh_remaining / (SoC / 100)
```

One sample is taken per learning tick (5 min) whenever SoC sits in the safe mid-range (15–85 %), summed across all installed battery modules (`_bms_kwh_remaining_1`, `_bms_kwh_remaining_2`, …). The mid-range gate excludes the near-full region, where the BMS holds SoC flat while balancing and `kwh_remaining` lags, and the near-empty region, where a hidden reserve skews the ratio. Samples feed the same rolling-median window as the existing Force Charge learner, so `get_learned_capacity()` stays the single source of truth.

Why it matters: the previous learner only sampled during `Force Charge` cycles, which rarely fire for a PV/arbitrage user — so capacity stayed pinned at the configured default. The BMS method warms up from normal daily cycling, with no grid charging required, and self-updates as the pack ages (tracks SoH).

- `discovery.py`: `discover_bms_kwh_remaining()` — finds all per-module `_bms_kwh_remaining_N` sensors via unique_id suffix match.
- `const.py`: `FOXESS_BMS_KWH_REMAINING` well-known fallback IDs.
- `coordinator.py`: `_resolve_bms_kwh_entities()` (discovery-first, cached), `_get_bms_total_kwh_remaining()` (sums installed modules), `_learn_capacity_from_bms()` (called alongside the Force Charge learner on each learning tick).

### Added — active ramp during the battery-full override

When the house battery is full and export is blocked by the price floor, the FoxESS MPPT self-throttles to match whatever the AC bus draws. The measured solar surplus therefore always equals the EV's own draw, so surplus tracking alone can never discover spare PV — the EV stayed pinned at the minimum (6 A) even when the panels could deliver more.

The override now actively probes for the real ceiling:

- Steps up 1 A at most once per 30 s while grid import stays at or below 0.3 kW (MPPT is keeping up).
- When grid import exceeds 0.3 kW (MPPT can't cover the last step), steps down 1 A and freezes up-steps for 120 s to let things settle.
- Floors at the configured min amps, caps at the configured max amps.
- Resets to min on session end, EV disconnect, or when the override deactivates (export resumes / battery drops below near-full).

This replaces the v0.39.18 "floor, not cap" behaviour inside the override regime: in that regime there is no higher real-surplus reading to preserve, so commanding the ramp ceiling is strictly better. Outside the regime, normal surplus tracking is unchanged. Cost of tracking a moving ceiling: roughly one 10 s tick of ~0.69 kW grid import every couple of minutes (~0.002 kWh) — negligible.

- `const.py`: `EV_OVERRIDE_RAMP_INTERVAL_SECONDS` (30), `EV_OVERRIDE_RAMP_GRID_IMPORT_THRESHOLD_KW` (0.3), `EV_OVERRIDE_RAMP_FREEZE_SECONDS` (120).
- `coordinator.py`: `_amps_to_kw()`, `_update_override_ramp()`, `_reset_override_ramp()`; override apply site reworked to command the ramp value; ramp reset wired into the idle/disconnect paths.

---

## [0.39.20] — 2026-05-27

### Fixed — v0.39.19 priority-gate bypass thrashed when EV's own draw consumed the export

v0.39.19 released the priority_soc gate when `grid_export_kw > min_kw`. Sound in intent (capture exported PV with the EV) but had a steady-state oscillation problem:

1. Gate releases because grid is exporting 4.5 kW
2. EV starts, ramps to 10 A (6.9 kW)
3. EV's own draw consumes what was being exported → `grid_export_kw` falls to ~0
4. Gate re-activates → `_compute_ev_target_kw` returns 0 with "Batteri prioriteret"
5. EV enters stop_window, stops after ~3 minutes
6. EV stops → exports resume → gate releases → cycle repeats every ~4 minutes

Until battery climbed to priority_soc (default 80 %), the system would cycle the EV on and off every ~4 min, achieving roughly 60-70 % capture rate of available solar instead of the ~95+ % a continuous run would deliver. Plus the dashboard would flap visibly.

### Fix

`_compute_ev_target_kw` accepts a new `ev_last_amps` parameter. The priority gate now requires **`ev_last_amps == 0`** in addition to the existing conditions. Once the EV is already charging, the gate is bypassed — surplus tracking alone decides when to stop.

```python
if (mode == EV_MODE_PV
        and battery_soc < priority_soc
        and grid_export_kw <= min_kw
        and ev_last_amps == 0):           # ← new
    return 0, "Batteri prioriteret: …"
```

Rationale: the priority_soc gate's purpose is "don't **start** the EV mid-battery-fill". Re-applying it to an already-charging EV inverts that intent — by the time the gate sees `grid_export_kw == 0`, the EV has already started precisely because the gate let it. The right thing once the EV is running is to let the natural `if solar_surplus < min_kw: return 0` branch handle the stop decision.

### Behaviour change

| Scenario | v0.39.19 | v0.39.20 |
|---|---|---|
| EV IDLE, battery < priority_soc, grid exporting > min_kw | Gate releases, EV starts | Same — no change |
| EV charging, grid_export drops to 0 because EV is consuming it | Gate re-activates, target = 0, stop_window engages, EV stops after ~3 min, cycle | Gate stays released (ev_last_amps > 0), surplus tracking continues, EV keeps running on real surplus |
| EV charging, PV genuinely drops to 0 (heavy cloud) | Same as above (target = 0 from gate) | Surplus < min branch catches it, target = 0 with "PV: overskud … < min" — EV stops via the right code path with the right reason text |
| EV IDLE, battery ≥ priority_soc | Gate already inactive — no change | No change |
| EV charging, battery climbs to priority_soc | Gate would have already released — no change | No change |

The fix is **additive only when EV is charging** — IDLE behaviour is identical to v0.39.19.

### Sites changed

`coordinator.py` only:
- `_compute_ev_target_kw` signature: new `ev_last_amps: int = 0` kwarg
- `_compute_ev_target_kw` gate: AND-ed with `ev_last_amps == 0`
- Docstring updated with v0.39.20 rationale
- Call site in `_run_ev_controller`: passes `ev_last_amps=self._ev_last_amps`

3 lines changed in the function, 1 line changed in the caller, plus docstring.

### What does not change

- v0.39.17 battery-full override path — unchanged.
- v0.39.18 soft cool-down — unchanged.
- v0.39.19 export-gate logic — augmented, not removed.
- `priority_soc` slider semantics — still gates IDLE→start; just no longer interrupts a running session.
- Stop_window, entry debounce — unchanged.

### Risks

- HA restart required.
- Edge case: rapid mode change (user toggles from PV to Locked and back) might leave `_ev_last_amps > 0` briefly while target is being recomputed. The mode check (`mode == EV_MODE_PV`) is evaluated first in the gate condition, so non-PV modes correctly bypass the gate entirely. No new risk.
- No config changes, no new constants, no new sliders.

---

## [0.39.19] — 2026-05-27

### Changed — battery-priority gate now releases when grid is actively exporting

Adds the export-active edge case to PV-mode behaviour. Before this fix, the EV would stay IDLE while `battery_soc < priority_soc` (default 80 %), **even when the inverter was actively exporting surplus to the grid**. With a typical 12 kWh battery filling from 30 % at ~3 kW, the priority hold lasted ~2 hours of cloudless morning. During that window, PV peaks above battery max-charge + house load got exported at sell price while the EV sat idle — a ~0.5-1.0 DKK/kWh net loss per diverted kWh.

### Fix

`_compute_ev_target_kw` accepts a new `grid_export_kw` kwarg. The battery-priority gate now releases when `grid_export_kw > min_kw` — i.e., when the grid is absorbing more than the EV would draw at minimum (6 A / 4.14 kW). The gate's original purpose (don't let the EV raid the battery's morning fill) is moot in that case because PV is already exceeding battery + house combined.

```python
# Before:
if mode == EV_MODE_PV and battery_soc < priority_soc:
    return 0, "Batteri prioriteret: …"

# After:
if (mode == EV_MODE_PV
        and battery_soc < priority_soc
        and grid_export_kw <= min_kw):
    return 0, "Batteri prioriteret: …"
```

Caller in `_run_ev_controller` reads `grid_power_w = evcc_state.get("gridPower", 0)` (positive = import, negative = export) and computes `grid_export_kw = max(0, -grid_power_w / 1000)` before passing it down.

### Behaviour change

| Scenario | v0.39.18 | v0.39.19 |
|---|---|---|
| Battery 60 %, PV exporting 5 kW to grid, EV plugged in PV mode | EV IDLE ("Batteri prioriteret"); 5 kW continues exporting at sell price | EV target = surplus → ramps up to absorb the export. Inverter starts diverting from grid to EV. |
| Battery 60 %, PV all consumed by battery + house (no export) | EV IDLE (gate active, as before) | EV IDLE (gate still active, as before) — no change |
| Battery 90 %, any PV state | EV at surplus tracking (gate already inactive) | EV at surplus tracking — no change |
| Export-stop active (no export by definition) | v0.39.17/18 override path | v0.39.17/18 override path — no change |
| Pure cloud day, no surplus | EV IDLE (no surplus, no export) | EV IDLE (no surplus, no export) — no change |

The fix is **additive** — when the new condition `grid_export_kw > min_kw` doesn't hold, behaviour is identical to v0.39.18.

### Why `min_kw` as the threshold

The threshold is "the EV could fit". If only 0.3 kW is exporting (e.g., 3-phase imbalance noise), starting the EV at 4.14 kW would draw 3.84 kW from somewhere else — battery or grid import. The `> min_kw` threshold ensures the EV's draw is fully covered by the export, no net new grid import.

Alternative thresholds considered but not used:
- `> 0` (any export) — too aggressive, would draw from battery to cover the EV-vs-export gap
- `> 2 * min_kw` — too conservative, misses many real cases
- A user-configurable slider — added complexity for marginal benefit

### Sites changed (coordinator.py only)

- `_run_ev_controller`, evcc_state unpack (~line 2756): added `grid_power_w` read + `grid_export_kw` derivation.
- Call site for `_compute_ev_target_kw` (~line 2865): passes `grid_export_kw=grid_export_kw`.
- `_compute_ev_target_kw` signature: new `grid_export_kw: float = 0.0` kwarg (default 0 preserves backwards compat if any other caller appears later).
- `_compute_ev_target_kw` priority gate: AND-ed with `grid_export_kw <= min_kw`.
- Docstring updated to explain the new bypass condition.

### What does not change

- v0.39.17 battery-full override (for floor-active + battery-full case) — unchanged. Layers on top.
- v0.39.18 floor-not-cap + soft cool-down — unchanged.
- PV+battery mode — unchanged (gate didn't apply there to begin with).
- FULL mode — unchanged (no gate at all).
- LOCKED mode — unchanged.
- `priority_soc` slider — unchanged. User still controls "above this SoC, EV always competes". The new bypass adds "below this SoC, EV competes when there's export to absorb".

### Risks

- HA restart required. EV currently CHARGING via v0.39.18 override; restart will cut briefly (~16 s).
- Behaviour change: PV-mode EV will start earlier on cloudless mornings (when export starts before battery hits 80 %). Intended, but worth knowing.
- No config flow changes, no new constants, no new sliders.

---

## [0.39.18] — 2026-05-27

### Changed — battery-full override is now a floor (not a cap), with a 10-minute soft cool-down between sessions

Two related refinements to the v0.39.17 override.

#### Floor, not cap

Before (v0.39.17): when the override fired, `target_kw` was **unconditionally** forced to `min_kw` (4.14 kW). If real surplus tracking would have returned a higher target (e.g., 6 A wouldn't have been enough — surplus calls for 10 A), the override clamped it down. Net effect: during overcast-but-not-curtailed periods where battery happened to be near full, the EV ran below what the surplus could actually feed.

After (v0.39.18): the override is a **floor**. It only raises `target_kw` to `min_kw` if `_compute_ev_target_kw` returned a value below min. When real surplus tracking returns `≥ min_kw`, the natural value is kept and the EV runs at the higher rate. The override now only kicks in when surplus tracking would otherwise refuse to charge — its proper role.

#### Soft cool-down on override-induced session end

Before: a 15-minute cool-down (`EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS`) was set only when `battery_full_override` was True at the exact moment the EV stopped via stop_window. In practice this rarely fired — by the time the stop confirmed (180 s after surplus first dipped below min), the battery had usually drained enough for `battery_near_full` to flip False, so `battery_full_override` was already False. No cool-down was set. Override fired again as soon as battery refilled (~90 s with a small battery). Cycle every 5-10 minutes.

After: a **session marker** tracks whether the current charging session was ever override-induced. Set on any tick where the override forces the target. Cleared when the EV is idle (`ev_last_amps == 0` at start of next tick) and on disconnect. When the EV stops while the marker is set, a **10-minute soft cool-down** (`EV_OVERRIDE_SOFT_COOLDOWN_SECONDS`) blocks the override from firing again. Long enough to prevent thrashing, short enough that the EV recovers within a reasonable window when sun stabilises.

### Why 10 minutes (not 15)

The v0.36.2 15-min cool-down was for "probe expired with reg 49251 still set — MPPT really won't respond". That's a hard failure mode. The v0.39.18 soft cool-down is for "the override-induced session ended for any reason" — usually transient cloud cover, not a hard failure. Shorter cool-down balances avoiding thrashing against recovering quickly when conditions improve.

### Behaviour change

| Scenario | v0.39.17 | v0.39.18 |
|---|---|---|
| Battery full, export-stop active, real surplus 7 A | Override clamps to 6 A. 1 A of surplus wasted. | Surplus tracking returns 7 A; override doesn't kick in. EV runs at 7 A. |
| Battery full, export-stop active, real surplus 0 (PV curtailed to ~house load) | Override forces 6 A. EV starts. | Override forces 6 A. EV starts. Same. |
| EV charging via override, cloud passes, battery drains to 97 % over 150 s | Override stops firing. EV continues at 6 A via inertia. After 180 s stop_window, EV stops. **No** cool-down set. Battery refills in ~90 s. Override fires again. Cycle every 5-10 min. | Override stops firing. Session marker stays True. EV continues, then stops via stop_window. **Soft cool-down (10 min) fires** because marker was True. Override is blocked for 10 min after the stop. Battery refills in 90 s but override doesn't fire. After 10 min, override can fire again. |
| EV charging via override, MPPT lifts to feed real surplus 10 A | Override clamps EV to 6 A even though 10 A is available. Underutilises sun. | Surplus tracking returns 10 A; override doesn't kick in (real target ≥ min). EV runs at 10 A on real PV. |

### Sites changed

- `const.py` — new `EV_OVERRIDE_SOFT_COOLDOWN_SECONDS = 600` constant.
- `coordinator.py`:
  - Import the new constant.
  - New instance attribute `_ev_session_was_override_induced: bool = False`. Doc-comment explains lifetime.
  - Disconnect handler clears the new marker.
  - Override logic: `override_forcing = battery_full_override and target_kw < min_kw`. Only force target when below min.
  - Session marker reset at start of new session (when `ev_last_amps == 0`).
  - Failure detection rewritten: now triggers on `_ev_session_was_override_induced AND ev_last_amps > 0 AND final_amps == 0`. Uses the new 10-min constant.

### What does not change

- `EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS` (15 min) still defined but no longer set anywhere in `coordinator.py`. Left in `const.py` for backwards compatibility with any external references.
- Override trigger conditions (floor_active + battery_near_full + solar_kw > 0.1) — unchanged.
- start_window bypass — unchanged (passed via `probing=override_forcing`).
- stop_window, entry debounce, recovery guard — unchanged.

---

## [0.39.17] — 2026-05-27

### Changed — curtailment probe replaced with a battery-full override

The v0.36.2 → v0.39.15 curtailment probe is **removed**. In its place is a much simpler battery-full override that doesn't depend on the FoxESS `reg 49251` PV-limited flag.

### Why

Live observation on 2026-05-27, mid-afternoon: battery at 100 % SoC, export-stop block active (price floor crossed), PV throttled from a forecast ~5 kW down to **0.36 kW** actual, EV plugged in and in PV mode, EV IDLE. The probe trigger gate that v0.39.15 broadened — `pv_curtailed AND (floor_active OR battery_near_full)` — still didn't fire, because **`self._pv_power_limited_flag` (reg 49251) reads False on this inverter even when MPPT is plainly throttling**. The probe strategy across four releases (v0.36.2, v0.38.1, v0.38.2, v0.39.12, v0.39.15) was built on a signal that turns out not to fire in the exact case it was designed for.

Trying to keep polishing the probe is a dead end: it's pinned to a quirky Modbus register whose behaviour on real installs doesn't match what the design assumed. Need a different strategy.

### New strategy

When the user-controllable conditions for "definitely want EV to absorb otherwise-wasted PV" all hold, just command the EV to draw min. No state machine, no synthesised solar, no `reg 49251`. The inverter responds to a new sink on the AC bus by lifting MPPT — that's the inverter's job, not Solar AI's to anticipate.

Conditions (ALL required):

1. `effective_mode == EV_MODE_PV` (or scheduled-resolving-to-PV)
2. `battery_soc >= max_soc - 2` (house battery has no headroom)
3. `floor_active` (Solar AI's price-floor block is open — export is blocked)
4. `solar_kw > 0.1` (PV is actually producing something — even if curtailed; prevents trying at night or in deep cloud cover)
5. Cool-down not active (last attempt didn't fail recently)

What stops the EV after a successful override start:

- **Success path:** real surplus tracking takes over once MPPT lifts (normal v0.26.0 surplus-based target). Override remains "active" in the sense that conditions still hold, but the target follows actual surplus.
- **Failure path:** if MPPT doesn't lift, the EV draws min (~4.14 kW for 3-phase 6 A) from the grid. `stop_window` (180 s default) catches it within ~3 minutes, then `EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS` (15 min) blocks retries. Worst-case grid import per failed cycle ≈ 0.21 kWh.

### Code changes

`coordinator.py` only:

- **Removed:** the v0.36.2 probe trigger block, probe state evaluation (60-s window check, expiry, cool-down), synthesised solar block. ~115 lines deleted.
- **Removed:** instance attribute `_ev_probe_started_at` (no longer needed).
- **Added:** ~30 lines computing the override conditions, applying the target override after `_compute_ev_target_kw`, and detecting failure (override active + `ev_last_amps > 0` + `final_amps == 0` → set cool-down).
- **Retained:** instance attribute `_ev_probe_cooldown_until` (reused for failure cool-down).
- **Retained:** `_pv_power_limited_flag` instance attribute and reg-49251 read path — still used by `_update_solar_accuracy` to drop curtailed samples from the learner (v0.39.15 behaviour, unchanged). Just no longer drives the EV probe.
- **Updated:** `_apply_ev_time_window` docstring to reflect that `probing=True` is now sent by the battery-full override instead of by the old probe state machine. The function signature is unchanged.

Net diff: 258 lines changed, -30 net.

### Behaviour change

| Scenario | Before (v0.39.15) | After (v0.39.17) |
|---|---|---|
| Battery 100 %, export-stop active, EV plugged in PV mode, PV throttled, reg 49251 reads True | Probe fires; EV starts within 1-2 ticks (race-fixed in v0.39.12) | Override fires; EV starts within 1-2 ticks. Same outcome. |
| Battery 100 %, export-stop active, EV plugged in PV mode, PV throttled, **reg 49251 reads False** (the observed case) | Probe never fires; EV stays IDLE; PV wasted | Override fires immediately; EV starts within 1-2 ticks |
| Battery 100 %, no export-stop, PV throttled | Probe gate fired (v0.39.15) — EV started absorbing the curtailed PV even without a price-floor block | Override does NOT fire (requires `floor_active`). Behaviour reverts to the v0.38.2 design: without a price-floor block, leave the system alone. |
| Battery not full + price-floor active | Probe fired if `pv_curtailed` (which is rare). EV would start. | Override does NOT fire (requires `battery_near_full`). Behaviour reverts to a stricter design: only fire when the case is unambiguous. |
| Pure grid-side fault | Probe didn't fire (correct). Override doesn't fire (correct). | Same — no change. |

The net narrowing (vs v0.39.15) is intentional. The probe was being broadened in successive releases to cover more cases, but it kept depending on an unreliable signal. The override is narrower but **actually works** for the exact case the user described.

### What does not change

- v0.39.12 start_window bypass when `probing=True` — preserved; the override uses the same flag.
- v0.39.11 symmetric COOLING entry debounce — preserved.
- v0.38.3 stop-recovery guard — preserved.
- v0.39.15 solar-accuracy learner curtailment signal (`floor_active OR mppt_curtailed`) — preserved; that fix was independent of the EV probe and is still useful.
- `EV_CURTAILMENT_PROBE_SECONDS` constant — still imported but no longer referenced in `coordinator.py`. Left in place for now (cleanup possible later).
- No config changes, no dashboard changes, no new constants.

### How to verify after deploy

Plug the EV in while battery is near full and an export-stop is active. Within ~10-20 s of the controller's first tick under these conditions, the EV should start drawing 6 A. Watch `sensor.solar_ai_ev_status` — the `reason` text will read "Override: batteri fuld (XX% / max YY%) + eksport-stop aktiv — EV trækker overskuds-PV". If the override fires but the EV then stops via `stop_window`, the cool-down log line "battery-full override failed — EV stopped via stop_window" will fire, and the next attempt is blocked for 15 minutes.

---

## [0.39.16] — 2026-05-27

### Documentation — README "Recent releases" v0.39.x section updated for v0.39.15

Three small edits to keep the README accurate after v0.39.15:

- Date range corrected from "Released in a single day (2026-05-26)" to "Released over 2026-05-26 → 2026-05-27".
- EV-controller fix count bumped from "three" to "four" to include v0.39.15.
- New bullet describing v0.39.15: the probe trigger gate broadened to `pv_curtailed AND (floor_active OR battery_near_full)`, and the solar learner's `curtailed=` signal broadened to `floor_active OR mppt_curtailed`. Cross-references the v0.38.2 design and explains why grid-side faults remain excluded.

No code changes. Manifest bumped per the project's per-push version rule. All integration code identical to v0.39.15.

---

## [0.39.15] — 2026-05-27

### Fixed — battery-full MPPT curtailment was not captured by the EV or the solar learner

Two coupled bugs flowing from the same misalignment: `pv_curtailed` (the FoxESS inverter's `reg 49251` "PV power limited" flag) was treated as a first-class signal for the EV curtailment-probe **only when combined with `floor_active`** (Solar AI's own price-floor block), and the solar-accuracy learner watched `floor_active` alone and ignored `pv_curtailed` entirely. Result: when the house battery filled up on a bright day and MPPT throttled PV to prevent export (no price-floor block — spot price was perfectly normal), the EV did not start charging and the solar learner saw artificially low actuals and biased its per-hour Solcast factor down.

#### Symptom 1 — EV did not start on battery-full curtailment

User scenario: full midday sun, house battery at 96 % SoC, no price-floor block. The FoxESS inverter throttles PV because the battery has no headroom to absorb more and grid-export would clip against any user-set export limit or the inverter's own internal logic. User plugs in the car. EV controller sees surplus ≈ 0 (because PV is throttled) and stays IDLE.

The v0.36.2 curtailment probe was specifically designed to handle this — synthesise enough demand to lift MPPT, EV draws the freed-up power, real PV catches up. But v0.38.2 had narrowed the trigger gate to `pv_curtailed AND floor_active`, on the rationale that non-price-floor curtailment is "rare 'curtailed for other reasons' cases (grid-operator hard limit, faults) that the EV can't reliably help with anyway". That rationale missed the most common non-floor case: battery-full curtailment, which the EV absolutely can help with — it's the exact mirror of the price-floor case.

#### Symptom 2 — solar learner skewed by curtailed-low actuals

`coordinator.py:992` called `_update_solar_accuracy(..., curtailed=floor_active)` — passing `True` only during price-floor blocks. When MPPT throttled PV for any other reason (battery full, user export limit, transient grid-side issue), the curtailed-low actual reading was fed into the per-hour Solcast factor learner. Over multiple cloudless-but-battery-full days, the learner concluded "Solcast over-estimates" and biased future forecasts downward. Optimiser then planned against under-predicted PV.

### Fix — single change, both sides

`_pv_power_limited_flag` (the inverter's own signal, already read every coordinator tick) is now used as a curtailment indicator in both places.

**EV probe trigger (`_run_ev_controller`, coordinator.py:2780-2820)**:

```python
floor_active = self._current_floor_block is not None
max_soc = int(self._stored.get(
    "battery_max_soc",
    self.config.get("battery_max_soc", DEFAULT_BATTERY_MAX_SOC),
))
battery_near_full = battery_soc >= (max_soc - 2)
if (pv_curtailed
        and (floor_active or battery_near_full)
        and self._ev_probe_started_at is None
        and not probe_cooldown_active):
    self._ev_probe_started_at = now_ts
```

The gate now fires the probe when **either** Solar AI's own price-floor block is open **or** the house battery is at/near `max_soc` (within 2 percentage points). Grid-side faults (where the AC bus would also reject the EV) are still excluded because they typically don't coincide with a full house battery.

**Solar learner curtailed signal (`_async_update_data`, coordinator.py:987-1008)**:

```python
floor_active = self._current_floor_block is not None
mppt_curtailed = self._pv_power_limited_flag
self._update_solar_accuracy(
    current_forecast_w, pv_power_w,
    curtailed=(floor_active or mppt_curtailed),
)
```

Samples are now dropped from learning whenever the inverter reports throttling, regardless of whether a price-floor block is open. Tick-ordering note: `_pv_power_limited_flag` is read once per coordinator update at line ~1468 (after this learning call), so this branch reads the *previous* tick's value — roughly 30 s of latency. Acceptable because MPPT throttling is stable across multiple ticks; the learner only triggers every `LEARNING_TICK_INTERVAL_SECONDS` anyway.

### Behaviour change

| Scenario | Before | After |
|---|---|---|
| Battery full + sunny day + EV plugged in (no price floor) | Probe never fires; EV stays IDLE; curtailed PV wasted | Probe fires; EV starts at min charge within 1-2 ticks (combined with the v0.39.12 race fix); MPPT lifts |
| Price-floor block + EV plugged in (battery any SoC) | Probe fires (unchanged) | Probe fires (unchanged) |
| Pure grid-side fault (battery not full, no floor block) | Probe doesn't fire (unchanged) | Probe doesn't fire (unchanged) |
| Solar learner during battery-full midday | Sample kept → factor biased down → forecast under-predicts | Sample dropped → factor preserved → forecast accurate |

### What does not change

- `EV_CURTAILMENT_PROBE_SECONDS` and the probe state machine — unchanged.
- `EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS` (15-min cool-down after failed probe) — unchanged. Worst-case grid import per failed cycle ≈ 0.29 kWh.
- v0.39.12 race fix (probe bypasses start_window from IDLE) — unchanged; this fix layers on top.
- v0.38.1 drop of strict `battery_near_full` requirement — preserved. v0.38.1 dropped it as a *required* condition; v0.39.15 adds it back as an *alternative* trigger (alongside `floor_active`). The two design rationales coexist cleanly.
- No new constants, no config flow changes, no dashboard YAML changes.

---

## [0.39.14] — 2026-05-26

### Documentation — README "Recent releases" section updated for v0.39.x

The README's "Recent releases" section stopped at v0.38.x. Added a v0.39.x block grouped by theme:

- **Pricing accuracy** (v0.39.6, v0.39.8, v0.39.13) — Strømligning 15-min cache key, DSO tariff Note filter + Energinet 41000, partial-fetch guard
- **EV controller** (v0.39.10, v0.39.11, v0.39.12) — FoxESS-mode backfill, symmetric COOLING entry debounce, curtailment probe / start_window race fix
- **OptionsFlow cleanup** (v0.39.7) — removed obsolete schedule-helper link step
- **Tooling** (v0.39.9) — `deploy.py` path fix
- **Smaller patches** (v0.39.0, v0.39.1, v0.39.2, v0.39.3, v0.39.5) — one-line summaries

No code changes. Documentation only. Manifest bumped per the project's per-push version rule.

### What does not change

- All integration code identical to v0.39.13.
- HA installs already on v0.39.13 see no behaviour change after upgrading to v0.39.14 — the only delta is the README rendered on the HACS / GitHub repo pages.

---

## [0.39.13] — 2026-05-26

### Fixed — partial tariff-schedule fetch could lock the cache onto bad data for 24 hours

The daily tariff-schedule refresh in `coordinator.py` runs two parallel `fetch_tariff_schedule` calls (one for the user's DSO, one for Energinet) plus a feed-in fetch. The result was committed to `self._tariff_schedule` and `self._last_tariff_schedule_refresh = now` regardless of whether either fetch actually returned data. If one side returned an empty `[0]*24` schedule — Datahub rate-limit, transient network blip, anything — the cache silently overwrote the previous good data with the partial result and locked that 24-hour-stale state for a full day.

Observed live on 2026-05-26: after the v0.39.8 deploy this morning, `sensor.solar_ai_nettarif_denne_time` correctly showed 0.217 DKK/kWh (DSO 0.092 + Energinet 0.115 + elafgift 0.01) at hour 10. Several subsequent restarts (v0.39.9 / .10 / .11 / .12) each triggered a fresh tariff fetch. During one of them, the Energinet side returned empty (rate-limited or similar). The cache was overwritten to DSO-only, and `nettarif_denne_time` dropped to 0.1023 (DSO 0.092 + elafgift 0.01). All downstream sensors that use the manual stack — `sensor.solar_ai_24h_priskort`, the Prissammensætning markdown card on the Priser & Plan tab, the optimizer's manual-stack fallback path — were now reading inflated-by-0.115-DKK-per-kWh wrong totals (or in the priskort's case, deflated).

The breakdown sensor `sensor.solar_ai_indkobspris_opdeling` is unaffected: it reads directly from Strømligning's API, not from `_tariff_schedule`.

### Fix

`coordinator.py` around the tariff-schedule commit: check that BOTH the DSO and Energinet fetches returned non-empty data before overwriting the cache.

```python
dso_ok = any(dso_sched)
energinet_ok = any(energinet_sched)
if dso_ok and energinet_ok:
    self._tariff_schedule = [round(d + e, 4) for d, e in zip(dso_sched, energinet_sched)]
    self._feed_in_tariff_dso = dso_feed_in
    self._feed_in_tariff_energinet = en_feed_in
    self._last_tariff_schedule_refresh = now
else:
    _LOGGER.warning("Tariff schedule fetch partial — keeping previous cache; will retry in ~10 minutes.")
    # Advance refresh timestamp by less than the full TTL so the next
    # retry fires after ~10 min, not 24 h.
    self._last_tariff_schedule_refresh = now - timedelta(
        seconds=TARIFF_SCHEDULE_REFRESH_SECONDS - 600,
    )
```

### Behaviour

| Scenario | Before | After |
|---|---|---|
| Both fetches succeed | Cache committed, fresh for 24 h | Same |
| Either fetch returns zeros | Cache overwritten with partial data, locked 24 h | Previous good cache preserved; retry in ~10 min |
| First-ever startup, one side fails | Cache populated with partial garbage | `_tariff_schedule` stays `[0]*24`; retry in ~10 min. Until first full success, manual-stack readers show zero tariff. Strømligning breakdown sensor is unaffected. |
| Permanent failure (e.g. wrong GLN) | Bad data persists 24 h | Retries every 10 min; manual stack stays at last good cache (or zeros on cold start) |

### What does not change

- `TARIFF_REFRESH_INTERVAL_SECONDS = 3600` (hourly price refresh) — unchanged.
- `TARIFF_SCHEDULE_REFRESH_SECONDS = 86400` (daily schedule refresh) — unchanged for the success path.
- Strømligning breakdown sensor — already reads the API directly, unaffected.
- v0.39.8 DSO Note filter + Energinet `{40000, 41000}` codes — unchanged. This patch is a guard against partial fetch failures, not a re-design of the fetch itself.

### Deploying this also fixes today's bad cache

The deploy includes the HA restart, which clears the in-memory cache and forces a fresh fetch. Datahub is responsive right now (verified live), so the fresh fetch should populate both DSO and Energinet correctly. Expected after restart: `sensor.solar_ai_nettarif_denne_time` returns to ~0.207–0.217 (depending on current local hour and DSO time-of-day rate); priskort buy at the current hour returns to ~0.26–0.28; Prissammensætning markdown card matches.

---

## [0.39.12] — 2026-05-26

### Fixed — curtailment probe and EV start-window raced at T=60 s; EV never started under export-stop + PV-limited

When `binary_sensor.solar_ai_eksport_stop_aktiv` is `on` (Solar AI's price-floor block is open) AND the FoxESS inverter reports PV throttling (holding register 49251 = 1), the EV controller is supposed to fire a 60-second curtailment probe (introduced v0.36.2, gated to floor-block-active in v0.38.2). The probe synthesises EV-demand-shaped solar to lift MPPT — the EV starts drawing, the inverter sees the new sink, MPPT releases the throttle, real PV catches up.

But the EV never actually started. Reason: `EV_CURTAILMENT_PROBE_SECONDS = 60` and `DEFAULT_EV_START_WINDOW_SECONDS = 60` were **equal**, and the probe-expiration check ran in `_run_ev_controller` **before** `_apply_ev_time_window` evaluated the start-window. At T=60+δ s (any non-zero tick jitter), `elapsed > 60` flipped True first → probe ended → synthesised solar was cleared → `target_amps` became 0 → `_apply_ev_time_window` returned 0 → the EV never received an OCPP `SetChargingProfile(6 A)` / `RemoteStartTransaction`. The controller then logged "probe window expired with flag still set — MPPT didn't respond" and entered a 15-minute cool-down before retrying. From the outside, the symptom looked like the probe feature was missing or broken.

### Root cause

The probe logic (v0.36.2) and the anti-flap start_window (v0.26.0) were written and tested in isolation. The coupling — start_window requires sustained synthesised surplus that lasts longer than the probe window — was never traced. The misleading log message hid the bug.

### Fix

`_apply_ev_time_window` accepts a new `probing` keyword. When `probing=True` and the EV is idle, the start_window is bypassed and `target_amps` is returned directly. The probe is itself a confidence signal — it only fires under two strict, simultaneous conditions (inverter PV-limited flag set + Solar AI price-floor block open), so the anti-flap protection is unnecessary in this path.

```python
if self._ev_last_amps == 0:
    if probing:
        # Bypass start_window — probe is the confidence signal.
        return target_amps
    # ... existing start_window logic unchanged
```

The single call site in `_run_ev_controller` now passes `probing=probing` (the existing local variable already set by the probe-state machine at lines 2769-2810).

### Behaviour change

| Scenario | Before | After |
|---|---|---|
| Probe fires, EV idle, PV mode | After 60 s race: probe expires → synthesised solar disappears → EV stays IDLE → 15-min cool-down armed. Repeats. | Probe-fire tick: `SetChargingProfile(6 A)` + `RemoteStartTransaction` sent. EV starts drawing within seconds. MPPT has the full 60 s probe window to respond. |
| Probe fires, EV already charging | No change | No change |
| Normal PV start (no probe) | start_window protection unchanged | start_window protection unchanged |
| Probe ends with MPPT having lifted | n/a (EV never started) | Real PV continues driving target; controller stays charging. |
| Probe ends without MPPT lifting | n/a | v0.39.11 entry debounce (10 s) → v0.38.3 stop_window (180 s) → confirmed stop. Worst-case grid import per failed probe attempt ≈ 250 s × ev_min_charge_kw ≈ 0.29 kWh (matches the magnitude estimated by the existing comment at coordinator.py:2735). Cooled down for 15 min before retry. |

### Sites changed

`coordinator.py`:
- `_apply_ev_time_window` signature: new `probing: bool = False` kwarg + docstring section.
- Idle-start branch: bypass block at top of the `ev_last_amps == 0` path.
- Call site at line 2859: passes `probing=probing` (probe state already tracked at lines 2769-2810).

No new constants. No config changes. No dashboard YAML changes.

### What does not change

- `EV_CURTAILMENT_PROBE_SECONDS = 60` and the probe state machine — unchanged.
- `start_window` / `stop_window` user-configurable values — unchanged.
- v0.39.11 cooling-entry debounce — unchanged.
- v0.38.3 stop-recovery guard — unchanged.
- v0.39.10 FoxESS backfill for `ev_charging_now` / `ev_charging_solar` — unchanged.

---

## [0.39.11] — 2026-05-26

### Fixed — EV controller state flapped CHARGING ↔ COOLING on borderline surplus

When solar surplus was hovering near the minimum charge threshold (`ev_min_charge_kw`, e.g. 4.14 kW for 3-phase 6 A) with typical variable-cloud noise of 50-100 W, the dashboard reported the EV state oscillating between `CHARGING` and `COOLING` every 20-30 seconds. Verified from `sensor.solar_ai_ev_status` history on 2026-05-26: 50+ state transitions over 30 minutes while `target_amps` and `last_commanded_amps` were both stuck at 6 the entire time — i.e. the charger never actually stopped, the state name was the only thing flipping.

### Root cause — asymmetric debouncing

`_apply_ev_time_window` had a debounce in only one direction:

| Direction | Behaviour |
|---|---|
| CHARGING → COOLING | **Immediate.** First single tick of `target_amps == 0` set `_ev_surplus_below_min_since_ts = now`, which `_ev_telemetry` reads to flip the state name. |
| COOLING → CHARGING | **10 s sustained recovery required.** v0.38.3 added `EV_STOP_RECOVERY_SECONDS = 10` to prevent the inverse flap (single tick above min during COOLING). |

So a single below-min tick during normal charging dropped the state into COOLING; 10 s of sustained recovery dropped it back. With surplus crossing the threshold every 10-20 s, the state name flapped at exactly that cadence while the charger drew 6 A continuously.

### Fix — symmetric entry debounce

Added `EV_COOL_ENTRY_SECONDS = 10` (mirror of `EV_STOP_RECOVERY_SECONDS`). When `target_amps == 0` and the EV is charging (`ev_last_amps > 0`) and the stop timer hasn't already armed, we now require the surplus to remain below min for `EV_COOL_ENTRY_SECONDS` of sustained ticks before setting `_ev_surplus_below_min_since_ts`. During the debounce window, state stays `CHARGING` and the EV continues drawing at `ev_last_amps`.

New instance attribute `_ev_cool_entry_ts` tracks the first below-min tick. Cleared on any above-min recovery while the EV is still in the pre-COOLING phase, on plug-in, on mode change, and on confirmed COOLING entry. Mirrors the lifetime of the v0.38.5 `_ev_arm_drop_since_ts` field but in the opposite direction.

### Behaviour change

| Scenario | Before | After |
|---|---|---|
| Surplus oscillates ±50 W around min, total time above ≥ 50 % | CHARGING ↔ COOLING flap every 10-20 s; EV draws at 6 A throughout | State stays `CHARGING`; EV draws at 6 A throughout |
| Genuine cloud passes (surplus < min for 30 s) | COOLING from T=0, stops at T=180 s | COOLING from T=10 s (after entry debounce), stops at T=190 s |
| Brief surplus drop during charging (< 10 s) | Single COOLING tick visible in state history | No state change |

Net effect: cosmetic flap eliminated. Actual stop behaviour delayed by `EV_COOL_ENTRY_SECONDS` = 10 s in the worst case (1.06 % of the 180 s stop window — not significant). No change to start_window, stop_window, or recovery logic.

### Sites changed

1. `const.py` — new `EV_COOL_ENTRY_SECONDS = 10` constant with doc-comment explaining the rationale.
2. `coordinator.py` — new `_ev_cool_entry_ts` instance attribute; entry-debounce block in `_apply_ev_time_window`; reset of the new field on plug-in, mode change, and the three exit paths.

### What does not change

- `EV_STOP_RECOVERY_SECONDS = 10` (the v0.38.3 recovery guard) — unchanged.
- `start_window` / `stop_window` (user-configurable in OptionsFlow) — unchanged.
- Actual OCPP commands sent to the charger — same as before.
- All other v0.39.10 / v0.39.9 / v0.39.8 fixes — unchanged.

---

## [0.39.10] — 2026-05-26

### Fixed — `ev_charging_now` and `ev_charging_solar` were hardwired False in FoxESS-only mode

Both flags were computed by walking `loadpoints` (the EVCC `/api/state` `loadpoints` array). In **FoxESS-only mode** there is no EVCC poll, so `loadpoints = []` and `any(...)` returns `False` regardless of what the EV is actually doing. Two visible effects:

1. **`binary_sensor.solar_ai_ev_oplader_solenergi` ("EV på solenergi") was permanently `off`** for FoxESS-only users even while the embedded OCPP server was actively serving a PV-mode charging session. The indicator users rely on to see "EV is absorbing curtailed solar / export-blocked surplus" never lit up.
2. **The optimizer's `should_export` guard ("don't fight EVCC: if EV is fast-charging, hold the battery for it") was never engaged.** Without `ev_charging_now`, the optimizer could decide to export the battery while the EV was simultaneously fast-charging from the grid. Net effect: the battery's stored energy could be exported at sell prices while grid power was used to charge the EV at higher buy prices. Magnitude depends on the user's actual usage of FULL / PV+battery modes.

The same defect class was fixed for `ev_charge_power_w` in v0.28.0 (the v0.28.0 fix added a backfill from the embedded OCPP server). That backfill was never extended to these two flags.

### Sites fixed

`coordinator.py:885-913` — added a single backfill block right after the loadpoints-based computations. When `loadpoints` is empty AND the OCPP draw is above the configured threshold, set the appropriate flag based on `_ev_effective_mode` (the controller's resolved active mode — accounts for `scheduled` mode resolution since v0.36.0):

| `_ev_effective_mode` | Flag set | Why |
|---|---|---|
| `pv` | `ev_charging_solar` | Pure surplus — same as EVCC `pv` mode |
| `pv_battery` | `ev_charging_now` | Uses house battery — same "hold the battery for the EV" rationale as EVCC `minpv` |
| `full` | `ev_charging_now` | Fast charge from grid — like EVCC `now` |
| `locked` | neither | Not charging |

### Behaviour changes for existing users

- FoxESS-only users will now see `binary_sensor.solar_ai_ev_oplader_solenergi` correctly toggle on/off while charging on PV.
- FoxESS-only users in PV+battery or Full mode will see the optimizer correctly suppress battery export while the EV is drawing. PV-only mode users see no behaviour change from the optimizer side.
- EVCC / Hybrid mode users see no change at all (the loadpoints path runs unmodified).

### What does not change

- No dashboard YAML changes. Dashboard is at v0.39.9 state.
- `deploy.py` unchanged.
- All other v0.39.9 fixes (15-min Strømligning cache, OptionsFlow cleanup, tariff filter, dashboard path) remain in place.

---

## [0.39.9] — 2026-05-26

### Fixed — `deploy.py` read from a stale legacy YAML and could destroy the live dashboard

`deploy.py`'s `DASHBOARD_YAML` constant pointed at `dashboard/battery_arbitrage_dashboard.yaml` — a backward-compatibility mirror that was supposed to track `dashboard/dashboard_da.yaml` but had silently drifted to a 1-view stale state. Every routine deploy (including any `--dashboard-only` call) pushed the stale file over the live Lovelace storage. Users editing `dashboard_da.yaml` (the file the README documents) had their edits ignored and risked having their live dashboard overwritten with the 1-view stub on the next deploy.

The v0.39.8 release tarball shipped to GitHub also contained the stale file. Anyone deploying v0.39.8 fresh with the default `deploy.py` mode would have destroyed their dashboard.

### Sites fixed

1. `deploy.py` — `DASHBOARD_YAML` repointed to `dashboard/dashboard_da.yaml` (the canonical Danish dashboard, documented in README).
2. `dashboard/battery_arbitrage_dashboard.yaml` — deleted. The README has documented `dashboard_da.yaml` and `dashboard_en.yaml` as the canonical files for some time; the legacy mirror was a footgun.

### Three dashboard improvements (originally drafted for v0.39.8, lost in the deploy mishap, now re-applied)

These were added to `dashboard_da.yaml` earlier in the session but never landed live because the deploy pushed from the wrong file:

- **Energy-flow card no longer double-counts EV in `total_out`.** Both Oversigt and EV / OCPP energy-flow markdown cards now compute `house = max(load - ev, 0)` (where `load = sensor.foxessmodbus_load_power` is the inverter's total house-side reading, which includes the EV) and use `house` for the "Forbrug" row + the outbound total. The "Forbrug" row is renamed to "Forbrug (ekskl. EV)" to make the exclusion explicit.
- **Conditional export-stop chip on EV / OCPP tab.** A `mushroom-template-card` wrapped in a `conditional` block now appears at the top of the EV / OCPP tab whenever `binary_sensor.solar_ai_eksport_stop_aktiv = on`. Shows the floor price that triggered the block, the activation time, and the spot price at block start. Hidden when export is allowed.
- **EV charge schedule cards on EV / OCPP tab.** The four native v0.38.0 schedule slots (`switch.solar_ai_skema_N_aktiveret`, `select.solar_ai_skema_N_tilstand`, `time.solar_ai_skema_N_starttid/sluttid`) now have dedicated cards: a "Planlagt opladning" summary markdown table at the top followed by four `entities` cards (Skema 1+2 side-by-side, Skema 3+4 side-by-side). Set the EV mode to `Scheduled` to use them.

### Why this came up

`deploy.py` had been pointing at the legacy file since the v0.21.x dashboard reorganisation. The dual-file scheme worked as long as a maintainer remembered to keep them in sync; once that broke, the script silently kept pushing the stale version. The destruction wasn't noticed earlier because the two files had been mostly identical until the recent (v0.36-v0.39) live dashboard work was never mirrored back to either file in the repo.

### What does not change

- `dashboard/dashboard_en.yaml` is unaffected. UK users still import the English version manually.
- Integration code (sensors, optimiser, OCPP server, EV controller) is unchanged from v0.39.8.

---

## [0.39.8] — 2026-05-26

### Fixed — manual-stack network tariffs were both over-included (DSO) and under-included (Energinet)

The `_tariff_schedule[h]` value that feeds the manual price stack (used by `sensor.solar_ai_nettarif_denne_time`, the 24h price chart, and as the fallback when Strømligning data is unavailable) was being assembled incorrectly in two ways that partially masked each other.

#### Bug 1A — DSO over-inclusion: all tier bands summed instead of just the residential one

Danish DSOs publish multiple parallel tariff records on the same day for different customer tiers — Dinel publishes 7 today: tier-A high/low (large industrial), tier-B spreed/high/low (small industrial), tier-C <100 / >100 (residential). Solar AI's existing filters (`require_all_prices=True` + `require_varying_prices=True`) kept all 7 because each tier has a complete 24-hour profile with varying prices. The "identical-profile" dedupe only collapsed C<100 and C>100 (which have the same prices), leaving 6 distinct profiles summed into a single schedule. A residential customer ended up paying for all four bands they don't actually pay for.

Verified against the live Datahub API for Dinel today: old code returned **DSO sum 0.293 DKK/kWh at hour 10** (six bands summed); the correct value is **0.0923 DKK/kWh** (Nettarif C time only).

#### Bug 1B — Energinet system tariff omitted

`ENERGINET_TARIFF_CODES` only included code `40000` (Transmissions nettarif, ~0.043 DKK/kWh). It missed code `41000` (Systemtarif, ~0.072 DKK/kWh), which is a separate flat hourly rate every Danish residential consumer pays. The Energinet contribution to the manual stack was roughly half what it should have been. Strømligning's breakdown lists them as two separate components (`transmission.netTariff` + `transmission.systemTariff`).

#### Net effect

Combined tariff at hour 10 today, before and after:

| Source | DSO | Energinet | Combined |
|---|---|---|---|
| OLD code | 0.293 (6 bands) | 0.043 (40000 only) | 0.336 |
| **v0.39.8 fix** | **0.0923** (Nettarif C only) | **0.115** (40000 + 41000) | **0.2073** |
| Strømligning truth | 0.0923 | 0.115 | 0.2073 |

The two bugs partially cancelled — overstated DSO + missing Energinet system tariff. The dashboard markdown card on Priser & Plan still showed an inflated all-in price (0.468 vs the true 0.325 for the current 15-min slot).

### Sites fixed

1. `tariffs.py` `fetch_tariff_schedule` — added optional `note_substring` parameter. When provided, only records whose `Note` field contains the substring (case-insensitive) are included.
2. `coordinator.py` — DSO query now passes `note_substring="Nettarif C"` (the standard Danish term for the residential time-of-use band, used consistently across the 7 supported DSOs).
3. `const.py` — `ENERGINET_TARIFF_CODES` widened from `{"40000"}` to `{"40000", "41000"}`. Comment updated to enumerate the codes deliberately excluded.

### Customer-tier assumption

The "Nettarif C" filter assumes the user is on the residential C-time band — the standard for ~98% of Danish households and the only DSO tariff residential customers can be on. Tier-A or tier-B users (small/large industrial connections, very rare for HACS installs) would need a future tier-picker in OptionsFlow; not addressed in this patch.

### What does not change

- Strømligning mode is unaffected — the breakdown sensor and the optimizer's `_compute_buy_price` already read from the Strømligning API directly when in `stromligning` mode (since v0.39.5 + v0.39.6).
- Octopus mode (UK) is unaffected.
- The `sensor.solar_ai_24h_priskort` chart still uses the manual stack regardless of buy-price mode. Now that the manual stack is correct, the chart's numbers will match Strømligning for users on either mode. Routing the chart through `_compute_buy_price` for a single source of truth is a separate cleanup.

---

## [0.39.7] — 2026-05-26

### Fixed — leftover OptionsFlow step still asked users to create `schedule.*` helpers

v0.38.0 moved EV charge schedules into the dashboard (native `skema_1..4` entities — `select`/`switch`/`time`/`sensor` per slot, edited directly on the EV / OCPP tab). The OptionsFlow step that asked users to create HA schedule helpers in Settings → Helpers → Schedule and link them per EV mode was supposed to be removed at the same time, but the cleanup was never done. Users opening Configure → OCPP Settings landed on the obsolete "EV-opladningsplaner (v0.36.0)" step before they could reach the entity-mapping step.

### Sites fixed

1. `config_flow.py` — `async_step_ev_schedules` method removed. `async_step_ocpp_settings` now routes directly to `async_step_entities`.
2. `config_flow.py` — unused imports for `CONF_EV_SCHEDULE_LINKS`, `CONF_EV_SCHEDULED_FALLBACK_MODE`, `DEFAULT_EV_SCHEDULED_FALLBACK_MODE`, `EV_SCHEDULE_LINKS_MAX` dropped.
3. `translations/en.json`, `translations/da.json`, `strings.json` — `ev_schedules` step entry removed.

### What does not change

- The legacy `CONF_EV_SCHEDULE_LINKS` data in entry.data is **preserved**. `coordinator.py` still reads it once at setup for one-time migration of pre-v0.38.0 installs (see lines 604–662). New installs and already-migrated installs are unaffected; the migration is idempotent (gated on `"ev_schedules" not in self._stored`).
- Native dashboard schedule entities (`select.solar_ai_skema_N_tilstand`, `switch.solar_ai_skema_N_aktiveret`, `time.solar_ai_skema_N_starttid`, `time.solar_ai_skema_N_sluttid`, `sensor.solar_ai_skema_N`) are unchanged.

---

## [0.39.6] — 2026-05-26

### Fixed — Strømligning cache collapsed 15-min slots to a single hourly value

The cache key in `stromligning.fetch_prices` aligned every entry to the hour boundary instead of the 15-min boundary. Strømligning publishes prices at 15-min resolution (each entry carries `resolution: "15m"`), so for any given hour the four quarter-hour entries all hashed to the same key — last-write-wins, leaving only the `:45` quarter in the cache.

Two downstream effects:

1. **Optimizer plan was priced wrong on every intra-hour slot.** The DP loop iterates at 15-min resolution and calls `_compute_buy_price(slot_start_dt=...)` for each quarter. With the cache collapsed, all four quarters in a given hour received the same price — the `:45` quarter's value — even when the actual `:00`/`:15`/`:30` prices were several times higher. Charge/export decisions were made against this flattened view.
2. **Buy-price-breakdown sensor showed the `:45` quarter's price as the "current hour" value.** This is what surfaced the bug — the sensor reported ~0.43 DKK/kWh for the 09:00 local hour on 2026-05-26 while the user's retailer page showed ~1.13 DKK/kWh (the early quarters of that hour).

### Sites fixed

1. `stromligning.py` `fetch_prices` — canonical cache key now uses `(minute // 15) * 15` instead of `minute=0`. Up to 4 entries per hour are stored under distinct keys.
2. `coordinator.py` `_compute_buy_price` (Strømligning branch) — lookup key built at 15-min resolution. Falls back to an hour-aligned key when the 15-min lookup misses, which handles products/dates where Strømligning returns hourly entries.
3. `sensor.py` `BatteryArbitrageBuyPriceBreakdownSensor._current_stromligning_entry` — same 15-min lookup + hour-aligned fallback. The breakdown sensor now updates four times per hour with the active quarter's components.

### Root cause

The minute collapse was introduced in v0.39.1 as a side-effect of the cache-key format-normalisation patch (which corrected a real bug — `+00:00` vs `.000Z` mismatch causing every lookup to miss). The format normalisation did not require dropping the minute resolution; that was a fingertips error. Doc-comments in all three sites now state the 15-min resolution contract explicitly so the next refactor doesn't strip it again.

### What does not change

- Strømligning cache TTL (24 h) is unchanged.
- Manual-stack and Octopus buy-price paths are unchanged.
- The 24-hour price chart (`sensor.solar_ai_24h_priskort`) uses a different code path (EDS spot + manual stack); not affected by this fix.

### Upgrade behaviour

Cache is in-memory and cleared on HA restart. After deploying v0.39.6, the first coordinator update repopulates the cache under the new (15-min) keys. No migration needed.

---

## [0.39.5] — 2026-05-25

### Fixed — Strømligning buy-price components were always read at the wrong nesting level

The live Strømligning API returns entries shaped like:

```jsonc
{
  "date": "2026-05-25T16:00:00.000Z",
  "price":   { "value": 0.909441, "total": 1.136801, "vat": 0.22736, "unit": "kr/kWh" },
  "details": { "electricity": {...}, "surcharge": {...},
               "transmission": { "netTariff": {...}, "systemTariff": {...} },
               "electricityTax": {...}, "distribution": {...} }
}
```

Three sites in the codebase indexed `entry["price"]["price"]["total"]` (two levels of `price`) and `entry["price"]["details"]` instead of `entry["details"]`. The KeyErrors were silently swallowed by surrounding `try/except` blocks, and every read fell through to the manual fallback or default 0.0. Result: the buy-price-breakdown sensor showed `mode=stromligning` with all components 0.0; the coordinator used the manual stack despite the cache being correctly populated; arbitrage decisions used wrong buy prices.

The wrong nesting has been in the code since Strømligning support was introduced (v0.29.0 / v0.35.1).

### Sites fixed

1. `coordinator.py` `_compute_buy_price` (Strømligning no-overrides branch): `entry["price"]["price"]["total"]` → `entry["price"]["total"]`
2. `sensor.py` `BatteryArbitrageBuyPriceBreakdownSensor.native_value`: same fix
3. `stromligning.py` `get_price_details`:
   - `details = price.get("details")` → `details = entry.get("details")`
   - `inner = price.get("price")` → removed; `total = price.get("total")`, `ex_vat = price.get("value")`

### How this relates to v0.39.1

v0.39.1's cache key normalisation was a defensive improvement (it makes the integration robust against ISO format variations from the API). It didn't fix the buy-price bug because the bug wasn't in the cache key path — it was in the reader paths. Both changes are kept: the cache is correctly normalised AND the readers now use the right nesting.

---

## [0.39.3] — 2026-05-25

### Fixed — UnboundLocalError in v0.39.0 auto-Full call

The v0.39.0 commit added a call to `_maybe_auto_full_negative_price` that referenced `current_buy_price` — a variable that is only defined inside a later grid-charge conditional block in `_async_update_data`. On code paths that didn't enter that block, the variable was undefined and the coordinator threw `UnboundLocalError`, putting the integration in `setup_retry` loop.

Caught during the staged-and-tested cycle before the public push — no GitHub release was made with the broken v0.39.0 / v0.39.1 / v0.39.2 in it. Live HA was briefly in `setup_retry` until v0.39.3 landed.

Fix: use `buy_price_next_slot` instead — same semantic value (the all-in buy price for the current/next slot), defined unconditionally at line ~880 in both the `if grid_slots:` and `else:` branches.

### Internal
- One-line change to `_async_update_data` swapping the variable name.
- Inline comment marks v0.39.3 fix so future readers see the bug-and-fix context together.

---

## [0.39.2] — 2026-05-25

### Added — `binary_sensor.solar_ai_eksport_stop_aktiv` for the EV/OCPP tab

A live indicator that the solar export floor block is currently open — i.e. Solar AI has dropped the export limit register (46616) to 25 W because the live export price is at or below the user's configured `min_export_price`. Useful for dashboard chips that tell the user at a glance "your panels are being clipped right now".

- **state**: `on` when `_current_floor_block is not None`, else `off`
- **attributes**:
  - `since` — ISO timestamp the current block opened
  - `floor` — the price floor that triggered it (DKK/kWh)
  - `price_at_start` — the export price when the block opened (DKK/kWh)

### Internal
- 4 new keys on the coordinator's data dict: `export_stop_active`, `export_stop_start_ts`, `export_stop_floor`, `export_stop_price_at_start`. All derived from existing `_current_floor_block` state — no new internal state.
- New entry in `BINARY_SENSORS` tuple in `binary_sensor.py`. Translation keys in en + da.
- Dashboard chip on the EV/OCPP tab to ship as a Lovelace push (separate from the integration code).

---

## [0.39.1] — 2026-05-25

### Fixed — Strømligning cache lookups always failed silently

The `buy-price-breakdown` sensor (`sensor.solar_ai_indkobspris_opdeling`) reported `mode = stromligning` with all per-component attributes (`spot`, `surcharge`, `net_tariff`, `system_tariff`, `distribution`, `elafgift`) at 0.0 and the state coming from the manual-stack fallback. Concretely on a DK install: dashboard read ~1.39 DKK/kWh while `sensor.stromligning_current_price_vat` read 0.654 DKK/kWh — Solar AI was using the wrong buy price for arbitrage decisions.

Root cause: `stromligning.py fetch_prices` stored each entry under the API's `entry.date` field as-is. Strømligning's API returns timestamps in `"2026-05-20T07:00:00+00:00"` ISO format. The lookups in `_compute_buy_price` (coordinator) and `_current_stromligning_entry` (breakdown sensor) both use `"%Y-%m-%dT%H:%M:%S.000Z"` format. **Mismatch on every slot.** Every lookup silently returned None, every call fell back to the manual stack. Bug was present since v0.35.1 when Strømligning support was introduced.

### Fix

Normalise the storage key in `fetch_prices` to UTC hour-aligned `.000Z` format — matches the lookup format regardless of which ISO variant the API uses. No callers touched, no behavior change other than "lookups now succeed".

### Internal
- ~10 lines added to `stromligning.py`. Existing imports of `datetime`, `timezone` reused.
- Unparseable date fields are skipped with a debug log instead of crashing.

---

## [0.39.0] — 2026-05-25

### Added — Auto-Full on negative buy price (opt-in)

When enabled, the integration automatically promotes the EV master mode to **Full** during negative-price periods and reverts to the previous mode when the price-floor block closes. Designed for the specific situation where:

1. The buy price drops to or below 0 DKK/kWh — you're being paid to import
2. The export floor block is active — solar is being clipped because price is below your `min_export_price`
3. Free grid + wasted PV simultaneously — both reasons to charge the EV as hard as possible

### Behaviour

| Direction | Trigger |
|---|---|
| **Switch to Full (auto)** | Opt-in switch ON *AND* EV plugged in *AND* master mode ≠ Full *AND* `buy_price ≤ 0` sustained for `AUTO_FULL_DEBOUNCE_SECONDS` (5 min) |
| **Switch back (auto)** | Price-floor block transitions from active → inactive (export price rises back above `min_export_price`) |

The pre-promotion mode is stashed and restored on the revert. If you were in PV, you go back to PV. If Scheduled, back to Scheduled. The revert trigger is the floor-block-close edge rather than buy-price-going-positive — it's a single discrete signal Solar AI already tracks, no zero-crossing noise.

### Safety measures

1. **Opt-in.** New switch `switch.solar_ai_auto_full_paa_negativ_pris` — default OFF. Backwards-compatible.
2. **Manual override wins.** If you manually change the master mode while auto-Full is active, the auto state clears and stays cleared until the next negative-price event.
3. **EV unplug resets.** Disconnecting clears the auto state. Next plug-in starts clean.
4. **Verbose logging.** Every transition logs at INFO level so the logbook tells you what Solar AI did and why.

### Known trade-off

If the buy price goes briefly positive (e.g. +0.02 DKK/kWh) while the floor block is still active, you stay in Full mode and pay full price for grid import. Worst-case ~0.24 DKK/hour. Acceptable for the simplicity of the trigger.

### Internal
- `CONF_AUTO_FULL_ON_NEGATIVE_PRICE` config key, `AUTO_FULL_DEBOUNCE_SECONDS = 300`.
- New coordinator state: `_ev_auto_full_active_since_ts`, `_ev_pre_auto_full_mode`, `_ev_neg_price_seen_since_ts`, `_ev_prev_floor_block_active`.
- New method `_maybe_auto_full_negative_price` called once per main update tick after the floor state has been updated.
- `set_ev_mode` accepts a private `_from_auto_full=True` flag so the coordinator's own auto-promotion calls can be distinguished from user-triggered mode changes — manual overrides clear the auto state.
- `BatteryArbitrageAutoFullSwitch` entity in `switch.py`.

---

## [0.38.5] — 2026-05-25

### Fixed — EV start-window no longer resets on noise blips below min

The mirror image of v0.38.3. The stop-window bug was: a brief blip *above* min reset the stop timer, so the EV could never actually stop. The start-window bug is the same shape on the other side: a brief blip *below* min reset the start timer, so the EV could never actually start on borderline surplus.

Observed scenario: master mode PV, surplus hovering at ~4.0–4.3 kW around the 4.14 kW (6 A) minimum. Cloud-flicker took surplus below 4.14 for one tick every 30–60 s. Each dip cleared `_ev_surplus_above_min_since_ts`, so the 60-second start-window timer never accumulated. EV stayed idle for hours. User had to manually switch to Full to force charging.

### Changes

- New constant `EV_START_DROP_TIMEOUT_SECONDS = 10`. Mirrors `EV_STOP_RECOVERY_SECONDS` from v0.38.3.
- New state field `_ev_arm_drop_since_ts: datetime | None`. Tracks "first tick we saw below-min while idle with a start timer running".
- `_apply_ev_time_window` idle-AND-below-min branch: instead of immediately clearing the start timer, require `EV_START_DROP_TIMEOUT_SECONDS` of sustained below-min before clearing. Brief blips keep the timer accumulating; genuine drops clear it.
- The "want to charge while idle" branch clears `_ev_arm_drop_since_ts` (recovery acknowledged).
- Hygiene resets in the EV plug-in event and the non-PV-mode early-return.

### Trade-offs

- The 10 s threshold is symmetric with v0.38.3 — no asymmetry between starting and stopping.
- Genuine sustained drops (clouds rolling in for real, EV cable swap, sun setting) still reset the timer correctly within 10 s. No regression for the "surplus genuinely dropped" path.

---

## [0.38.4] — 2026-05-25

### Fixed — Intra-hour solar correction no longer poisoned by export-floor curtailment

The v0.28.6 short-term solar learner (compares actual PV to Solcast in 15-min slots, computes a rolling ratio over the last 4 slots, applies with 2-hour linear decay) had no guard against the solar export floor. When the user's `min_export_price` is crossed and Solar AI drops the export limit to 25 W, the inverter clips PV to match local load. The learner reads actual=1 kW vs forecast=8 kW, computes ratio=0.125 (clamped to 0.3), and that bad ratio drives the rolling factor for up to 2 hours after the floor closes. The "justeret 24h" / "justeret 6h" forecasts then read ~30% of raw for the rest of the afternoon on otherwise-normal days.

The v0.30.1 fix only filtered the per-hour accuracy learner. The intra-hour learner was missed.

v0.38.4 extends the filter: any 15-min slot in which `_current_floor_block is not None` for at least one tick is discarded at rollover. Its residual is not appended to the ring buffer, and `_st_solar_factor` keeps the last valid value computed from non-curtailed slots. The forecast adjustments resume normally once the floor closes and a fresh clean slot completes.

### New
- `coordinator._st_solar_floor_seen_during_slot: bool` — sticky per-slot flag.
- `coordinator._st_solar_last_curtailed_skip_iso: str | None` — diagnostic timestamp of the most recent skipped slot, exposed on the data dict as `solar_short_term_last_curtailed_skip` so the dashboard / logbook can confirm the filter is firing.
- INFO-level log entry on each skip: `Short-term solar correction: skipping slot HH:MM — solar export floor was active …`

### Trade-off

A few times a year, midday floor blocks during sunny low-price periods will discard up to ~8 slots of learning data. Acceptable — the alternative (factor stuck at 0.3 for 2 hours after the floor closes) was significantly worse.

---

## [0.38.3] — 2026-05-25

### Fixed — EV stop-window no longer resets on noise blips above min

Observed: a car had been plugged in for 30 minutes drawing ~3.9 kW (the 6 A OCPP minimum) entirely from solar — but the dashboard sensors read `target_kw = 0`, `ev_status = COOLING`, `reason = "stoppet"`. The car was physically charging the whole time while Solar AI's state machine thought it was perpetually "about to stop".

Root cause — two issues:

1. **Stop timer cleared on a single tick of recovery.** The anti-flap window for stopping (`stop_window_seconds`, default 180 s) was intended to absorb cloud-flicker on the surplus signal. But the implementation cleared `_ev_surplus_below_min_since_ts` the moment surplus crossed *briefly* above min — even for a single 10-second tick. When the EV is drawing close to min on borderline surplus, the surplus oscillates by 50–200 W. Each oscillation cleared the stop timer, so the 180 s window never completed and the charger held at min indefinitely. From the user's perspective the car was charging fine; from Solar AI's perspective it was always "in the process of stopping but never quite there".

2. **Misleading status during the hold.** While in this state, the controller was actively sending the last-commanded amps (e.g. 6 A) to the charger every tick — but `target_kw`, `target_amps`, and the `reason` sensor all reported as if the EV were stopped. `last_commanded_amps = 6` was the only sensor telling the truth.

### Changes

- **`_apply_ev_time_window` requires sustained recovery before clearing the stop timer.** New constant `EV_STOP_RECOVERY_SECONDS = 10`. When charging with a pending stop, surplus must hold above min for ≥ 10 s before the cool-down resets. Brief noise blips no longer interrupt the count-down.
- **Telemetry reflects reality during cool-down hold.** When `final_amps > 0` while `target_kw == 0` (the cool-down-holding case), `reported_target_kw` is overridden to the actual commanded power and `reason` becomes "PV: overskud N.N kW < min — oplader fortsætter ved minimum (X.X kW) i nedkøling (Ns)". The dashboard now matches the physical state of the charger.

### Internal
- One-line clamp + extra branch in `_apply_ev_time_window`.
- Reason / target_kw override at the end of `_run_ev_controller`.

---

## [0.38.2] — 2026-05-25

### Changed — Curtailment probe now only fires during price-floor blocks

The probe trigger gains a third condition: `_current_floor_block is not None` (Solar AI's existing flag for "price is below the user-configured minimum export floor right now and Solar AI has dropped the export limit to 25 W").

Before: probe fired whenever the inverter reported PV curtailment (reg `49251 = 1`), regardless of the underlying cause. That caught the bread-and-butter case (battery full while the price-floor block was open) plus a handful of rare edge cases (grid-operator hard limits, frequency-response events, inverter faults).

After: probe fires only when curtailment AND the price-floor block is open. The rare cases are skipped — they were a few hours per year at most on typical residential installs, and the probe couldn't reliably help with grid-operator limits anyway (MPPT can't lift past a hard cap).

What this buys: 1:1 correlation between "EV started on a kick-in" and "Solar AI's price-floor logic is currently active". Easier to reason about, easier to debug, and exactly matches what the user actually wants the feature to do.

In-flight probes are unaffected if the floor closes mid-probe — the existing window-expiry / flag-clears end conditions still apply. No stuttering when the price hovers near the floor.

### Internal
- Single-line condition added to the v0.38.1 probe trigger in `_run_ev_controller`.
- Log message updated to mention the floor-block precondition.

---

## [0.38.1] — 2026-05-25

### Fixed — Curtailment probe now triggers on car-swap and post-cloud restart

Two observed cases where the v0.36.2 curtailment probe failed to start the EV even though the inverter was reporting active PV curtailment (reg `49251 = 1`):

1. **Car swap mid-curtailment** — Car 1 charges through a successful probe, finishes, gets unplugged. A few seconds later Car 2 is plugged in. The battery had drifted from 100% down to ~97.5% during the brief gap while covering house load. The probe's `battery_near_full = soc ≥ max − 2 %` precondition (98% with default max 100%) failed, so the probe didn't fire, and Car 2 stayed at 0 A even though MPPT was still curtailed and there was free PV to extract.

2. **Cloud-then-sun restart** — Car charging from a probe-lifted MPPT. Clouds roll in, surplus drops, stop-window (180 s) stops the EV. Over the following 20–30 min of cloud the battery drops ~3 % covering house load. Sun returns, MPPT curtails again, but `battery_near_full` is now False (97% vs ≥ 98% required) — probe blocked, EV stayed idle.

In both cases the user's workaround was to flip the master mode to PV+Battery (which bypasses the surplus calc and uses the battery to gap-fill), then back to PV-only once MPPT had lifted.

### What changed

- **Dropped `battery_near_full` from the probe trigger.** Probe now fires whenever the PV-limited flag is set and the EV is plugged in. The safety net (180 s stop-window) backs out wrong probes within minutes at a worst-case cost of ~0.07 kWh grid import. The original gate was added in v0.36.2 to avoid probing during grid-operator-imposed curtailment that the EV can't help with — point 2 below replaces that protection.

- **Added a cool-down for failed probes.** When a 60 s probe expires with the flag still set (MPPT didn't respond — typically grid-operator hard limit, not the price-floor case), the controller waits `EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS = 900` (15 minutes) before re-probing. Caps wasted grid import to at most ~0.07 kWh per 15 min in pathological cases.

- **Cool-down clears on EV disconnect.** A failed probe earlier in the day no longer blocks Car 2's plug-in from probing legitimately. Each new session is a fresh start.

- **Successful probe clears the cool-down too.** A flag-cleared probe means MPPT did lift, so any prior failure was specific to an earlier set of conditions; don't keep punishing the new state.

### Internal
- New state field `_ev_probe_cooldown_until: datetime | None` on the coordinator.
- New constant `EV_CURTAILMENT_PROBE_COOLDOWN_SECONDS = 900` in `const.py`.

---

## [0.38.0] — 2026-05-24

### Changed — EV scheduling moved entirely into the dashboard (native model)

The v0.36.0 Phase A scheduling required users to create `schedule.*` helpers in Settings → Helpers, then link them in the Configure flow, then flip the master mode to `Scheduled`. Every time-range edit took a Settings → Helpers detour. The v0.37.0 `add_schedule_slot` service that tried to create helpers programmatically required a HA restart to surface them on installs where the schedule integration was dormant. Both were friction.

v0.38.0 drops the dependency on HA's `schedule.*` helper integration entirely. Solar AI now owns the schedule data, owns the UI, and the dashboard is the only place schedules exist.

### New data model

`coordinator._stored["ev_schedules"]` is a list of slot dicts:

```jsonc
{
  "slot": 1, "enabled": true, "mode": "pv_battery",
  "name": "Skema 1",
  "start": "23:00", "end": "06:00",
  "days": ["mon", "tue", "wed", "thu", "fri"]
}
```

Up to `EV_SCHEDULES_MAX` (=4) slots. `end < start` means the window wraps midnight.

### `_resolve_effective_ev_mode` rewrite

Walks `_stored["ev_schedules"]` in slot-order. Returns the first enabled slot where:
- today's weekday is in `days`, and
- the current local time falls inside `[start, end)` (or the wrap-around half if `end < start`)

If no slot matches, falls back to the user-configured fallback mode (unchanged).

### New entities per slot (always created, 1..4)

| Entity | Type | What it backs |
|---|---|---|
| `select.solar_ai_skema_N_tilstand` | select | mode (PV / PV+Bat / Full) — kept from v0.37.0, now reads new data |
| `switch.solar_ai_skema_N_aktiveret` | switch | enabled toggle |
| `time.solar_ai_skema_N_starttid` | time | start (native HA time picker) |
| `time.solar_ai_skema_N_sluttid` | time | end (native HA time picker) |
| `sensor.solar_ai_skema_N` | sensor | state = `active` / `idle` / `disabled` / `empty`; attributes carry days, summary, name |

All four sets always exist so the dashboard cards always have entities to bind to. Empty slots have `state = "empty"` so the dashboard knows to render a "+ Tilføj skema" affordance.

Day toggling is service-driven (no per-day switch spam):

- `battery_arbitrage.toggle_schedule_day` (slot, day)
- `battery_arbitrage.set_schedule_days` (slot, days)
- `battery_arbitrage.add_schedule_slot` — allocates the next free slot with defaults (no HA `schedule.*` helper created, no restart needed)
- `battery_arbitrage.remove_schedule_slot` (slot) — clears the slot's data

### Migration v0.37.x → v0.38.0

On first load, if `_stored["ev_schedules"]` is absent and `ev_schedule_links` exists in the config entry:

1. For each link, look up the linked `schedule.*` helper's per-day attributes.
2. Take the first non-empty range as the new slot's `start`/`end` (one range per day in the new model — multiple ranges are dropped; user can re-edit on the dashboard).
3. Build `days` from the helper's day list.
4. Mode preserves the v0.37.0 `_stored["ev_schedule_link_N_mode"]` override or falls back to the link's `mode` field.

The old `schedule.*` helpers stay in Settings → Helpers (Solar AI doesn't delete user data) but Solar AI no longer reads them. Users can delete the helpers themselves once they're sure the migration looks correct.

### Removed

- The old `BatteryArbitrageEvScheduleLinkModeSelect` class (replaced by the new `BatteryArbitrageEvScheduleSlotModeSelect` that reads `ev_schedules`)
- The `add_schedule_slot` `.storage/schedule` direct-write path (and `schedule_helpers.py`'s `create_solar_ai_schedule` / `delete_schedule_by_entity_id` functions are no longer called by the integration — kept on disk for one cycle to avoid surprise breakages; deletable in v0.38.1)
- The Configure flow's "EV charge schedules" step exposure (kept readable for migration, but no longer editable — the flow step will be removed in v0.38.1)

### Added — `Platform.TIME` to the integration's platform list

So the new start/end time entities can be loaded by HA's `time` component.

### Internal
- 7 new coordinator setters: `set_schedule_slot_mode`, `set_schedule_slot_enabled`, `set_schedule_slot_time`, `toggle_schedule_slot_day`, `set_schedule_slot_days`, `delete_schedule_slot`, `add_schedule_slot_native`.
- `get_schedule_slot(slot_idx)` lookup helper.
- Dispatcher signal `battery_arbitrage_schedules_changed` fires on every mutation so the slot sensors, time entities, and enabled switches re-render in sync.

---

## [0.37.2] — 2026-05-24

### Fixed — Prisparametre card now greys out *all* shadowed manual sliders

v0.37.1 only greyed out the Moms slider in Strømligning / Octopus modes, but the same logic applies to the other two manual buy-component sliders that share the same code path:

- `number.solar_ai_elafgift_dkk_kwh` (Elafgift)
- `number.solar_ai_spotpris_tillaeg_elhandlertillaeg` (Spotpris-tillæg / elhandlertillæg)

Both are ignored by `_compute_buy_price` in `stromligning`-no-overrides and `octopus` modes (the API's `total` / `value_inc_vat` field includes their equivalents) but the Prisparametre dashboard card kept them looking active. Now all three are greyed out together when the API provides the full buy-price stack.

The helper was renamed from `_vat_slider_available` to `_manual_buy_component_available` to reflect its broader role; the old name is kept as a compatibility alias.

No buy-price calculation changed.

---

## [0.37.1] — 2026-05-24

### Fixed — buy-price breakdown card now matches the buy-price mode

A user reported confusion about whether the "Moms på køb" slider was double-applying VAT. Investigation found the slider behaved correctly — `_compute_buy_price` applies it once in `manual` mode and ignores it in `strømligning` / `octopus` modes — but the dashboard's "Prissammensætning" card always recomputed the breakdown locally using the slider value, regardless of the active source. This meant:

- In `strømligning` mode, the card showed the user's manual `number.*` slider values × the slider's VAT, while the optimiser actually used Strømligning's own all-in `total` field. The two numbers could legitimately differ if the manual sliders drifted from Strømligning's components.
- In `octopus` mode, same issue with `value_inc_vat`.

v0.37.1 resolves both:

1. **New sensor `sensor.solar_ai_buy_price_breakdown`** — per-component breakdown of the current slot's buy price, sourced from the live API in `strømligning` / `octopus` modes. Attributes include `mode`, per-component values (`spot`, `surcharge`, `net_tariff`, `system_tariff`, `distribution`, `elafgift`, `subtotal_ex_vat`, `vat_amount`, `vat_pct`, `total_inc_vat`). The state is the current slot's all-in buy price.

2. **Dashboard "Prissammensætning" card branches on `mode`** — renders the manual line stack in manual mode, the Strømligning per-component breakdown in strømligning mode (with VAT derived from Strømligning's `total − value`), and the Octopus VAT-inclusive line in octopus mode. The card now matches whatever the optimiser is actually using.

3. **VAT slider greys out when it has no effect** — `number.solar_ai_moms_pa_kob` is marked `unavailable` in `strømligning` mode without manual overrides, and in `octopus` mode. The slider was already ignored by the coordinator in those modes; now it's also visually communicated. Flipping back to manual mode or enabling Strømligning's manual-overrides toggle restores it.

No buy-price calculation changed — this is a UX and visibility fix.

### Internal
- `BatteryArbitrageConfigNumber` accepts an optional `available_when: Callable[[Coordinator], bool]` argument.
- New `_vat_slider_available` helper encodes the "when is the slider in play?" logic so it stays in one place.
- New `BatteryArbitrageBuyPriceBreakdownSensor` class in `sensor.py`.

---

## [0.37.0] — 2026-05-24

### Fixed — OCPP transaction tracking survives HA restarts (Item 5)

Resolves a class of runaway charging sessions where Solar AI's stop commands (`SetChargingProfile current=0`, `RemoteStopTransaction`) silently failed because the integration had lost track of the active OCPP transaction id after a HA restart or transport reconnect. Two complementary recovery paths:

1. **MeterValues recovery (live path)** — OCPP 1.6 lets chargers include the active `transactionId` on every `MeterValues.req`. `on_meter_values` now parses it and:
   - Adopts it as the current session if the integration has no tracked session (the canonical "after-restart" case — charger keeps charging, Solar AI thought IDLE).
   - Detects drift and re-syncs to the charger's view if a different id arrives (mid-disconnect session swap, e.g. car re-plugged during HA downtime).
   - Seeds `session_start_energy_wh` from the first `Energy.Active.Import.Register` after recovery so the in-session counter starts at 0 rather than going negative against a stale start.

2. **Persistence (cross-restart path)** — `_persist_charger_metadata` now snapshots `session_active`, `session_transaction_id`, `session_start_ts`, `session_start_energy_wh`, `session_energy_wh`, `session_solar_wh`, `session_grid_wh` alongside the existing vendor/model fields. `OcppServer._handle_connection` restores them onto the new `ChargePoint` instance on reconnect, so `RemoteStopTransaction` works from the first tick after HA comes back — before any MeterValues even arrives.

3. **`TriggerMessage(MeterValues)` on reconnect** — `request_status_refresh` now requests MeterValues in addition to Status + Boot. If a session is active when Solar AI (re)connects to the charger, the charger's immediate response carries the `transactionId`, which `on_meter_values` picks up via path (1). Belt-and-braces with path (2).

### Added — `battery_arbitrage.force_stop_charger` service

Brute-force escape hatch for the rare case where the recovery paths above didn't catch the session (e.g. crash before persistence flush, charger that doesn't include `transactionId` on MeterValues). The service walks a list of candidate transaction ids — user-supplied → tracked → 1 → 0 — and sends `RemoteStopTransaction` for each until the charger accepts. Most OCPP chargers stop the only active transaction regardless of the id supplied, so even tx=1 or tx=0 usually works.

Optional parameters:
- `transaction_id: <int>` — try this id first
- `charger_id: <cpid>` — limit to one charger (otherwise targets all connected)

### Added — EV schedules fully managed from the dashboard

Two complementary changes that move EV-charging scheduling out of the Configure flow and onto the EV/OCPP tab:

1. **Per-slot mode select** — each configured schedule link gets its own select entity (`select.solar_ai_skema_N_tilstand`, `N = 1..4`). Options: `PV`, `PV+Bat`, `Full`. The select writes to coordinator storage and `_resolve_effective_ev_mode` reads storage every tick (initial seed from the link dict's `mode` field via a one-shot migration on `async_setup_entry`). Users who already configured schedules pre-0.37.0 keep their setup.
2. **Create / remove schedule helpers from a service call** — two new HA services let the dashboard provision schedule helpers without sending the user to Settings → Helpers:
   - `battery_arbitrage.add_schedule_slot` — picks the lowest unused slot index, creates `schedule.solar_ai_skema_<N>` via the HA `schedule` storage collection, links it in PV mode, reloads the config entry. No params needed.
   - `battery_arbitrage.remove_schedule_slot(slot)` — deletes the helper for `slot` (1–4) and unlinks it.

Locked and Scheduled modes are deliberately excluded from the per-slot dropdown: an empty schedule already "locks" charging during its time window, and a `Scheduled` schedule that defers to another schedule would loop.

The dashboard layout (master mode selector + 4 slot positions with conditional "Opret skema N" buttons + edit-schedule popup) ships in a follow-up Lovelace push using the entity ids verified live after the integration deploy.

### Why

The v0.36.0 EV scheduling Phase A made schedule helpers + the link configuration possible, but every mode change required reopening Configure, and creating a new schedule meant a detour to Settings → Helpers. The dashboard now owns both flows.

### Internal
- `EV_SCHEDULE_LINK_MODE_OPTIONS = [pv, pv_battery, full]` in `const.py`.
- `set_schedule_link_mode(slot_idx, mode)` setter on the coordinator.
- `BatteryArbitrageEvScheduleLinkModeSelect` in `select.py`, one instance per configured link.
- New `schedule_helpers.py` module wrapping HA's `schedule` storage collection — handles both the historical (`hass.data["schedule"]` = collection) and dict-wrapped (`{"storage_collection": coll}`) layouts. Raises a clear error if the internal API ever changes; the rest of the integration continues to work and the user can create helpers manually via the UI as a fallback.
- Translation keys added to `strings.json`, `translations/en.json`, `translations/da.json`.

---

## [0.36.2] — 2026-05-24

### Changed — EV curtailment trigger now reads the inverter, not the forecast

The v0.30.1 forecast-substitution heuristic compared Solcast's predicted PV against actual PV to detect when the export-limit floor was throttling the panels. It worked, but only when (a) Solcast was accurate and (b) the curtailment was caused by Solar AI's own price floor. Other curtailment causes (grid-operator limits, battery-full with low export ceiling, frequency-response events) were invisible to it, and a wrong forecast on a partly-cloudy day could trigger spurious EV starts.

v0.36.2 replaces the heuristic with a direct read of the inverter's own curtailment signal: FoxESS holding register `49251` ("PV Power Limited Flag"). The value is 1 whenever the MPPT is actively throttling PV output, 0 otherwise — regardless of why. The coordinator reads this register every fast tick alongside the existing export-limit write (reg `46616`) and caches the value for the EV controller.

When the flag is 1 *and* the house battery is at/near its configured max SoC, the EV controller launches a 60-second probe: it synthesises just enough solar in the surplus calculation to guarantee `ev_min_charge_kw` of EV demand. MPPT lifts to deliver real PV through the charger, and after the probe ends the live solar reading takes over — no forecast involved. If the flag clears during the probe, the probe ends early and normal surplus control resumes. If the window expires with the flag still set (curtailment cause we can't undo), the probe releases and the existing 180-s stop-window backs the session out within minutes.

What this changes for the user:
- EV kick-start during curtailment is now reactive (factual) rather than predictive (forecast-based).
- Catches grid-operator and battery-full curtailment in addition to the price-floor case.
- No dependency on Solcast forecast accuracy for the EV trigger.
- Worst-case cost of a wrong probe is ~60 s × `ev_min_charge_kw` imported from the grid (≈ 0.07 kWh on three-phase 6 A) before the stop-window backs out.

The forecast remains the input for everything else (DP optimiser, planning chart, dashboard) — only the EV-controller trigger changed.

### New
- `FOXESS_PV_POWER_LIMITED_FLAG_REGISTER = 49251` constant.
- `EV_CURTAILMENT_PROBE_SECONDS = 60` probe-window constant.
- `_read_pv_power_limited_flag()` coordinator helper.
- Per-tick cached `_pv_power_limited_flag` on the coordinator.
- `_ev_probe_started_at` state field tracking an in-flight probe.

### Removed
- The forecast-substitution block in `_run_ev_controller` (`pv_power_w * 2` and `slot_forecast_w > 1000.0` heuristics).

---

## [0.36.1] — 2026-05-24

### Fixed — README note about 15-s card refresh

The v0.36.0 "Known limitations" note about end-to-end 15-second freshness implied that FoxESS Modbus's poll interval was a user-tunable setting and that dropping it was a prerequisite for true 15-s freshness. Both points were inaccurate:

- FoxESS Modbus's poll rate is adapter-specific and not exposed in the UI. `direct` / TCP adapters already poll every ~5 seconds — faster than the integration's new 15-s default. No user action is needed for direct/LAN setups.
- Solcast Solar's poll cadence is rate-limited by the user's API tier (free tier: 10 calls/day ≈ one refresh every 2.4 h). Forecasts change server-side every 30–60 minutes regardless, so a faster local poll wouldn't add freshness.
- OCPP charger data is event-driven (the charger pushes `MeterValues` to the embedded server), not polled.

The README note now reflects all of this. Docs-only change; no code or config behaviour modified.

---

## [0.36.0] — 2026-05-24

### Changed — Default fast-poll interval dropped from 30 s to 15 s

`DEFAULT_FAST_POLL_SECONDS` is now `15` (was `30`). Lovelace cards driven by integration-published sensors (price stack, savings, EV status, surplus, plan, charger live values, intra-hour solar correction, etc.) now refresh in 15 s instead of 30. Migration in `__init__.py` bumps existing config entries from 30 → 15 only when they were on the old default — values the user explicitly customised (e.g. 10 s, 20 s, 60 s) are preserved. Range and `Configure → Live data poll interval` slider unchanged at 10–300 s.

The full freshness gain depends on the data source — see the "Known limitations" note in README about FoxESS Modbus's own poll cadence, which is independent of this integration.

### Added — EV scheduling (Phase A — schedule-driven mode)

New EV charge mode `Scheduled` and a config-flow step "EV charge schedules" that links up to four HA schedule helper entities to EV modes. Use case: charge between specific times on specific weekdays, switching mode automatically (e.g. `Full power` 02:00–06:00 weekdays, `Solar only` 09:00–17:00 weekends), without having to flip the mode select manually or rely on the car's internal timer.

- Users create HA schedule helper entities themselves at *Settings → Helpers → Schedule* — HA's native helper provides per-weekday time-range editing in a mature UI. Solar AI then links each schedule to an EV mode.
- New `EV_MODE_SCHEDULED` value added to the EV mode select (alongside Locked / Solar only / Solar + battery / Full power).
- New `CONF_EV_SCHEDULE_LINKS` (list of `{schedule_entity, mode}` dicts, up to 4) and `CONF_EV_SCHEDULED_FALLBACK_MODE` (used when no link is currently active; defaults to `locked`).
- Coordinator resolves the effective mode once per tick via `_resolve_effective_ev_mode()` — walks links in order, first whose schedule entity is `on` wins. Existing battery-lock and anti-flap logic operate on the resolved effective mode, so a schedule that resolves to `Full power` still gets the actual-draw battery lock (v0.30.1) and a schedule resolving to `Solar only` still gets the anti-flap windows.
- New telemetry attributes on `sensor.solar_ai_ev_status`: `ev_effective_mode` (the resolved mode) and `ev_active_schedule_link` (which schedule is currently in control). When mode is non-scheduled, effective == active and the link is null.

Migration: existing config entries get `CONF_EV_SCHEDULE_LINKS = []` and fallback = `locked`. No behaviour change unless the user explicitly opts into the scheduled mode by selecting it on the EV mode select.

Phase B (optimiser-driven departure-by-time scheduling) deferred to a future release.

---

## [0.35.1] — 2026-05-23

Combined release of four iteration cycles (internally labelled 0.29.0 → 0.30.1) that were staged locally and tested on the user's HA between 2026-05-19 and 2026-05-22. Shipped together as v0.35.1 to keep the public release history tight while preserving the per-feature breakdown below.

### Headline changes
- Strømligning retailer pricing for Danish users (consumer-side all-in price stack via the Strømligning public API, with optional per-component overrides).
- Sell-side company picker — curated list of common Danish solar-export buyers with their typical commission.
- Country picker (Denmark / United Kingdom) — switches which smart-pricing source is offered.
- Octopus Energy retailer pricing for UK users (Agile, Tracker, Cosy, Go, Fixed and more via the free public Octopus API; 14 UK GSP regions).
- Solcast HA integration 2× units bug fix (was silently doubling forecast values on v4.x+).
- "Fuld kraft" EV charge mode now defers the house-battery discharge lock until the car actually starts pulling power (fixes the overnight-lock bug with cars that have their own internal charge timers).
- Spot price area + Danish tariff fetch are now editable from *Configure* (previously required a `const.py` edit).
- Solar visibility / curtailment handling for the EV controller when the export floor is active.

### Detailed breakdown (per iteration)

---

## [0.30.1] — 2026-05-22

### Added — Spot price area + Danish tariff fetch now configurable

The two Danish-specific settings that previously required a `const.py` edit are now editable from *Settings → Solar AI → Configure*:

- `CONF_PRICE_AREA` — dropdown of Nord Pool zones (`DK1` western Denmark / Jutland + Funen, `DK2` eastern Denmark / Zealand). Drives which area the Energi Data Service Elspotprices fetch queries. Default unchanged at `DK2` for backward compatibility.
- `CONF_TARIFF_FETCH_ENABLED` — toggle for the Danish DatahubPricelist tariff fetch (DSO time-of-use + Energinet system tariff + indfødningstarif). Default on. Turning off skips the daily fetch block entirely so the manual stack runs without API calls — appropriate for installs outside Denmark.

### Changed — "Fuld kraft" battery lock now follows actual charging window

The house-battery discharge lock in `EV_MODE_FULL` previously engaged the moment FULL mode was selected, based on the controller's amp setpoint. Symptom: if the car had its own internal charge timer (e.g. set to charge 02:00–06:00) and the user selected FULL at 22:00, the house battery was locked from 22:00 until 06:00 — eight hours unusable — even though the car only actually pulled power for the last four.

The lock condition now reads observed charger power (`ev_current_kw`) and engages only when draw exceeds `EV_BATTERY_LOCK_POWER_THRESHOLD_KW` (0.3 kW). Releases automatically when draw drops. Works with any car timer arrangement without extra configuration.

### Fixed — Solar visibility for the EV when the price floor is active

Two related problems while the solar export floor was throttling the panels (export limit at 25 W, typically when the spot price was at or below the user's configured floor):

1. **EV controller saw no surplus.** When the house battery was at/near `max_soc`, the FoxESS MPPT throttled the panels to match local consumption — `pv_power ≈ load`, and the EV controller's surplus calculation came out near zero. The EV refused to start even though sun was available for the taking. The controller now substitutes the forecast PV value into the surplus calculation when (a) the floor is active, (b) battery SoC ≥ `max_soc − 2`, (c) the slot's forecast exceeds 1 kW, and (d) actual production is less than half of forecast (clear curtailment signal). Once the EV starts pulling, panel MPPT rises to match real demand; if the forecast was wrong, the existing anti-flap stop-window (default 180 s) ends the session before any meaningful battery or grid draw.

2. **Per-hour solar accuracy learning was poisoned.** During curtailment the integration was sampling `(forecast, actual)` pairs where actual was deliberately throttled — pushing the per-hour learned accuracy factor toward "panels always under-perform" even though that's just the price-floor throttle. `_update_solar_accuracy` now accepts a `curtailed=True` parameter; the call site passes `True` when the floor is active, and the sample is dropped instead of recorded.

Migration: existing config entries are seeded with the new fields defaulted to current behaviour (DK2, tariff fetch on). No user action required.

---

## [0.30.0] — 2026-05-20

### Added — Country picker and Octopus Energy retailer pricing (UK)

Solar AI now supports UK users with native Octopus Energy retailer pricing alongside the existing Danish Strømligning path. The buy-price source step in the options flow asks the user to pick a country first, then offers the relevant smart-pricing source.

- New `CONF_COUNTRY` field with two options: `denmark` (default, current behaviour) and `uk`. Adding more countries later only requires extending `COUNTRY_OPTIONS` plus the matching buy-price mode branch.
- New `BUY_PRICE_MODE_OCTOPUS` mode available when country is UK.
- New `octopus.py` transport module with `fetch_products()`, `fetch_prices()`, and `load_bundled_products()`. Uses the free public Octopus REST API at `api.octopus.energy/v1`, no auth required.
- Bundled product catalogue in `data/octopus_products.json` (32 products, ~15 KB), used by the config-flow dropdown so first-install setup works offline. Refreshed on each release.
- Coordinator caches Octopus prices daily on the same trigger as the existing tariff and Strømligning refreshes. The buy-price helper `_compute_buy_price()` routes through Octopus when the mode is set, with `value_inc_vat` (already includes UK's 5% VAT) used directly as the per-slot price. Falls back to the manual stack on cache miss or transport failure.
- New options-flow fields: `CONF_OCTOPUS_PRODUCT_CODE` (e.g. `AGILE-24-10-01`) and `CONF_OCTOPUS_REGION` (UK GSP letter A–P). The 14 UK GSP regions are listed in `OCTOPUS_GSP_REGIONS` with their DNO names so users can pick the right one without knowing the letter convention.

Sell-side support for Octopus (Outgoing Agile, SEG products) is **not** in v0.30.0 — UK users use the existing manual seller-fee slider for now. The plumbing is in place to add it later as a small follow-up.

Manual mode remains the always-available fallback for all countries. Non-Octopus UK customers (~85% of the UK retail market) can use manual mode with their flat unit rate and standing charge handled outside the integration.

Migration: existing config entries get `CONF_COUNTRY` defaulted to `denmark`, preserving current behaviour for every existing install. UK users opt in via *Configure → Buy-price source*.

### Known limitation — DKK labels on GBP-configured installs

UK users who set the currency to GBP get functionally correct price math (Octopus returns pounds, all main price sensors render `GBP/kWh` correctly), but several surfaces still show `DKK/kWh` as a hardcoded literal:

- Six number-entity sliders (spot markup, elafgift, sell-side fee, min export price, battery degradation cost, min arbitrage spread).
- Two savings-related sensors.
- Mode-change notification text in the coordinator.
- Slider labels in `strings.json` carry the parenthetical `(DKK/kWh)`.

The Danish-specific term "Elafgift" also remains visible in the English UI. Fixing these surfaces requires replacing the hardcoded units with the same currency-template substitution already used by the main price sensors. Deferred to a follow-up release; the math is unaffected.

---

## [0.29.1] — 2026-05-20

### Fixed — Solcast HA integration unit interpretation (2× over-forecasting)

The integration was reading `pv_estimate` from the Solcast HA integration's `detailedForecast` attribute as **kWh per 30-min slot** and dividing by `dur_h` to convert to average power. In Solcast HA integration v4.x and newer, `pv_estimate` is already in **kW** (average power during the slot, matching the `device_class: power` sibling sensors). The division was doubling every forecast value.

Symptoms: forecasted peak ~2× the user's actual PV system DC capacity. Per-hour accuracy learning (4-day rolling EMA factor) was silently compensating around 0.5–0.7, so the optimiser plans were roughly correct, but the Solcelleprognose chart's grey raw-Solcast columns showed implausibly high values (e.g. 13 kW peak for a 9.4 kWp system).

Fix:
- `_fetch_solar_from_solcast` now auto-detects the unit semantic by comparing the max value in `detailedForecast` against the sibling `peak_forecast_today` / `peak_forecast_tomorrow` sensor (which is unambiguously in W with `device_class: power`).
- If ratio matches 1:1 → values are kW (modern), used directly: `watts = value × 1000`.
- If ratio matches 1:2 → values are kWh per period (legacy Solcast v3.x), divided by `dur_h` as before.
- Defaults to kW interpretation when the peak sensor can't be found.

After the fix the integration's per-hour accuracy learning will gradually drift back to ~1.0 over 4 days as fresh samples roll in. The optimiser keeps making the same decisions throughout — only the displayed numbers correct themselves.

---

## [0.29.0] — 2026-05-20

### Added — Strømligning retailer pricing and expanded DSO support

Solar AI can now source its buy-side price stack directly from Strømligning's public API, which aggregates every Danish electricity retailer's per-15-minute all-in price. The user picks DSO + retailer + product; the integration fetches the breakdown daily and uses it in place of the manually-composed `(spot + markup + DSO tariff + Energinet + elafgift) × VAT` stack.

The existing manual stack remains the default and is unchanged. Existing installs keep working without any configuration changes.

- **Phase A — expanded DSO coverage**: `DSO_OPTIONS` in `const.py` now lists Dinel, Radius, Cerius, N1, TREFOR El-Net, Vores Elnet, and Elnet Midt with verified GLN numbers and price-area mappings. Each entry also carries the matching Strømligning supplier id so the retailer dropdown filters automatically.

- **Phase B — Strømligning integration**:
  - New module `stromligning.py` with `fetch_prices()`, `fetch_suppliers()`, `fetch_companies()`, and `get_price_details()`. Transport-only, with graceful fallback to bundled offline snapshots when the API is unreachable.
  - Bundled snapshots in `data/stromligning_suppliers.json` and `data/stromligning_companies.json` (47 KB + 13 KB), refreshed each release. First-install setup works fully offline.
  - New constants `CONF_BUY_PRICE_MODE` (`manual` | `stromligning`), `CONF_STROMLIGNING_SUPPLIER_ID`, `CONF_STROMLIGNING_PRODUCT_ID`, `CONF_STROMLIGNING_CUSTOMER_GROUP`, `CONF_STROMLIGNING_USE_MANUAL_OVERRIDES`. All default to preserve current behaviour.
  - New options-flow step "Buy-price source" added between battery parameters and OCPP settings. New users default to `manual`; switch to `stromligning` to pick a retailer.
  - Coordinator caches Strømligning prices daily and routes both the stats block (`buy_price_min`, `buy_price_p25`, `buy_price_next_slot`) and the DP optimiser's per-slot buy price through a single helper `_compute_buy_price()` that branches on the configured mode.

- **Override mode**: when `stromligning_use_manual_overrides` is true, the integration uses Strømligning's spot/distribution/transmission components but the user's VAT / markup / elafgift values. Useful when a regulatory change hasn't propagated to Strømligning's database, or when a contract has a markup not in their catalogue.

### Added — Sell-side company picker

The Danish sell-side (solar-export) market is separate from buy-side retail — many users have a different company paying them for excess solar than the one charging them for consumption. Strømligning's API is buy-only, so this is a curated list maintained in `const.py`.

- New `CONF_SELL_SIDE_COMPANY` field on the same "Buy-price source" options-flow step. Dropdown of ~9 common Danish solar-export buyers (Andel Indfødningsaftale, NRGi Solcellepris, EWII, Tibber, Modstrøm, etc.) with their typical per-kWh commission, plus "same as buy-side retailer" (no fee) and "Custom" (use the manual slider).
- Coordinator resolves the export fee at runtime: if a curated company is selected, its `fee_dkk_kwh` overrides the slider value; otherwise the existing dashboard Sell-side fee number entity is the source.
- Fees in the list are starting points sourced from public price lists; users should verify against their actual contract. The list ships as data and updates per release.

Sell-side DSO + Energinet feed-in production tariff fetches from Energi Data Service are unchanged and continue to be deducted automatically on top.

Migration: existing config entries get all new fields seeded to safe defaults on first load (`buy_price_mode=manual`, `sell_side_company=custom`). No user action required to keep current behaviour. To opt in to either picker, go to *Configure → Buy-price source*.

---

## [0.28.7] — 2026-05-19

### Added — User-configurable OCPP charger compatibility

The two charger-quirk workarounds introduced in v0.28.0 and v0.28.1 are now exposed as settings in *Configure → OCPP Settings*, so the integration can be tuned to spec-compliant chargers as well as the FoxESS L11PMC it was originally developed against.

- New `CONF_OCPP_RESTART_STRICT` (default `False` = Lenient, preserves current behaviour for existing installs). When set to True, RemoteStartTransaction is only fired when the charger reports `Preparing`, `SuspendedEV`, or `SuspendedEVSE` — the OCPP 1.6 spec set. When False (default), `Charging` and `Finishing` are also accepted, which is required for the FoxESS L11PMC and any charger that lingers in non-spec states after a cool-down stop.
- New `CONF_OCPP_REMOTE_START_COOLDOWN_S` (default 30 s, range 5–300 s). Minimum gap between consecutive RemoteStartTransaction attempts on the same charger, previously hardcoded. Cooldown is still automatically cleared on every clean StopTransaction (the v0.28.1 fix), so this only throttles the within-failed-start retry loop.

Migration: existing config entries get both fields set to their defaults on first load of v0.28.7, so behaviour is identical for current users until they choose to change it.

The other two charger-related fixes from v0.28.0 / v0.28.1 — zeroing `cp.power_w` on `StopTransaction` and on non-charging StatusNotifications, and clearing `last_remote_start_attempt` on `StopTransaction` — remain hardcoded because they are universally correct under the OCPP 1.6 spec.

---

## [0.28.6] — 2026-05-19

### Added — Short-term solar forecast correction (Kalman-style intra-hour layer)

The existing per-hour accuracy correction is a 4-day slow-moving average — great for fixing systematic bias (your roof + Solcast settled at factor ≈ 0.7), but blind to the kind of "Solcast didn't see this cloud bank" miss that wrecks solar-only EV decisions in real time. v0.28.6 adds a second correction layer on top.

- **Per-tick PV residual tracking**: every coordinator tick the actual PV output is sampled and accumulated into the current 15-min slot, alongside the matching Solcast forecast value. On slot rollover, `actual_mean / forecast_mean` is computed and appended to a rolling ring of the last 8 closed slots (2 h of history).
- **Short-term multiplier**: `_st_solar_factor = mean(ratio over last 4 closed slots)` (= 1 h smoothing), clamped to [0.3, 2.0]. Recomputed every time a slot closes.
- **Linear decay across 2 h**: when forecasting future slots, `get_short_term_solar_factor(hours_ahead)` blends the short-term multiplier with 1.0 linearly across `_st_solar_decay_hours` (default 2 h). At t+0 → full short-term influence; at t+2 h → no influence; the long-term per-hour factor takes over from there.
- **Applied in both the optimizer and the 48 h chart**: the DP optimizer's `_slot_factor` and the Solcelleprognose chart's `_solar_adj_factor` now both call `get_short_term_solar_factor` so the adjusted curve the user sees on the chart matches exactly what the optimizer plans against.
- New `sensor.solar_ai_solcelleprognose_fejl_nu` (Danish) / `sensor.solar_ai_solar_forecast_error_now` (English): state is the current short-term deviation in percent (`+15%`, `-25%`, etc.). Attributes expose the recent ratio samples, sample count, raw factor, and decay window — so you can see exactly which 15-min slots are feeding the rolling correction.

---

## [0.28.5] — 2026-05-19

### Fixed — Stale ARMING timer rendered "Starter om -178 sek"

- `coordinator.py` (`_apply_ev_time_window`): when target drops to 0 and the EV is already idle, the function now clears any lingering `_ev_surplus_above_min_since_ts`. Previously this path was a bare `return 0`, so an arm timer set earlier (when surplus was above min) survived the surplus dropping below min — leaving the state machine in `ARMING` with an `arming_until` timestamp permanently in the past. Dashboard then rendered the countdown as a negative integer.
- Dashboard template clamped to `max(remaining, 0)` as belt-and-braces defence so even a transient one-tick lag in clearing `arming_until` no longer shows a negative second count.

---

## [0.28.4] — 2026-05-19

### Added — EV session log with grid / solar energy split

- `ChargePoint` now integrates a per-tick grid-vs-solar energy split during each active session by comparing live EV draw against the current solar surplus (PV minus non-EV house load). Numbers are approximate (depend on coordinator tick cadence) but make it visible how much of a charge actually came from the panels vs the grid.
- Each completed session in `sensor.solar_ai_lader_sessions_log` (formerly only exposed via `last_session`) now also carries `energy_kwh_solar` and `energy_kwh_grid` alongside the existing `energy_kwh`, `duration_min`, `start_ts`, `end_ts`, and `avg_power_kw` fields.
- New `sessions` attribute on the session-log sensor lists the last 20 completed sessions newest-first — ready for a dashboard history table.
- Live in-progress split also surfaced as `live_solar_kwh` / `live_grid_kwh` attributes so a session-in-progress card can show "currently 80% solar / 20% grid".

### Added — Dashboard cards

- "Bil tilsluttet" Mushroom card at the top of the EV / OCPP tab — clearly tells you whether a car is plugged in, and lets you tap through to the rest of the tab.
- Charge session history table on the Logs tab — start/stop, duration, total kWh, and the grid/solar split for each session.

---

## [0.28.3] — 2026-05-19

### Added — Daily forecast totals (today remaining + tomorrow)

- Two new sensors: `sensor.solar_ai_solcelle_rest_af_i_dag` and `sensor.solar_ai_solcelle_forventet_i_morgen`. Both expose the adjusted (per-hour-accuracy-scaled) kWh figure that the optimizer plans against — so what the user sees on the dashboard matches the number behind the charge/export plan.
- Both totals are also published as attributes (`today_remaining_kwh`, `today_remaining_raw_kwh`, `tomorrow_kwh`, `tomorrow_raw_kwh`) on `sensor.solar_ai_solcelleprognose_48t_graf` for easy use in the chart card header.
- Dashboard: small subtitle row added above the 48-h chart on the EV / OCPP tab showing both numbers.

---

## [0.28.2] — 2026-05-19

### Added — Solcast 48-hour forecast chart on EV tab

- New `sensor.solar_ai_solar_forecast_48h_chart` — exposes the full 48-hour PV forecast as a per-slot list under the `slots` attribute. Each entry carries `start` (ISO timestamp), `raw_kw` (raw Solcast / Forecast.Solar value), `adj_kw` (scaled by the per-hour accuracy factor — i.e. the same "solcelleprognose" adjustment the DP optimizer plans against), and `factor`.
- ApexCharts card added to the bottom of the EV / OCPP tab. Renders a two-series chart spanning "now → +48 h": a thin grey column series for the raw forecast and a thick amber line for the adjusted forecast. Makes it instantly visible when sun is expected and how much the per-hour calibration is shaving off.

---

## [0.28.1] — 2026-05-19

Hot-fix after the first day of solar-only EV charging. The 180 s anti-flap cool-down was stopping the session correctly when a cloud rolled in, but the controller never re-started the car when the sun came back — the dashboard kept showing "charging" while the car drew 0 kW. Also: the start/stop countdown only refreshed every 30 s.

### Fixed — Solar-only restart never fired after cool-down stop

- `coordinator.py`: broadened the post-stop restart guard from the narrow `{Preparing, SuspendedEV, SuspendedEVSE}` status set to the full plugged-in set `{Preparing, Charging, SuspendedEV, SuspendedEVSE, Finishing}`. Many chargers (incl. the L11PMC) linger in `Finishing` after a session ends, or stay in `Charging` with the 0 A profile still applied — both were silently excluded. With `session_active` already gating the start, it's safe to fire `RemoteStartTransaction` from any plugged-in state.
- `ocpp_server.py`: `on_stop_transaction` now clears `last_remote_start_attempt`, so a stale 30 s cooldown timestamp from earlier in the day can't block the next legitimate restart after the cool-down stop.

### Added — Live per-second countdown on EV anti-flap timer

- `coordinator.py`: telemetry now also exposes `ev_arming_until` and `ev_cooling_until` as ISO timestamps in addition to the existing `*_seconds_left` integers.
- `sensor.py`: `sensor.solar_ai_ev_status` surfaces the new `arming_until` / `cooling_until` attributes so the dashboard can render a true per-second countdown by subtracting `now()` instead of rendering a value that only refreshes every 30 s coordinator tick.

---

## [0.28.0] — 2026-05-19

Major fix release after the user spotted several real bugs during the first full day of live operation. The standout is that the optimizer had been planning pointless grid-charges (12:00 yesterday, 05:15 this morning) because its solar forecast was reading 0 kWh/24h — the configured Forecast.Solar entity didn't actually expose hourly data, and the Solcast source wasn't wired up for the two-entity (today + tomorrow) layout.

### Added — Solcast 48-hour forecast (today + tomorrow)

- New `CONF_SOLCAST_TOMORROW_ENTITY` — second Solcast sensor for tomorrow's `detailedHourly` forecast. When set alongside the existing today-entity, Solar AI merges the two into a true 48-hour PV forecast that the DP optimizer can plan against.
- `try_solcast()` wrapper now reads both entities, de-duplicates midnight overlap, and returns a sorted rate list.
- Existing `forecast_solar` source still works for single-entity Forecast.Solar setups; Solcast is now the more accurate option for 48-h planning.

### Fixed — EV draw double-counted in house-load model

- The `home_power_w` from FoxESS Modbus's `load_power` sensor includes the EV charger draw. The hourly house-load *learning model* was being fed this raw value in FoxESS-only mode because `evcc_state["loadpoints"]` is empty and `ev_charge_power_w` defaulted to 0 — so the subtraction in `base_load_kw = home_power_w - ev_charge_power_w` was a no-op. Over time the learned profile got inflated with EV-charging hours.
- Fix: when `ev_charge_power_w` is 0 from EVCC, backfill from the embedded OCPP server's `ChargePoint.power_w`. The EV's real draw is now correctly subtracted in all live-data modes.

### Fixed — `lader_effekt` sensor stuck after charger stops

- The OCPP `MeterValues` stream updates `cp.power_w` as the charger reports power. But when a session ends, the L11PMC doesn't send a final 0-W frame — so `cp.power_w` (and the `sensor.solar_ai_lader_effekt` it backs) stayed at the last reading (e.g. 4.7 kW), even though the charger was idle. Energy-flow card showed phantom EV consumption.
- Fix: zero `cp.power_w` in two places:
  - `on_stop_transaction` handler (explicit session end)
  - `on_status` handler when new status is `Available` / `Finishing` / `Faulted` / `Unavailable` / `Reserved` (any non-charging state)

### Fixed — Køb / Salg chips on Oversigt showed wrong price tier

- The `Køb` mushroom chip on the Overview tab read `sensor.battery_arbitrage_naeste_slots_pris` which returns a pre-VAT/pre-tariff value (~0.57 DKK). The correct consumer-side buy price for the current hour is in the `slots` attribute of `sensor.solar_ai_24h_priskort` (~1.30 DKK).
- Fix: both chips now template-read directly from the priskort `slots` array, selecting the entry whose hour matches `now().hour`. Single source of truth for the consumer price.

### Files touched

`ocpp_server.py`, `coordinator.py`, `const.py`, `config_flow.py`, `translations/en.json`, `translations/da.json`, `strings.json`, `manifest.json`, `CHANGELOG.md`.

### What this should fix in practice

- The optimizer's `Dagens plan` will now reflect tomorrow's actual sun, not phantom-zero forecasts → no more inexplicable grid-charge slots when sun is in the forecast.
- House-load predictions will drift downward over the next week as the learning model un-contaminates from EV hours.
- Energy-flow card's EV-lader line drops to 0 the moment a session ends.
- The "Køb" chip now matches the price chart and the optimizer's decisions.

---

## [0.27.8] — 2026-05-19

Dashboard polish — terminology.

### Changed

- Charger card title renamed from *"Foxess lader"* (FoxESS-specific) to *"EV-charger"* (vendor-neutral). The integration works with any OCPP 1.6-compatible charger via the embedded server, not just FoxESS L11PMC — the title now reflects that.

### Note

Applied to the live Lovelace dashboard via the WebSocket `lovelace/config/save` API. Reference `dashboard/*.yaml` files in the repo were not affected.

### Files touched

`manifest.json`, `CHANGELOG.md`.

---

## [0.27.7] — 2026-05-19

Dashboard polish — Foxess lader card icon mapping.

### Fixed

- The Foxess lader card's header icon used `mdi:help-circle` (`?`) as the fallback for OCPP states that weren't explicitly mapped — most visibly during the `Finishing` state (session ending). Replaced with a proper charger pictogram (`mdi:ev-station`) and added explicit entries for `Finishing` (`mdi:battery-charging-50`, cyan) and `Reserved` (`mdi:calendar-clock`, purple).

### Note

The live dashboard config lives in HA's storage (`/.storage/lovelace_battery-arbitrage`), not in this repo. This version bump captures the change in the changelog; the actual dashboard update is applied via the WebSocket `lovelace/config/save` API. New installs get the bundled `dashboard/*.yaml` files which serve as reference templates — those have not been auto-updated to match the live dashboard's accumulated v0.26.x → v0.27.x customizations.

### Files touched

`manifest.json`, `CHANGELOG.md`.

---

## [0.27.6] — 2026-05-19

Documentation accuracy fix.

### Changed

- README's FoxESS-only mode warning rewritten to reflect v0.27.x reality: it was wrongly claiming "no way to detect EV charging" and "could exceed your main breaker". Both claims are outdated:
  - The embedded OCPP server (v0.27.0+) detects EV charging directly via the charger
  - Grid-headroom protection (live grid-import monitoring, in Solar AI since v0.18.x) caps battery charge based on real grid import, so combined EV + battery draw cannot exceed the breaker regardless of EV-detection method
- Warning downgraded from ⚠️ to ℹ️ (informational note) — accurate trade-off explanation rather than scare text. EV-aware *scheduling* features (hourly probability learning, skip grid charge during EV hours) still require EVCC live-data mode and are inactive in FoxESS-only mode — that part remains true.

### Files touched

`README.md`, `manifest.json`, `CHANGELOG.md`.

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
