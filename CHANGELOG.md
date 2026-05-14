# Changelog

All notable changes to **Solar AI** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
