# Changelog

All notable changes to **Solar AI** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
