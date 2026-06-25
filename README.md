# Solar AI for FoxESS

[![HACS Custom Repository](https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant-community-store)](https://hacs.xyz)

A Home Assistant integration that schedules a FoxESS battery against Nord Pool day-ahead prices, drives an OCPP 1.6 EV charger from solar surplus, and learns from observed production and consumption.

## What it does

Solar AI is an automated energy manager for a FoxESS solar-and-battery system. It runs entirely inside Home Assistant and makes the decisions a battery owner would otherwise make by hand — when to store solar, when to buy cheap grid power, when to sell, and when to hold enough back for the house — and it remakes them every 15 minutes, around the clock, adjusting as prices, weather and your consumption change. You set it up once; it runs itself.

### The core loop — buy low, sell high, cover your own use first

Every 15 minutes it builds a plan over the next 48 hours from the day-ahead electricity prices, your solar forecast, your learned house consumption and the battery's state, and acts on it:

- **Stores your solar.** Surplus production charges the battery instead of being exported for a few øre, so you run the house on your own power in the expensive evening hours rather than buying it back.
- **Buys low.** When grid power is cheap — or negative, when the grid pays you to consume — it charges the battery from the grid, but only when that genuinely beats waiting for solar.
- **Sells high.** When prices rise enough to clear the round-trip cost (including battery wear), it exports stored energy to the grid and pockets the difference.
- **Keeps the house covered.** Before selling, it reserves enough charge to run your home through the dark hours until solar returns — so it never empties the battery and leaves you importing at peak prices overnight.

**The benefit:** your battery does more than store solar for the evening. It actively shifts energy from cheap hours into expensive ones and earns from the daily price swings, while always covering your own consumption first — turning a flat electricity bill into one that follows the cheapest hours.

### Charges your EV from spare solar

With an OCPP 1.6 charger, Solar AI charges the car from **surplus solar** — the power that would otherwise be sold cheaply. You pick the behaviour per session or per schedule: solar-only, solar-plus-battery, full-speed, or charging windows you set per weekday. It won't drain the house battery into the car unless you ask it to, and it won't compete with the charger for the cheap night hours.

With a **FoxESS charger in Modbus TCP mode**, it can additionally drop to **single-phase charging (down to ~1.4 kW)** to follow small surpluses on weak-sun days — below the 4.14 kW floor a three-phase OCPP charger is stuck at — and switch back up to three-phase (up to 11 kW) automatically when there's plenty of sun. Single-phase is only available on the Modbus backend.

**The benefit:** the car charges from your own roof for free where possible, or from the cheapest grid hours when there isn't enough sun — without you touching the charger.

### Handles prices and tariffs for you

No separate price integration (Tibber, Nord Pool, etc.) is needed. Pick your country, price area and grid company during setup, and Solar AI fetches the day-ahead spot price and the network tariffs automatically (Denmark today, via Energi Data Service / Strømligning) and keeps them current.

### Learns your home and adapts

Solar AI tunes itself to your specific system instead of running on fixed assumptions. It continuously learns your solar-forecast accuracy, your weekday and weekend consumption pattern, your true battery capacity, round-trip efficiency, and how fast the battery charges at different temperatures. Its decisions sharpen over the first few days and keep following the seasons — short summer nights, long winter ones — with no re-tuning from you.

### Safe and transparent

- **Respects your main fuse.** Total grid draw (house + battery + EV) is held under your breaker rating, so charging never trips the main.
- **Protects the battery.** It accounts for cycle wear and temperature and keeps a health floor, so chasing a few øre never costs you battery life.
- **Show, then trust.** Run it in monitoring mode first — it shows exactly what it *would* do on a built-in dashboard (prices, the plan, battery, EV, earnings and history) — and hand over control only when you're satisfied.

Everything runs locally in Home Assistant, on top of your existing FoxESS Modbus and solar-forecast integrations. No cloud account, and no external service makes the decisions.

---

## Installation

This is a step-by-step walkthrough written for someone who has used Home Assistant but has never installed a custom integration. Budget about 30 minutes. Read [Prerequisites](#prerequisites) first and make sure the required integrations (at minimum the FoxESS Modbus integration and a solar-forecast source) are already installed and producing data — Solar AI builds on top of them.

**Electricity prices are handled for you.** You do **not** need a separate price integration (Tibber, Nord Pool, etc.). During setup you just pick your **country**, **price area** (DK1/DK2 in Denmark) and your **electricity grid company (DSO)** from dropdowns, and Solar AI fetches the day-ahead spot price and the network tariffs automatically from Energi Data Service. Pointing it at an existing price sensor is optional (step 5).

The steps, in order:

1. Install HACS (skip if you already have it).
2. Add Solar AI to HACS and download it — or copy the files manually.
3. Restart Home Assistant.
4. Install the dashboard cards (HACS Frontend).
5. Add and configure the integration (the setup wizard).
6. Connect an EV charger (optional).
7. Import the dashboard.
8. Set your retailer price components (auto-filled if you use Strømligning).
9. Run in monitoring mode, then enable control.

### 1. Install HACS

HACS (the Home Assistant Community Store) is the easiest way to install and update custom integrations. If *Settings → Devices & Services* already shows a **HACS** entry, skip to step 2. Otherwise follow the official guide: <https://hacs.xyz/docs/use/download/download/>. After installing HACS you must restart Home Assistant and add the HACS integration before continuing.

### 2. Add Solar AI to HACS

1. Open **HACS** from the left sidebar.
2. Click the three-dot menu (⋮) in the top-right corner and choose **Custom repositories**.
3. In **Repository**, paste:
   ```
   https://github.com/Planckus/solar_ai
   ```
4. In **Type**, choose **Integration**, then click **Add**. Close the dialog.
5. Back in HACS, search for **Solar AI**, open it, and click **Download** (accept the version shown). 
6. Continue to step 3 to restart.

**Manual installation (no HACS).** If you prefer not to use HACS:

1. Download the repository as a ZIP from <https://github.com/Planckus/solar_ai> (green **Code** button → **Download ZIP**) and unzip it.
2. Copy the folder `custom_components/battery_arbitrage` from the unzipped files into your Home Assistant configuration folder so the final path is:
   ```
   /config/custom_components/battery_arbitrage/
   ```
   Use the **File editor** or **Studio Code Server** add-on, the **Samba share** add-on, or SSH to copy files. The `custom_components` folder sits next to your `configuration.yaml`; create it if it does not exist.
3. Continue to step 3.

### 3. Restart Home Assistant

*Settings → System → (power icon, top-right) → Restart Home Assistant.* Wait for it to come back online. This is what makes the newly-copied integration code available.

### 4. Install the dashboard cards

The bundled dashboard uses five custom Lovelace cards. Install each one before importing the dashboard, or the dashboard will show "Custom element doesn't exist" errors. In **HACS**, search for each card by name and click **Download**:

| Card to search for | Why it's needed |
|---|---|
| Mushroom | Status tiles, charge-mode selector, section titles |
| ApexCharts Card | Price/SoC chart and the 48-h solar forecast chart |
| Power Flow Card Plus | Animated energy-flow diagram on the home screen |
| card-mod | Layout and width styling |
| button-card | Cohesive card styling |

After downloading all five, **hard-refresh your browser** so it picks up the new cards: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (macOS).

### 5. Add and configure the integration

1. Go to *Settings → Devices & Services → **Add Integration*** (bottom-right).
2. Search for **Solar AI** and click it. (If it does not appear, the restart in step 3 was missed, or the browser needs a hard-refresh.)
3. A setup wizard opens. Work through the pages:

   | Page | What to enter |
   |---|---|
   | **Live data source** | Pick **EVCC**, **Hybrid**, or **FoxESS only** — see the [Live data mode](#live-data-mode) table. If unsure and you have no EV, choose **FoxESS only**. Using EVCC? See [Using Solar AI with EVCC](#using-solar-ai-with-evcc). |
   | **EVCC URL** *(EVCC/Hybrid only)* | The address of your EVCC instance, e.g. `http://your-ha-ip:7070`. |
   | **FoxESS live sensors** *(Hybrid / FoxESS-only)* | Grid-import, grid-export, PV-power and house-load sensors. Auto-detected defaults are pre-filled — change only if your entity IDs differ. |
   | **No-EV acknowledgement** *(FoxESS-only)* | Confirm you have no EV, or that your charger never pulls from the house battery. This avoids tripping your main breaker. |
   | **Inverter control entities** | The work-mode `select`, the force-charge and force-discharge `number` entities, and the inverter ID. Defaults match the FoxESS Modbus integration; see [FoxESS Modbus entity IDs](#foxess-modbus-entity-ids). |
   | **Battery sensors** | SoC, cell temperature, charge/discharge power, and lifetime charge/discharge totals. |
   | **Country, price area & grid company** | Choose your **country** (Denmark / UK), your **price area** (DK1 = western Denmark / Jutland + Fyn, DK2 = eastern Denmark / Sjælland), and your **electricity grid company (DSO)** from the dropdown. With just these, Solar AI fetches the day-ahead spot price **and** the network tariffs for your area automatically — **you do not need a separate electricity-price integration**. |
   | **Electricity price source** *(optional)* | **Leave the spot-price entity blank** to use the automatic Energi Data Service prices from the choices above. Only fill it in if you'd rather read an existing price sensor instead (Strømligning, Tibber, etc.). |
   | **Solar forecast source** | EVCC, Solcast, Forecast.Solar, or Auto — plus the entity overrides. For Solcast see [the two-entity wiring note](#solcast-ha-integration--two-entity-wiring-v0280). |
   | **Battery & trading parameters** | Battery capacity (kWh), round-trip efficiency, starting thresholds and currency. |
   | **Dashboard** | Leave **"Create the Solar AI dashboard for me"** ticked (recommended) and the integration builds the dashboard for you at the URL `/solar-ai` — you skip the manual import in step 7. (It still needs the cards from step 4 to render.) Untick it if you'd rather import the YAML by hand or link an existing dashboard. |

Everything here can be changed later from *Settings → Devices & Services → Solar AI → **Configure*** without re-running the wizard. When the wizard finishes, Solar AI creates its sensors and switches and starts in monitoring mode (control off).

### Using Solar AI with EVCC

**What each one does.** EVCC ([evcc.io](https://evcc.io)) is a separate, free application that controls your EV charger — when and how fast the car charges, including solar following. Solar AI does the home-battery arbitrage — it reads live grid, PV and EV data and decides when to charge the battery from the grid, when to export, and when to hold. They run side by side: EVCC owns the car, Solar AI owns the battery, and Solar AI reads EVCC's live data over the LAN so the two don't fight.

You do **not** set up EVCC from inside Solar AI. EVCC must already be installed and running, with your charger (and, for EVCC mode, your grid/PV meters) configured in EVCC itself. Solar AI only needs EVCC's address — it reads from EVCC's local API and never changes EVCC's configuration.

1. **Get EVCC running first (prerequisite).** Install EVCC (Home Assistant add-on, Docker, or standalone — see [evcc.io](https://evcc.io)) and confirm its web UI is reachable, e.g. `http://your-ha-ip:7070`. Note that address. No EVCC API key or special setting is required; Solar AI uses EVCC's standard read endpoints on the local network.
2. **Pick EVCC or Hybrid as the live data source** when the Solar AI wizard asks:

   | Choose | When | Live grid + PV from | EV data from |
   |---|---|---|---|
   | **EVCC** | EVCC already sees your grid and PV meters | EVCC | EVCC |
   | **Hybrid** | You want grid + PV straight from the FoxESS inverter, but still let EVCC run the car | FoxESS Modbus sensors | EVCC |

3. **Enter the EVCC URL** from step 1 (both modes), e.g. `http://your-ha-ip:7070`.
4. **(Hybrid only) Confirm the FoxESS live sensors** — grid import/export, PV power, house load. Auto-detected defaults are pre-filled; change only if your entity IDs differ. Hybrid also needs a solar-forecast source (Solcast or Forecast.Solar), since it doesn't take the PV forecast from EVCC.

The rest of the wizard (inverter control, battery, prices, forecast) is identical in all modes. EV-aware scheduling and EVCC battery-mode coordination are active in both EVCC and Hybrid mode — see [Live data mode](#live-data-mode).

### 6. Connect an EV charger (optional)

For an OCPP 1.6 charger driven by the integration's EV controller:

1. In *Solar AI → Configure → OCPP Settings*:
   - Enable the EV charge controller.
   - Use the embedded OCPP server (default).
   - Set the OCPP server port (default `9000`).
   - Set the Charge Point ID (CPID), e.g. `charger` or `foxess_l11pmc`.
2. On the charger:
   - OCPP backend URL: `ws://<ha-ip>:9000/`. Trailing slash, no CPID in the URL.
   - Charger ID field: the same string set as CPID in HA.
   - Some FoxESS firmware appends the Charger ID to the URL automatically. Verify the final URL the charger reports is `ws://<ha-ip>:9000/<cpid>/`.
   - Leave authentication blank (LAN-only, no auth).
   - Save and power-cycle the charger to force a fresh OCPP connection.
3. Verify within 30–60 s:
   - `sensor.solar_ai_lader_status` moves from `Unavailable` to `Available` (or `Preparing` if a vehicle is already plugged in).
   - `sensor.solar_ai_lader_info` populates with vendor, model, firmware, serial.
   - The EV / OCPP dashboard tab shows the OCPP-connected line.

The embedded server tolerates non-standard OCPP frames (empty-`[]` keepalives from the FoxESS L11PMC are silently ignored). Charger metadata is persisted to HA storage and `TriggerMessage` is sent on reconnect so sensors do not blank after an HA restart.

**Alternative: FoxESS Modbus TCP backend (single-phase capable).** A FoxESS L11PMC can instead be driven directly over Modbus TCP, which unlocks single-phase charging (~1.4–3.7 kW) for following small solar surpluses — something the OCPP path cannot do, as it is three-phase only with a 4.14 kW minimum.

1. In the FoxESS app, switch the charger to **Modbus TCP mode** (this drops its OCPP connection — the two are mutually exclusive).
2. In *Solar AI → Configure → OCPP Settings* (or on the dashboard's **Advanced setup** page): set **Charger backend** to **FoxESS Modbus TCP**, and enter the charger's **host/IP** (e.g. `192.168.x.x`), port (`502`), and unit id (`1`).
3. The controller then charges single-phase on small surpluses and switches up to three-phase automatically when the surplus is large enough; the min/max charge-rate dropdowns bound the current within whichever phase is active.

The embedded OCPP server stays available regardless of this setting — it is the path for OCPP 1.6 chargers of any brand (Easee, Zaptec, Wallbox, etc.). You can turn it off from the Advanced setup page if you don't use it.

> **Security — keep the OCPP port on your trusted LAN.** OCPP 1.6 is plaintext and unauthenticated, so the embedded server on port `9000` accepts connections from any device that can reach it. Keep it on your home/trusted network only — **do not port-forward `9000` to the internet or expose it across an untrusted VLAN**. The server bounds how many charge points it will track to limit abuse, but it cannot authenticate the charger; treat the port as you would any other internal-only service.

### 7. Import the dashboard

**If you left "Create the Solar AI dashboard for me" ticked in step 5, the dashboard already exists** — a **Solar AI** entry in the sidebar (URL `/solar-ai`), in your Home Assistant language. Just make sure the cards from step 4 are installed and skip to step 8. **Restart Home Assistant once** when convenient to finalise it (you'll get a notification reminding you): the dashboard works right away, but until that restart it isn't yet listed under *Settings → Dashboards*, so it can't be edited or removed there. After the restart it behaves like any normal dashboard. (To recreate or refresh it later, call the service **Developer Tools → Actions → `battery_arbitrage.create_dashboard`** — use `force: true` to overwrite an existing one with the latest bundled layout.)

To import it **manually** instead, two ready-made dashboard files are included — pick one by language:

| File | Language |
|---|---|
| `custom_components/battery_arbitrage/dashboards/dashboard_en.yaml` | English |
| `custom_components/battery_arbitrage/dashboards/dashboard_da.yaml` | Danish |

Both share the same single-screen layout (the English file is a full translation of the Danish one). Integration-generated text (status reasons, notifications) follows Home Assistant's configured language regardless of which file you pick.

To import it:

1. Open the file you want on GitHub, e.g. <https://github.com/Planckus/solar_ai/blob/main/custom_components/battery_arbitrage/dashboards/dashboard_en.yaml>, click the **Raw** button, and copy the entire contents (`Ctrl/Cmd+A`, then `Ctrl/Cmd+C`). If you installed manually, the same file is in your downloaded copy.
2. In Home Assistant, go to *Settings → **Dashboards*** → **Add dashboard** (bottom-right) → **New dashboard from scratch**. Give it a title (e.g. "Solar AI"), optionally an icon, and click **Create**.
3. Open the new (empty) dashboard. Click the pencil **Edit** icon (top-right). If asked, choose to take control / continue.
4. Click the three-dot menu (⋮, top-right) → **Raw configuration editor**.
5. Select all the existing text in the editor and delete it, then paste the YAML you copied in step 1. Click **Save**, then close the editor.

The dashboard now renders. If you see "Custom element doesn't exist" messages, a card from step 4 is missing — install it via HACS and hard-refresh.

### 8. Set your retailer price components

You do **not** enter electricity prices here — the **spot price and the network/feed-in tariffs are already fetched automatically** from the country / price area / grid company you chose in step 5. This step is only for the few values that depend on your specific **retailer contract**, and even those are filled in for you if you picked Strømligning (Denmark). On the dashboard **Settings / Indstillinger** page, check the **Price parameters** card:

- **Elafgift** — electricity duty (from your bill).
- **Spot markup** — your retailer's per-kWh add-on.
- **VAT** — 25% in Denmark.
- **Seller-side fee** — your retailer's per-kWh cut on exports, if any.
- **Minimum export price** — optional floor below which Solar AI will not export (default 0.00).

(In Strømligning mode these fields are greyed out — they're filled automatically.) The grid feed-in tariff (DSO + Energinet production tariff) is always fetched and deducted automatically.

### 9. Run in monitoring mode, then enable control

Solar AI starts with the **Arbitrage enabled** switch **off**. In this mode it calculates and shows what it *would* do but never changes the inverter. On the dashboard, watch:

- **Today's plan** — the charge/export hours it has scheduled.
- **Decision reason** — why it is choosing the current action.

Let it run for a day or two and confirm the planned actions look sensible for your setup and prices. When you are comfortable, turn **Arbitrage enabled** on (Settings page or `switch.solar_ai_...arbitrage`). From then on it actively sets the inverter work mode and charge/export power within your configured limits.

### Verify the install / troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| "Solar AI" not in the Add Integration list | Restart HA (step 3) was skipped, or the browser is cached — hard-refresh (`Ctrl/Cmd+Shift+R`). |
| Integration loads but values are `unknown` / `unavailable` | A source integration isn't ready. Confirm FoxESS Modbus and your solar-forecast entities have live values; re-check the entity IDs in *Solar AI → Configure*. |
| Dashboard shows "Custom element doesn't exist: …" | A Lovelace card from step 4 is not installed. The integration also raises a **Settings → Repairs** issue listing exactly which cards are missing, with links — install them in HACS and hard-refresh; the issue clears on its own. |
| No charge/export ever happens | Expected if **Arbitrage enabled** is off (step 9), or if prices are too flat to clear your minimum spread — check **Today's plan** and **Decision reason**. |
| EV charger stays `Unavailable` | Re-check the OCPP backend URL and Charge Point ID (step 6), then power-cycle the charger. |
| Prices look wrong | Re-check the price parameters (step 8) and your selected grid operator (DSO) in *Configure*. |

For installs on a Raspberry Pi / SD card, also enable the [disk-space alarm](#disk-space-alarm) so you are warned before storage fills up.

---

## Overview

If you have solar panels, a FoxESS hybrid inverter with a battery, and variable electricity prices, you have a daily optimisation problem with too many moving parts to solve by hand:

- Day-ahead spot prices change every hour and often vary 10× between the cheap night hours and the evening peak.
- Solar production depends on weather forecasts that are wrong 20–30% of the time.
- Network distribution tariffs (DK) and elafgift add a time-of-use surcharge on top of the spot price.
- House load is irregular — a kettle, an oven, a heat pump cycling.
- Cycling the battery costs something in degradation that has to be weighed against the price spread it captures.
- An EV that wants to charge now might be better off charging tomorrow if a sunny day is coming.

Solar AI handles all of this in one decision loop. Every hour it runs a backward-induction **dynamic programming optimiser** over a 48-hour horizon at 15-minute resolution. The model includes battery state of charge (1% steps), terminal value of energy left in the battery at the horizon, degradation cost, the full DK or UK price stack (spot + retailer markup + DSO tariff + Energinet + elafgift + VAT on the buy side; spot − indfødningstarif − seller fees on the sell side), and a per-hour learned solar accuracy factor with a short-term residual correction on top. The output is an ordered plan of CHARGE / EXPORT / IDLE actions per slot.

Between plan refreshes a **15-second execution tick** reads live FoxESS Modbus state, decides what the plan implies for *right now*, and writes the inverter's work mode, force-charge / force-discharge power, and export-limit register. An **embedded OCPP 1.6 server** (no separate integration required — the charger connects directly to `ws://<ha-ip>:9000/<cpid>/`) drives a connected EV charger from the same loop. Five EV modes are available: locked, solar-only, solar + battery-to-minimum, full power, and schedule-driven.

The integration **learns**: it tracks per-hour solar forecast accuracy over the last 4 days, intra-hour residual error over the last 2 hours, actual battery charge/discharge rates at different temperatures, and your real house load by hour. Those corrections feed back into the next optimiser run, so after a few weeks of operation the plan reflects your specific install rather than a generic model. A live dashboard shows every decision and why; a session log records each EV charging session split into solar vs grid kWh; a savings tracker accumulates the realised arbitrage spread against a baseline of doing nothing.

Country support today: **Denmark** (Strømligning retailers + DK1/DK2 price areas + DatahubPricelist tariff fetch) and **United Kingdom** (Octopus Energy + GSP region picker). Other Nord Pool / EU markets work with the manual price-stack inputs.

---

## Recent releases

### v0.59.13 — three-phase override + sub-5-minute phase switching

- The battery-full override — which charges the car from solar that would otherwise be curtailed when export is price-blocked and the house battery is full — now drives **three-phase**, reaching the full inverter output instead of the single-phase ~3.7 kW wall. It falls back to single-phase if the sun can't sustain the 4.14 kW three-phase floor.
- The FoxESS charger was found to accept a **1-minute** phase-switch interval (the documented 5-minute minimum is not hardware-enforced), so phase switching is far more responsive. Two new dashboard sliders — **Phase-switch interval** and **Override ramp step** — let you tune the timings.

### v0.59.11 — price matrix: two decimals and negative prices

- The buy/sell price matrix shows two decimals (`0.00`) and no longer clamps the sell price at zero, so negative-price hours are visible.

### v0.59.10 — curtailment recovery + full-power battery lock on the Modbus backend

- Two protections that previously worked only on the OCPP path now apply to the FoxESS Modbus backend: the car **recovers from the export-blocked + battery-full curtailment deadlock** (it draws the otherwise-wasted solar instead of stalling), and the **house battery is locked while charging in full-power mode** so the car is fed from solar and grid rather than draining the battery.

### v0.59.0–v0.59.9 — solar EV charging refinements + new controls

- An export-aware surplus signal (no more dumping solar to the grid while the car waits), prices that **survive restarts and failed fetches**, a date-correct "today's plan" card, smoother phase switching that no longer stalls on broken-cloud days, and two new dashboard controls: the **three-phase switch threshold** and the **charging current step** (1 / 0.5 / 0.1 A).

### v0.58.0 — EV control interval on the dashboard

- How often the EV controller re-evaluates and re-asserts the charger is now adjustable from the dashboard.

### v0.57.0 — FoxESS Modbus charger backend (single- and three-phase solar following)

- A FoxESS L11PMC can now be driven directly over **Modbus TCP** as an alternative to OCPP, which unlocks **single-phase charging** (~1.4–3.7 kW) for following small solar surpluses — below the 4.14 kW floor the three-phase OCPP path is stuck at. It switches up to three-phase (up to 11 kW) automatically when the surplus is large, by hysteresis (up ≥ 4.5 kW, down < 4.0 kW) gated by the charger's 5-minute suspend interval. **Single-phase is only available on the Modbus backend; OCPP is three-phase only.**
- The backend selector, charger IP, and an embedded-OCPP-server on/off switch are on the dashboard's Advanced setup page (and in Configure). The embedded OCPP server stays the generic path for OCPP chargers of any brand regardless of the selected backend.
- `sensor.solar_ai_lader_effekt` reports live Modbus power, per-phase currents, and the live vs target phase count. The solar-only battery-drain guard (0.54.0) applies to the Modbus backend too.

### v0.56.0 — more setup options in the dashboard

- Live data source, solar forecast source, buy-price mode, price area, and electricity product/provider are now dashboard selects (previously config-only), applied without a reload. A new **Advanced setup** dashboard page groups these plus diagnostics and a deep link to Configure.

### v0.55.3 — home-page navigation fix + polish

- Fixes a v0.55.2 regression where the home-page solar-forecast section pushed the page-navigation links off the bottom; the links are back at the bottom. The nav links are also larger and colour-coded per page for visibility. Dashboard-only.

### v0.55.2 — solar forecast on the home page

- The solar-forecast section (today/tomorrow expected production, the live forecast-correction card, and the 48-hour forecast chart) now also shows on the home dashboard view, not just the EV page. Dashboard-only.

### v0.55.1 — security hardening

- Defence-in-depth from a security review of the embedded OCPP server (an unauthenticated plaintext LAN listener) and the HTTP fetches: the OCPP server now caps how many distinct charge points it tracks (reconnects from a known charger are always allowed; a flood of new IDs is refused) to bound memory; the price/EVCC/forecast fetches refuse response bodies over 8 MB; and the README documents that port 9000 must stay on a trusted LAN. Nothing is internet-exposed by default. A charge-point-ID allowlist and optional OCPP Basic-Auth remain tracked as follow-ups.

### v0.55.0 — friendlier onboarding

- The setup wizard now offers a **quick setup**: when your FoxESS Modbus entities are all auto-detected, it collapses the entity-picker screens into one confirm-and-go form that only asks for what can't be detected (battery capacity, grid company, currency), with a "Customise advanced settings" toggle for the full per-entity wizard. If something can't be detected, the full wizard is used automatically. Setup also **pre-checks the FoxESS Modbus prerequisite** and aborts with clear guidance if it's missing, **defaults the solar forecast to Forecast.Solar** (no account needed) when nothing else is detected, and shows a **one-time post-setup health summary** confirming SoC / solar / price are reading. Also fixes a latent `KeyError` (`evcc_url`) that would have affected fresh FoxESS-only installs.

### v0.54.0 — solar-only EV charging no longer drains the house battery

- In PV (solar-only) mode the EV could keep charging at the charger's 4.14 kW hardware minimum (6 A, 3-phase — it can't go lower) while solar surplus was well below that, with the house battery silently covering the gap (observed: ~1.2 kW surplus, EV at 4.1 kW, battery discharging ~3.2 kW). Cause: the battery-full override that harvests curtailed PV into the EV judged spare PV by grid import only, and grid import stays ~0 when the battery covers the draw — so it never backed off. The override now also reads house-battery discharge: if the battery is discharging to cover the EV, it yields and PV mode's normal "surplus below minimum → stop" takes over. Solar-only mode no longer pulls from the house battery.

### v0.53.0 — discharge floor no longer dissolved by token grid-charges

- A week of live data showed the discharge floor still letting the battery drain to ~11% overnight: it sized the reserve as "house load until the next refill" but treated *any* planned grid-charge as a full refill, so a token charge (one case ran 10 minutes) collapsed the whole reserve and let the evening export sell the SoC the house needed for the night. Now only solar covering the house ends the dark bridge; a planned charge is credited for the energy it *actually* returns (sustained charge rate × planned hours) and netted off the reserve. A short charge offsets almost nothing (the floor stays high enough to protect the night); a genuine multi-hour cheap charge offsets a lot (more can be exported). The charge credit uses a new continuously-learned *sustained* charge rate (the mean of observed charge power per temperature bucket, rather than the p90 peak, which over-credits). The reserve is driven entirely by learning inputs — solar forecast, house-load profile, capacity, efficiency, sustained charge rate and the self-correcting margin — with no fixed rate assumptions, so it adapts across days and seasons. The learned margin is reset once on upgrade (it had ramped up while fighting the old broken bridge).

### v0.52.0 — dynamic discharge floor no longer drains overnight

- The dynamic discharge floor was counting cheap overnight grid-price windows as battery "refills", so its reserve only had to bridge the house to the first cheap hour instead of to the next real energy arrival. On nights without a planned grid-charge, evening export emptied the battery to that too-low floor and Self-Use then drained it close to empty before dawn. Now a slot counts as a refill only when solar actually covers the house load, or the optimiser has planned a grid-charge for that slot — a cheap price alone no longer shortens the bridge. A dawn margin keeps the thin shoulder around sunrise from ending the bridge early, the self-learned safety margin is now raised in proportion to how far below comfort the battery actually fell (with a higher ceiling), and the previously-learned margin is reset once on upgrade. The floor still governs export only.

### v0.51.2 — dashboard width fix on all pages

- Every dashboard page now wraps its content in a `custom:mod-card` width cap (the EV page already did). This replaces the card-mod `:host`-on-a-bare-stack trick that intermittently failed after a restart and left pages stretched full-width.

### v0.51.1 — auto-dashboard finalise-on-restart

- An auto-created dashboard works immediately but isn't listed under *Settings → Dashboards* (so it can't be edited/removed there) until the next Home Assistant restart — a limitation of HA not exposing its live dashboards collection to integrations. The integration now raises a notification telling you to restart once to finalise it; after that it behaves like any normal dashboard.

### v0.51.0 — automatic dashboard setup + sell-price matrix

- The dashboard now ships inside the integration and the setup wizard can **create it for you** (opt-in, on by default) at `/solar-ai` in your HA language — no manual raw-config paste. A `battery_arbitrage.create_dashboard` service does the same for existing installs (`force: true` to refresh). The custom Lovelace cards still need a one-time HACS Frontend install — and the integration now raises a **Repairs** issue naming exactly which cards are missing (clears once installed).
- A **sell-price matrix** on the Prices page, directly below the buy-price matrix: the hourly export price for today and tomorrow, colour-coded so green = a high (good) sell price and red = low.

### v0.50.1 — EV page width fix

- After v0.50.0 added the weekday toggles, the larger EV / OCPP page rendered full-width because card-mod's `:host` max-width style stopped applying to the bare stack. The page content is now wrapped in a `custom:mod-card` so the 1000 px width cap holds reliably, matching the other pages. Dashboard-only.

### v0.50.0 — per-schedule weekday selection in the GUI

- Each EV charge schedule (1–4) now has seven weekday on/off toggles (Mon–Sun), so you can pick exactly which days a charge plan runs — e.g. charge 02:00–05:00 on Monday, Tuesday and Friday only — entirely from the dashboard. New schedules still default to Mon–Fri; the resolver honours per-day activation including windows that wrap past midnight.

### v0.49.0 — clearer no-trade wording + disk-space alarm

- **No-trade-day wording.** When the optimiser finds nothing worth doing (prices too flat to clear the spread, battery already covered by solar), the daily plan now says so explicitly instead of a bare "none · none" that read like an error.
- **Disk-space alarm.** New `disk_free` sensor (free GB + % on the partition HA runs on) and `disk_low` problem binary_sensor, with a GUI threshold (default 10% free) and an optional mobile push. Aimed at Pi/SD-card installs. See [Disk-space alarm](#disk-space-alarm).

### v0.47.5–v0.48.1 — execution fixes, net balance, price matrix

- **Export/charge execution fixes (v0.47.5–v0.47.7).** The optimiser's planned charge/export wasn't reliably executing: the in-progress 15-minute slot was dropped from the plan (so the current interval matched nothing), export used FoxESS "Feed-in First" (which only routes solar, never discharges the battery) instead of "Force Discharge", the force-charge/-discharge power setpoints wrote watts into kW fields (so they ran at full power, ignoring the grid-headroom cap), and a cold plan right after a restart was cached for ~15 min. All fixed — the battery now actually performs arbitrage export.
- **Net grid balance (v0.48.0).** New `import_cost` sensor (all grid import — house + battery charging) and `net_grid_balance` sensor (export income − import cost), with a net-balance card beside export income on the Prices page. `export_income` remains gross export.
- **Buy-price matrix (v0.48.1).** New `price_forecast` sensor (hourly, timestamped buy/sell prices over today + tomorrow) and a colour-coded price-matrix card on the Prices page, so upcoming buy prices are visible at a glance (green = cheap, red = expensive).

### v0.47.0 — receding-horizon planning + dynamic discharge floor

Two changes to how the optimiser reserves and times battery use:

- **Receding-horizon planning.** The DP plan now re-solves every 15 minutes (and on restart / daily tariff refresh) instead of once per day, so it picks up tomorrow's day-ahead prices when they publish (~13:00) and tracks the live SoC and solar through the day. Previously a plan made in the morning was used unchanged for ~24 hours.
- **Dynamic self-learning discharge floor** (new `Dynamic discharge floor` switch, default off). When on, the export floor is the SoC needed to run the house until the next refill — sunrise solar or a cheap grid window — times a self-learned safety margin, instead of a fixed value. A short bridge lets it export more; a long night with no cheap window holds enough to avoid expensive overnight imports. The margin self-corrects daily from whether the reserve actually lasted. The `effective_floor` sensor shows the floor in effect.

### v0.46.0 — weekday/weekend house-load split

The learned house-load profile is now split into weekday and weekend curves, each learned separately and selected per slot by the slot's date (so a 48-hour horizon spanning the weekend uses the right shape). Both seed from the previous combined curve on upgrade. Tariff handling (seasonal + time-of-day, from EDS DatahubPricelist) was reviewed and already correct, so no tariff change was needed.

### v0.45.0 — session-aware EV demand

The optimiser used to model EV load as an hour-of-day probability. When the car is plugged in and in a forced-draw situation (actively charging, fast/pv+battery mode, or EVCC now/minpv), it now treats the next 2 hours of EV demand as near-certain — the live charge power — and won't grid-charge the house battery against it. Beyond that window the learned hourly model resumes. Pure-PV charging is unaffected (already handled by the solar→EV dynamics). The reserved demand shows as the `dp_session_demand_kw` attribute on the `ev_target_kw` sensor.

### v0.44.0 — probabilistic solar in the optimiser

The DP optimiser can now plan against a configurable percentile of each hour's observed solar forecast/actual ratio instead of the fixed median. A new `Solar confidence` control (10–90 %, default 50) sets the percentile; at 50 it equals the median, so the default is identical to 0.43.0 with no behaviour change. Lowering it makes the planner assume more conservative solar — grid-charging more readily in cheap windows and avoiding over-exporting battery it will need on a cloudy day. Builds on the 0.43.0 percentile groundwork; pair it with the `prediction_accuracy` scorecard to measure the effect before and after.

### v0.43.0 — prediction scorecard + solar-forecast percentiles

Observability groundwork for more precise decisions; no behaviour change. The optimiser's predicted battery SoC is now logged against the realised SoC every 15 minutes, surfaced as a `prediction_accuracy` sensor (rolling 7-day SoC mean-absolute-error, plus 30-day MAE, solar-forecast MAPE, and the predicted-action mix). The per-hour solar `(forecast, actual)` buckets are also exposed as P10/P50/P90 of the actual/forecast ratio. Together these give a measured baseline so a later release can switch export/charge sizing to a conservative solar percentile and prove the improvement on real data rather than assuming it. (v0.46.1 hardened the scorecard against restart artifacts — it skips a 15-minute warm-up after each restart so the cold optimiser plan doesn't inflate the error metric.)

### v0.42.0 — export-income tracking

A new `export_income` sensor (`sensor.solar_ai_eksport_indtaegt`) accumulates the running revenue from exported energy (`feed-in kWh × export price`, integrated each coordinator tick) and exposes period totals as attributes: `today`, `last_7_days`, `last_30_days`, `this_month`, `this_year`, plus a `daily` list. The Prices page gains a period-totals chip row and a daily-income bar chart. Because the sensor is `monetary` + `total_increasing`, it can be added to Home Assistant's **Energy dashboard** (Settings → Dashboards → Energy → *Individual devices* / *Grid* gas-and-cost), giving an arbitrary from/to date picker and daily/weekly/monthly breakdowns for any period. See [Export income](#export-income) below.

### v0.41.0 — bilingual user-facing text

The EV-controller status reasons and push notifications now follow Home Assistant's configured language — Danish on a Danish HA, English everywhere else. Combined with the translated English dashboard (v0.40.7), an English install is now fully English; a Danish install is unchanged.

### v0.40.1–v0.40.7 — dashboard fixes + OCPP reliability

A run of fixes and a hardening pass on top of the v0.40.0 redesign:

- **Energy-flow card** — corrected the battery flow direction, slowed the flow-dot animation, kept the EV branch always visible, switched the buy/sell tiles to live current-price sensors, added a battery-temperature chip, and a stop-window countdown chip shown while solar charging winds down. (v0.40.1, v0.40.6, v0.40.7)
- **Solar-mode cool-down (v0.40.7)** — when PV surplus drops below the minimum, the EV now eases to the *minimum* rate during the stop-window hold instead of the last (higher) rate, minimising battery/grid draw while it waits to see if the sun recovers.
- **English dashboard (v0.40.7)** — `dashboard_en.yaml` rebuilt to mirror the Danish layout, fully translated (entity IDs unchanged).
- **EV charge-rate enforcement (v0.40.2)** — after an OCPP reconnect the charger could drop its charging profile and free-run at full current (pulling from the house battery). The controller now re-asserts the commanded limit at least every 60 s, and only caches a rate once the charger replies `Accepted`.
- **Session recovery (v0.40.3)** — a stale `session_active` flag left by a reconnect could wedge the charger in `Preparing` with no charging starting. It's now cleared on `Available`/`Preparing` and on boot.
- **OCPP hardening (v0.40.4–v0.40.6)** — an `ocpp_diagnostics` sensor exposing the embedded server's internals (session, transaction, last command results + ages, MeterValues age, a rolling event log); verified/retried `SetChargingProfile`; a desync watchdog that auto-heals a charger that won't deliver (TriggerMessage re-sync, then a connector-availability cycle); a `GetCompositeSchedule` read-back; and unit tests for the charge-point behaviours.

### v0.40.0 — dashboard redesign + capacity/ramp learning

The Danish dashboard was rebuilt into a single cohesive-style screen: one centered column with the master controls, current prices, a `power-flow-card-plus` energy-flow diagram, a Charge-mode selector, and the 24 h chart, with the five detail pages moved to subviews reached from a bottom navigation row. New dashboard prerequisites: `power-flow-card-plus`, `card-mod`, `button-card` (see Dashboard dependencies below).

This release also bundles two integration features first added in v0.39.21: **battery capacity is auto-detected from the BMS** (`Σ bms_kwh_remaining / SoC`, sampled in the 15–85 % mid-range) so it no longer depends on a grid-charge cycle; and an **active ramp during the battery-full override** steps the EV up 1 A at a time while grid import stays low, so the charger finds the real PV ceiling instead of staying at minimum. The v0.39.20 priority-gate fix (only block the EV from *starting*, not while already charging) is included as well.

### v0.39.x — pricing accuracy, FoxESS-mode parity, and EV-controller hardening

Released over 2026-05-26 → 2026-05-27 as a chain of small fixes. The latest release in the chain is the version HACS will install. Earlier v0.39.x tags exist in the release history for traceability but are superseded.

**Pricing accuracy (v0.39.6, v0.39.8, v0.39.13).** Three independent fixes restored the buy-price computation to the value retail customers actually pay:

- `stromligning.fetch_prices` cache key collapsed all four 15-min slots per hour into one key (last-write-wins meant only the `:45` quarter survived). Now keyed at 15-min resolution with an hour-aligned fallback for products/dates where Strømligning returns hourly entries. (v0.39.6)
- DSO tariff fetch summed all of a DSO's parallel tariff bands (Dinel publishes seven — tier-A high/low, tier-B spreed/high/low, tier-C residential <100/>100). The existing `require_all_prices` + `require_varying_prices` filters kept six of them after profile-dedupe. Added a `note_substring` filter; the coordinator passes `"Nettarif C"` to restrict to the residential C-time band. Energinet `ENERGINET_TARIFF_CODES` widened from `{"40000"}` to `{"40000", "41000"}` (Systemtarif was missing entirely). Combined network tariff at hour 10 today went from 0.336 (wrong) to 0.2073 (matches the Strømligning breakdown sensor to 4 decimal places). (v0.39.8)
- Daily tariff-schedule refresh used to commit a partial fetch (one of DSO or Energinet returning empty) into the cache and lock that 24-hour-stale state for a full day. New guard checks that both fetches returned non-empty data before overwriting; otherwise keeps the previous good cache and advances the refresh timestamp by less than the full TTL so the next retry fires after ~10 minutes. (v0.39.13)

**EV controller — four related fixes (v0.39.10, v0.39.11, v0.39.12, v0.39.15).**

- `ev_charging_now` and `ev_charging_solar` were derived purely from the EVCC `loadpoints` array. In FoxESS-only mode (no EVCC poll) `loadpoints = []`, so both flags reported `False` regardless of what the EV was actually doing. `binary_sensor.solar_ai_ev_oplader_solenergi` was permanently off for FoxESS-only users, and the optimizer's "hold the battery for the EV" guard against `should_export` was never engaged. Same backfill pattern as the v0.28.0 fix for `ev_charge_power_w`: when loadpoints is empty, derive from the embedded OCPP server's draw + `_ev_effective_mode`. (v0.39.10)
- Anti-flap state-name flapped CHARGING ↔ COOLING every 20-30 s when solar surplus oscillated within ~100 W of `ev_min_charge_kw` under variable cloud cover. Verified live from `sensor.solar_ai_ev_status` history: 50+ state transitions in 30 minutes while the charger drew at a steady 6 A throughout — the state name was flipping while the EV kept charging. Root cause: the v0.38.3 stop-recovery guard debounced COOLING → CHARGING but the CHARGING → COOLING entry was immediate. New `EV_COOL_ENTRY_SECONDS = 10` mirror requires sustained below-min before flipping state. (v0.39.11)
- Curtailment probe (v0.36.2) and start_window (60 s default) were both 60 seconds and raced at T=60 s; the probe almost always expired before the start_window completed and the EV never started. Probe ends → synthesised solar disappears → `target_amps = 0` → `_apply_ev_time_window` returns 0 → 15-minute cool-down. From outside the probe feature looked broken. New `probing` kwarg on `_apply_ev_time_window` bypasses start_window when the probe is in flight; the probe is itself a confidence signal (fires only when the inverter explicitly reports PV throttling AND a Solar AI price-floor block is open). (v0.39.12)
- Probe trigger gate broadened from `pv_curtailed AND floor_active` to `pv_curtailed AND (floor_active OR battery_near_full)`. v0.38.2's `floor_active` gate excluded the most common non-price-floor curtailment case — battery full on a bright day, MPPT throttling because there's nowhere to put the PV. The EV is exactly the right sink for that. Same change broadens the solar-accuracy learner's `curtailed=` signal from `floor_active` alone to `floor_active OR mppt_curtailed` so battery-full curtailed days no longer poison the per-hour Solcast factor. Grid-side faults (where the AC bus would reject the EV too) remain excluded because `battery_near_full` happens to also exclude them. (v0.39.15)

**OptionsFlow cleanup (v0.39.7).** v0.38.0 moved EV schedules into the dashboard but the OptionsFlow step that asked users to link HA `schedule.*` helpers per EV mode was never removed. Step retired; `ocpp_settings` now routes directly to `entities`. Legacy `CONF_EV_SCHEDULE_LINKS` data is preserved in entry.data — the coordinator's one-time migration path at lines 604–662 still runs on pre-v0.38.0 setups.

**Tooling (v0.39.9).** `deploy.py`'s `DASHBOARD_YAML` constant had pointed at a legacy backward-compat mirror (`battery_arbitrage_dashboard.yaml`) that had silently drifted from the canonical `dashboard_da.yaml`. Repointed to the documented canonical file; the legacy mirror is deleted.

**Smaller patches.** v0.39.0 added an opt-in auto-Full mode that promotes the EV to `Full` while spot price is ≤ 0 and reverts when the price-floor block closes. v0.39.1 normalised Strømligning cache keys to handle ISO-format variations (`+00:00` vs `.000Z`). v0.39.2 added `binary_sensor.solar_ai_eksport_stop_aktiv` so dashboards can render a conditional chip while the price-floor block is open. v0.39.3 fixed an `UnboundLocalError` introduced by v0.39.0. v0.39.5 corrected the nesting level the buy-price-breakdown sensor used to read Strømligning's `entry.price.total` and `entry.details`. See [CHANGELOG.md](CHANGELOG.md) for per-version detail.

### v0.38.x — EV scheduling on the dashboard + curtailment-probe refinements

- **Native EV scheduling, owned end-to-end by the integration.** v0.38.0 drops the dependency on HA's `schedule.*` helper integration. Schedule data lives in `coordinator._stored["ev_schedules"]` and is edited entirely from the dashboard — no Settings → Helpers detour, no Configure-flow step. Four slots per install with mode (PV / PV+Bat / Full), enabled toggle, start/end times (native HA time picker), and per-weekday chips. New services: `add_schedule_slot`, `remove_schedule_slot`, `toggle_schedule_day`, `set_schedule_days`. Migration imports any pre-existing `ev_schedule_links` automatically; the old `schedule.*` helpers stay around but are no longer read.
- **Curtailment-probe trigger fixes.** v0.38.1 dropped the `battery_near_full` precondition that was falsely blocking the probe when the battery had drifted a few percent (car-swap mid-curtailment, post-cloud restart). v0.38.2 added a `_current_floor_block is not None` gate so the probe is now coupled 1:1 to the user's price-floor feature — fires only during price-floor blocks, ignores rare non-price-floor curtailment cases that the EV couldn't help with anyway. Added a 15-minute cool-down after a failed probe (MPPT didn't lift) so grid-import waste is capped.
- **Stop-window stuck-in-COOLING fix.** v0.38.3 made the stop timer require ≥ 10 s of sustained surplus above min before clearing, so 50–200 W noise blips on borderline surplus no longer keep the controller perpetually "about to stop" while the charger holds at minimum from solar. Telemetry override during cool-down hold reports the actual commanded power (`target_kw`) and an honest reason ("oplader fortsætter ved minimum… i nedkøling") instead of `target_kw = 0 / "stoppet"`.

### v0.37.x — OCPP transaction recovery + EV schedule modes on the dashboard

- **OCPP transaction tracking survives HA restarts.** Multi-restart sessions used to lose the active `transactionId`, leaving Solar AI unable to send `RemoteStopTransaction` — the charger kept drawing while the integration thought IDLE. v0.37.0 adds three coordinated recovery paths: live capture of `transactionId` from every `MeterValues` frame (with drift detection), persistence of session state alongside vendor/model metadata, and `TriggerMessage(MeterValues)` on reconnect so a fresh frame arrives within ~2 s.
- **`battery_arbitrage.force_stop_charger` service.** Brute-force escape hatch for runaway sessions — walks candidate transaction ids (user-supplied → tracked → 1 → 0) and sends `RemoteStopTransaction` for each. Most chargers stop the only active transaction regardless of the id supplied.
- **Per-slot EV schedule mode selects.** Each configured `ev_schedule_link` gets its own `select.solar_ai_skema_N_tilstand` entity on the EV/OCPP tab. Options: PV / PV+Bat / Full. Edits persist to coordinator storage; `_resolve_effective_ev_mode` prefers storage over the link dict's seeded mode. Mode changes no longer require reopening Configure.
- **Schedule provisioning services.** `battery_arbitrage.add_schedule_slot` creates a `schedule.solar_ai_skema_N` helper + adds a link; `remove_schedule_slot(slot)` deletes the helper + unlinks. The dashboard layout grouping (master selector + slot cards + edit-schedule popup) ships in a follow-up Lovelace push.

### v0.36.x — inverter-driven EV curtailment + 15-second card refresh + EV scheduling Phase A

- **Curtailment trigger reads the inverter, not the forecast.** v0.36.2 replaces the v0.30.1 forecast-substitution heuristic with a direct read of FoxESS reg `49251` ("PV Power Limited Flag"). When the flag is set and the house battery is at/near its max SoC, a 60-second probe synthesises just enough solar in the surplus calculation to guarantee `ev_min_charge_kw` of EV demand. MPPT lifts to deliver real PV; after the probe ends the live solar reading takes over. No forecast in the EV trigger path. Catches grid-operator and battery-full curtailment in addition to the price-floor case.
- **15-second default fast-poll.** v0.36.0 dropped `DEFAULT_FAST_POLL_SECONDS` from 30 to 15. Lovelace cards driven by integration sensors (price stack, savings, EV status, surplus, plan, charger live values) now refresh in 15 s. Migration bumps existing entries from 30 → 15 only when they were on the old default.
- **EV scheduling Phase A.** Master mode select got a fifth option (`Scheduled`). When active, the coordinator resolves each tick by walking a configured list of `schedule.*` helpers → EV mode links, with a configurable fallback. Schedule helpers are created via Settings → Helpers → Schedule and linked from the options flow.
- **`_open_floor_block` name-clash fix.** Pre-existing v0.30.1 bug where an instance attribute shadowed a method of the same name, surfacing as `setup_retry` when the export floor was active.

### v0.30.x — v0.35.x — buy-side pricing, country picker, retail integrations

- **Strømligning (DK) retailer pricing.** New `stromligning.py` transport module with bundled offline supplier snapshots, sell-side company picker, USE_MANUAL_OVERRIDES toggle for diagnostics.
- **Country picker (DK / UK) + Octopus Energy (UK).** New `octopus.py` module with bundled product catalogue + region (GSP letter A–N). Sell-side support deferred (UK users keep the manual seller-fee slider).
- **Configurable DK price area + tariff fetch.** DK1 / DK2 dropdown, separate toggle for the Energi Data Service DatahubPricelist fetch. Previously hard-coded in `const.py`.
- **EV battery-lock follows real power draw.** v0.30.1 — battery-lock now triggers on `ev_current_kw > 0.3 kW` rather than mode flag alone, so an overnight session driven by the car's own timer correctly engages the lock when the car actually wakes up.
- **Solcast HA integration units fix.** v0.29.1 — modern Solcast v4.x reports `pv_estimate` as kW (power), not kWh per period. Auto-detected by comparing `max(detailedForecast)` against the peak_forecast sensor.

### v0.28.x — production hardening after first weeks of live operation

- Solcast HA integration supports both `today` and `tomorrow` entities; optimiser plans against a full 48-hour PV horizon (previously 24 h).
- Intra-hour short-term solar correction (v0.28.6): per-tick residual tracking compares actual PV to the matching Solcast 15-min slot, computes a rolling ratio over the last 4 closed slots, and applies the correction with linear decay over a 2-hour horizon on top of the existing 4-day per-hour accuracy factor.
- 48-hour solar forecast chart on the EV / OCPP tab. Two series: raw Solcast (columns) and the per-hour adjusted forecast the optimiser uses (line). Includes today-remaining-kWh and tomorrow-expected-kWh totals.
- EV charge session log with per-tick grid vs solar energy split. Each completed session records start, stop, duration, total kWh, energy from solar surplus, and energy from grid. Rendered as a history table on the Logs tab.
- Bug fixes: lader_effekt now zeros on session end; cool-down restart works from any plugged-in OCPP state; ARMING timer clears when surplus drops below minimum; EV charge power is subtracted before house-load learning; live anti-flap countdown computes against a fixed-target timestamp.

See [CHANGELOG.md](CHANGELOG.md) for the per-version detail.

### v0.27.x — embedded OCPP server and EV charge controller

- Built-in OCPP 1.6 server. The charger connects directly to `ws://<ha-ip>:9000/<cpid>/`. No separate `lbbrhzn/ocpp` HACS integration required.
- Four EV charge modes: Locked, Solar-only, Solar+Battery-to-minimum, Full power (with house-battery discharge lock).
- Time-based anti-flap windows (configurable start / stop) and amp-step rate limiting to stay within charger and breaker tolerances.
- Persistent charger metadata across HA restarts; `TriggerMessage` on reconnect.

### Configuration reference

[docs/CONFIGURATION.md](docs/CONFIGURATION.md) lists every slider, switch, and setup field with the value range and effect.

---

## What it does

Solar AI operates as a Home Assistant integration. It reads live state from FoxESS (and optionally EVCC), fetches day-ahead spot prices, and runs an hourly dynamic programming optimiser that decides when to charge from the grid, when to export, when to idle, and at what current to drive a connected EV charger.

The decision loop has two layers:

1. **Hourly planning.** Fetch spot prices from Energi Data Service (Nord Pool, area `DK2` by default). Combine with auto-fetched DSO and Energinet tariffs, elafgift, VAT, and seller-side fees to compute per-slot buy and sell prices. Run a 24- to 48-hour DP optimiser over 15-minute slots with battery SoC as state (101 integer steps) and CHARGE / EXPORT / IDLE as actions. The result is an ordered plan: `{slot_start, action, expected SoC, buy, sell}`.

2. **Fast tick.** Every 10–300 seconds (configurable, default 30 s) read live state and execute the plan: set FoxESS work mode, write force-charge / force-discharge power, set the export limit register, and — if the OCPP controller is enabled — send `SetChargingProfile` to the EV charger.

All thresholds are live-configurable via dashboard number entities. No YAML editing required after initial setup.

---

## Features

### Arbitrage engine

| Item | Detail |
|---|---|
| Optimiser | Backward-induction dynamic programming. 15-min slots over 24–48 h. SoC state at 1% resolution. CHARGE / EXPORT / IDLE actions. |
| Multi-cycle planning | Handles `charge at 02h, export at 11h, charge again at 14h, export again at 19h` correctly. Simple threshold logic cannot. |
| Buy price | `(spot + retailer markup + DSO tariff + Energinet tariff + elafgift) × VAT` |
| Sell price | `spot − seller-side fee − indfødningstarif (DSO + Energinet, auto-fetched)` |
| Minimum spread | Export only when `sell_price − cheapest_recharge_cost / efficiency ≥ min_spread`. Default 1.00 DKK/kWh, configurable 0.10–3.00. |
| Minimum export price floor | Hard floor below which the export limit register is set to 25 W, blocking both battery and solar export. Default 0.00 (blocks only negative or zero prices). |
| Export power cap | Optional cap on battery discharge during export (0–10 kW). Default 0 (no cap). |
| Negative-price grid charge | When the buy price drops to ≤ 0 DKK/kWh, grid charging starts regardless of spread or EV schedule. |

### Price stack

All components are live-configurable number entities:

| Component | Default | Range |
|---|---|---|
| Buy-side VAT | 25% | 0–50% |
| Seller-side fee | 0.00 DKK/kWh | 0.00–0.50 |
| Spot price markup (retailer add-on) | 0.00 DKK/kWh | 0.00–0.50 |
| Elafgift | 0.01 DKK/kWh | 0.00–3.00 |
| Min. export price floor | 0.00 DKK/kWh | 0.00–2.00 |

### Network tariff integration

- Hourly DSO time-of-use tariffs are fetched from the Energi Data Service DatahubPricelist API by GLN number, refreshed daily.
- Energinet system and transmission charges (code `40000`) are fetched daily.
- The DSO feed-in production tariff (e.g. Nettarif indfødning C, code `TC_IND_03`) and Energinet production tariff (code `40010`) are auto-fetched and deducted from the export price.
- DSO is set in *Settings → Solar AI → Configure → Grid operator*. Dinel (Jutland/Fyn) is wired now; additional DSOs are added in `const.py`.

### Solar forecast

| Item | Detail |
|---|---|
| Sources | EVCC (Solcast under the hood), Solcast HA integration (today + tomorrow entities), Forecast.Solar HA integration, Auto (fallback chain) |
| Per-hour accuracy correction | 4-day rolling per-hour-of-day factor in [0.3, 1.5]. Applied inside the optimiser. |
| Intra-hour correction (v0.28.6) | Per-tick residual tracking; `_st_solar_factor = mean(actual / forecast over last 4 closed 15-min slots)`. Applied with linear decay over 2 h on top of the per-hour factor. |
| Net surplus | Predicted house load subtracted from forecast PV to compute available kWh for the battery. Grid charge skipped when solar will fill the battery. |

### House load model

| Item | Detail |
|---|---|
| Per-hour profile | 24 slots, ~8-day exponential moving average per slot |
| Short-term mean | 2-hour rolling average |
| Long-term mean | 28-day rolling average |
| Vacation detection | If load drops below 25% of 28-day baseline for ≥ 4 hours, the model switches to a conservative estimate. |
| Outlier guard | Two-layer: physical ceiling at `grid_max_kw`, soft cap at 5× current estimate once warm. |
| EV-subtracted (v0.28.0) | Active EV charge power is subtracted before learning, so leaving a car plugged in does not inflate the predicted 24-h house load. |

### EV-aware scheduling (requires EVCC live data mode)

EV-aware features run in EVCC and Hybrid live-data modes. In FoxESS-only mode they are inactive (probability stays at 0).

| Item | Detail |
|---|---|
| Charging detection | Based on actual EV charge power, configurable 500–10000 W (default > 3000 W). |
| Hourly probability | Exponential smoothing over ~8 days. Grid charging is blocked in hours where EV charges ≥ 70% of the time. |
| Max charge rate | ~20-sample EMA from full-speed sessions only (≥ 80% of current learned max). Solar-throttled sessions excluded. |
| Battery-bypass model | EVCC's setting "battery does not feed the EV" is honoured. Solar allocated to the EV is subtracted from battery-available kWh, not from battery discharge. |
| EVCC battery mode | Set to `hold` during arbitrage actions. Restored to `normal` when done. If EVCC has independently taken control, the integration backs off. |

### EV charge controller (opt-in)

Optional active control of a connected charger, disabled by default. Enable in *Settings → Solar AI → Configure → OCPP Settings*. Two backends, selectable there or on the dashboard's Advanced setup page:

| Backend | Charger | Phases |
|---|---|---|
| **OCPP** (default) | Any OCPP 1.6 charger (Easee, Zaptec, Wallbox, FoxESS, …) via the embedded server | Three-phase only; 4.14 kW (6 A) minimum |
| **FoxESS Modbus TCP** | FoxESS L11PMC over direct Modbus | Single- **and** three-phase; ~1.4 kW (6 A, 1φ) minimum |

**Single-phase charging is only available on the Modbus backend.** Over OCPP the charger does not expose phase switching, so it is three-phase only and cannot go below 4.14 kW. The Modbus backend can hold single-phase to follow small surpluses and switch up to three-phase when the surplus is large.

Four modes selectable from the dashboard (both backends):

| Mode | Behaviour |
|---|---|
| Locked | No charging. |
| Solar-only | Charge only from real-time PV surplus. Stops when surplus drops below the minimum. If the house battery starts discharging to cover the car, charging stops. |
| Solar+Battery-to-minimum | Solar surplus first; house battery tops up to the minimum when surplus is insufficient. Stops at the battery floor. |
| Full power | Maximum charge rate from any source. House battery discharge is locked at 0 A while in this mode, so the EV's grid demand cannot be supplemented from the house battery. On the Modbus backend, full mode always uses three-phase. |

Control loop properties:

- Decoupled asyncio task at a configurable cadence (5–60 s, default 10 s), independent of the main coordinator fast-poll. Editable live from the Advanced setup page; on the Modbus backend this is the setpoint write/heartbeat cadence (kept well under the charger's ~180 s expiry window).
- Ramps the current setpoint between 6 A and 16 A at a maximum of 2 A per tick. The resulting power depends on the active phase count (3-phase: 4.14–11 kW; single-phase: ~1.4–3.7 kW).
- Subtracts the EV's own current draw from house load when measuring surplus.
- Anti-flap windows: start window (default 60 s, range 10–600 s) and stop window (default 180 s, range 30–1800 s). After a stop, the start counter resets.
- **Modbus phase switching** (Modbus backend only): single ↔ three-phase by hysteresis on the available surplus — up at a sustained ≥ 4.5 kW, down at < 4.0 kW — gated by the charger's 5-minute suspend interval so it never flaps or pauses the session. Phase count is read back from the per-phase currents.
- **Modbus setpoint heartbeat:** the charger's limits expire ~180 s after the last command (reverting to full three-phase), so the controller re-asserts them every cycle.
- Smart OCPP writes: `SetChargingProfile` is only sent on start, stop, or ≥ 1 A change.
- `sensor.solar_ai_ev_status` exposes the controller state machine (`IDLE` / `ARMING` / `CHARGING` / `COOLING`) and `arming_until` / `cooling_until` ISO timestamps for live per-second countdowns. On the Modbus backend, `sensor.solar_ai_lader_effekt` reports live power, per-phase currents, and the live vs target phase count.

### Battery model

| Item | Detail |
|---|---|
| Round-trip efficiency | Auto-detected from FoxESS lifetime charge/discharge totals. Activates after 100 kWh cycled. Falls back to configured value until then. |
| Usable capacity | Learned during Force Charge cycles by measuring energy delivered vs SoC rise per tick. Activates after 20 samples. |
| Temperature-adaptive charge rate | 7 buckets: `< 0`, `0–5`, `6–15`, `16–21`, `21–35`, `35–50`, `> 50 °C`. Each bucket records actual charge power during Force Charge and updates the learned rate at the 90th percentile. Each bucket is also exposed as an editable number entity for manual override. |

### Seasonal mode

- 28-day rolling daily solar average switches between `summer` and `winter` mode at a threshold of 6 kWh/day.
- Defaults to `winter` (conservative) until at least 7 days of data are recorded.
- No hard-coded calendar dates.

### Grid overcurrent protection

- Every fast-poll tick reads live grid import power (from EVCC or directly from the FoxESS CT clamp).
- Available headroom = `breaker limit − 0.5 kW safety margin − current grid draw`.
- The battery charge rate is automatically capped to stay within the breaker limit.
- Grid charging is skipped entirely if headroom drops below 0.3 kW.
- Limit is configurable in the config flow (5–63 kW, default 17 kW).

### Savings tracker

- Actual savings: revenue from battery export plus the estimated value of cheap grid charging.
- Missed savings: estimated opportunity cost while the arbitrage switch is off.
- Reported for today, 7 days, and 30 days.
- Stored in a 90-day rolling log that survives HA restarts.
- Hours blocked by the minimum export price floor are excluded from both actual and missed calculations.

### Polling

- Live state (grid power, PV, EV status, battery mode) is fetched on every fast-poll tick.
- Price and tariff data is refreshed at most once per hour.
- Live data poll interval is configurable in *Configure* (10–300 s, default 30 s).

### Settings reference

Every setting below is editable from the dashboard (**Indstillinger / Settings** page) without restarting HA — changes take effect on the next coordinator cycle. The groupings match the cards on that page. Home Assistant shows the labels in Danish on a Danish install and in English elsewhere — both are listed below (**English**<br>_Danish_).

#### Master controls

| Setting | Type | What it does |
|---|---|---|
| **Arbitrage enabled**<br>_Arbitrage aktiv_ | on/off | Master switch. When **off**, Solar AI still computes and reports its plan but sends **no** charge/export commands to the inverter — i.e. monitoring mode. Turn on to let it actually control the battery. |
| **Mode-change notifications**<br>_Notifikationer ved tilstandsskift_ | on/off | Master toggle for push notifications on mode changes (the per-event toggles below still apply). |
| **15-minute price resolution**<br>_15-minutters prisopløsning_ | on/off | **Display only.** On = the price chart shows every 15-min slot; off = one row per hour. Does **not** affect the calculations — the optimiser always runs at native 15-min resolution. |

#### Battery limits

| Setting | Range | Default | What it does |
|---|---|---|---|
| **Minimum SoC (export)**<br>_Minimum SoC (eksport)_ | 10–100 % | 50 % | The static export floor — the battery is never *exported* below this SoC, reserving the rest for the house. Ignored while *Dynamic discharge floor* is on. |
| **Maximum SoC (grid charge)**<br>_Maksimum SoC (netopladning)_ | 10–100 % | 100 % | Ceiling that grid-charging will fill the battery to. |
| **Export power cap**<br>_Eksporteffekt-grænse (0 = ingen)_ | 0–10 kW | 0 (no cap) | Limits how fast the battery discharges to the grid. 0 = use the full available rate. |
| **Grid import limit**<br>_Net-importgrænse_ | 5–63 kW | 17 kW | Your main breaker rating. Total grid draw is kept under this — grid-charge power is reduced to leave headroom for house + EV load. |
| **Dynamic discharge floor**<br>_Dynamisk afladningsgulv (selvlærende)_ | on/off | off | When on, replaces the static *Minimum SoC* with a self-learning floor sized to run the house from now until solar covers it again, on top of the hardware minimum SoC. A planned grid-charge is netted off the reserve only for the energy it actually returns (so a token charge does not lower the floor; a real cheap multi-hour charge does). Short bright night → lower floor (export more); long winter night → higher floor (hold more). The safety margin self-corrects daily from how far the SoC actually fell. |
| **Effective discharge floor**<br>_Effektivt afladningsgulv_ | read-only | — | Shows the floor actually in effect right now (the static value, or the computed dynamic reserve) plus the self-learned safety margin. |

#### Price parameters

These build the buy- and sell-side prices the optimiser uses. (The DSO + Energinet **net tariff is fetched automatically** from Energi Data Service — it is not set here.)

| Setting | Range | Default | What it does |
|---|---|---|---|
| **Buy-side VAT**<br>_Moms på køb_ | 0–50 % | 25 % | VAT applied to the buy price. |
| **Electricity duty (elafgift)**<br>_Elafgift_ | 0.00–3.00 DKK/kWh | 0.01 | Danish electricity tax added to the buy price. |
| **Spot price markup**<br>_Spotpris-tillæg (elhandlertillæg)_ | 0.00–0.50 DKK/kWh | 0.00 | Your retailer's per-kWh add-on on top of spot (buy side). |
| **Sell-side fee**<br>_Salgsgebyr_ | 0.00–0.50 DKK/kWh | 0.00 | Per-kWh cut your provider takes from export revenue (subtracted from the sell price). |
| **Minimum export price**<br>_Minimum eksportpris (0 = tillad negativ)_ | 0.00–2.00 DKK/kWh | 0.00 | Blocks exporting when the net sell price is below this. 0 = allow any price, including negative. |

#### Optimizer

| Setting | Range | Default | What it does |
|---|---|---|---|
| **Minimum arbitrage spread**<br>_Minimum arbitrage-spread_ | 0.00–3.00 DKK/kWh | 0.30 | Required gap between selling now and buying back later (after round-trip losses) before the optimiser will export-and-rebuy. Higher = more conservative, fewer cycles. |
| **Battery wear cost**<br>_Batteri-slidomkostning_ | 0.00–1.00 DKK/kWh | 0.10 | Estimated battery degradation per kWh cycled. Subtracted from both charge and export rewards so the optimiser won't cycle the battery for tiny gains. Higher = less cycling. |
| **Solar confidence**<br>_Sol-konfidens_ | 10–90 % | 50 | The percentile of each hour's solar forecast the optimiser plans against. 50 = median (neutral, = previous behaviour). Lower = assume less solar (more conservative — grid-charges more readily in cheap windows, holds back more battery). |

#### EV charge controller (requires the OCPP server or EVCC live-data mode)

| Setting | Range | Default | What it does |
|---|---|---|---|
| **EV minimum charge rate**<br>_EV minimum opladningshastighed_ | 1.4–11 kW | 4.14 | Lowest rate the controller will run the car at — your charger's minimum (4.14 kW ≈ 3-phase 6 A). |
| **EV maximum charge rate**<br>_EV maksimum opladningshastighed_ | 1.4–22 kW | 11.0 | Cap on the EV charge rate (11 kW ≈ 3-phase 16 A). |
| **Battery-first threshold**<br>_Batteri-først tærskel_ | 50–100 % | 80 % | In solar modes, the EV waits until the house battery reaches this SoC before it starts consuming solar surplus. |
| **Auto-Full on negative price**<br>_Auto-Fuld ved negativ pris_ | on/off | off | When on, automatically promotes the EV to Full charging while the buy price is negative (paid to consume), then restores the previous mode afterwards. |

#### Charge rates by temperature (auto-learned)

Seven `Max charge rate` / `Maks. opladning` controls (`<0`, `0–5`, `6–15`, `16–21`, `21–35`, `35–50`, `>50 °C`) hold the battery's maximum charge rate per cell-temperature band. These are **learned automatically** from observed charging; you can override a band manually if needed.

#### Notifications

Per-event push toggles — **export started / stopped**, **charging started / stopped**, **solar export blocked / resumed (price floor)** — plus one toggle per discovered Home Assistant Companion device to choose where notifications are delivered.

### Export income

`sensor.solar_ai_eksport_indtaegt` ("Solar AI Eksport-indtægt" / "Export income") tracks revenue from exported energy. Each coordinator tick it adds `feed-in kW × interval × export price` to a running total and to a per-day log. Attributes hold the rolled-up periods:

| Attribute | Period |
|---|---|
| `today` | Since local midnight |
| `last_7_days` | Trailing 7 days |
| `last_30_days` | Trailing 30 days |
| `this_month` | Calendar month to date |
| `this_year` | Calendar year to date |
| `daily` | List of `{date, dkk}` (last ~400 days) |

The Prices page shows these as a chip row plus a daily-income bar chart.

For an arbitrary from/to date range with daily/weekly/monthly breakdowns, add the sensor to Home Assistant's **Energy dashboard** — the sensor is `device_class: monetary`, `state_class: total_increasing`, so HA keeps long-term statistics for it:

1. **Settings → Dashboards → Energy**.
2. Under **Grid consumption / Return to grid**, on the *Return to grid* energy source, set its **cost/income** to *Use an entity tracking the total costs* and pick `sensor.solar_ai_eksport_indtaegt` (or add it as an individual monetary sensor).
3. Open the **Energy** dashboard; its date-range picker (day / week / month / year / custom from–to) then shows export income for any period.

Pair it with the feed-in kWh entity for energy totals and the export-price entity for the rate, both of which the integration already reads.

**Note — export income is gross.** `export_income` is export revenue only; it does **not** subtract what you pay to import. For the true net position, two companion sensors are provided (v0.48.0):

- **`import_cost`** ("Import-omkostning" / "Import cost") — cumulative cost of **all** grid import (house load *and* battery grid-charging), `import kWh × full buy price` per tick, with the same period attributes.
- **`net_grid_balance`** ("Netto el-balance" / "Net grid balance") — **export income − import cost** (can be negative if you're a net buyer), with `today` / `last_7_days` / `last_30_days` / `this_month` / `this_year` and a daily net series.

The Prices page shows a net-balance card beside the export-income card.

---

### Disk-space alarm

On a Raspberry Pi / SD-card install the disk can fill up over time (mostly Home Assistant's recorder database). Solar AI watches free space on the partition HA runs on and warns before it becomes a problem.

| Entity | What it does |
|---|---|
| `sensor.solar_ai_disk_free` ("Ledig diskplads" / "Free disk space") | Free space in GB. Attributes: `pct_free`, `total_gb`, `used_gb`, `path`, `alarm_threshold_pct`. |
| `binary_sensor.solar_ai_disk_low` ("Lav diskplads" / "Low disk space") | Problem sensor — on when free space is below the threshold. Hang your own automations off this. |
| `number.solar_ai_…_threshold` ("Alarmgrænse for lav diskplads" / "Low-disk alarm threshold") | The threshold in **% free** (default 10, range 1–50), in the settings panel. |
| `switch.solar_ai_…_notify_disk_low` ("Notifikation: lav diskplads" / "Notify: low disk space") | Toggles the mobile push (default on). |

Free space is checked every 5 minutes. When it first drops below the threshold a single mobile push is sent (subject to the master notifications switch and configured targets); the alarm clears only after recovering a few points above the threshold, so a borderline reading doesn't repeat. The `disk_low` binary sensor reflects the state regardless of whether push is configured.

---

## Prerequisites

### Live data mode

The integration supports three live-data modes. Pick one during setup:

| Mode | When to choose | Required components |
|---|---|---|
| EVCC | EVCC is running and EV-aware coordination is wanted | EVCC + Solcast (via EVCC) + FoxESS Modbus |
| Hybrid | EVCC handles the EV, but live grid and PV come directly from the inverter | EVCC + FoxESS Modbus + a solar forecast source |
| FoxESS only | No EV, or the EV does not draw from the house battery | FoxESS Modbus + a solar forecast source (Solcast direct or Forecast.Solar) |

Note on FoxESS-only mode: if there is an OCPP-connected EV charger, the embedded OCPP server (v0.27.0+) still detects EV charging directly via the charger. Grid-headroom protection caps battery charging based on live grid-import readings in all modes. EV-aware scheduling (skip grid charge during typical EV hours, hourly probability learning) requires EVCC live-data mode and is inactive in FoxESS-only mode.

### Component checklist

| Component | EVCC | Hybrid | FoxESS only | Link |
|---|:---:|:---:|:---:|---|
| FoxESS Modbus integration | Required | Required | Required | [GitHub](https://github.com/nathanmarlor/foxess_modbus) |
| EVCC | Required | Required | Not used | [evcc.io](https://evcc.io) |
| Solar forecast (one of: EVCC/Solcast, Solcast HA integration with both today + tomorrow entities, Forecast.Solar) | Required | Required | Required (excl. EVCC) | [Solcast](https://solcast.com) / [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) |
| Spot price entity (Strømligning, Tibber, etc.) | Optional | Optional | Optional | — |

If no spot price entity is configured, Solar AI reads spot prices directly from [Energi Data Service](https://api.energidataservice.dk).

### Solcast HA integration — two-entity wiring (v0.28.0+)

The Solcast HA integration creates one entity per forecast day (typically `sensor.solcast_pv_forecast_forecast_today` and `sensor.solcast_pv_forecast_forecast_tomorrow`). The integration reads both for a full 48-hour forecast. Set them in *Settings → Solar AI → Configure → Solar forecast source*:

| Field | Set to |
|---|---|
| Solar forecast source | `solcast` |
| Solcast (today) | `sensor.solcast_pv_forecast_forecast_today` |
| Solcast (tomorrow) | `sensor.solcast_pv_forecast_forecast_tomorrow` |

If the tomorrow field is left blank, the optimiser plans against a 24-h horizon (today only). With both wired, the optimiser plans against the full 48 h and avoids night-time grid charges when the next day is sunny.

### Feature availability by mode

| Feature | EVCC | Hybrid | FoxESS only |
|---|:---:|:---:|:---:|
| Day-ahead DP optimiser (15-min, 48-h) | Yes | Yes | Yes |
| Battery floor / max SoC enforcement | Yes | Yes | Yes |
| Minimum arbitrage spread + degradation cost | Yes | Yes | Yes |
| Solar export floor | Yes | Yes | Yes |
| Temperature-adaptive charge rate learning | Yes | Yes | Yes |
| Capacity + round-trip efficiency auto-detection | Yes | Yes | Yes |
| Solar forecast accuracy learning | Yes | Yes | Yes |
| House load profile learning | Yes | Yes | Yes |
| 30-day savings tracker | Yes | Yes | Yes |
| Session log (exports and charges) | Yes | Yes | Yes |
| Mode-change notifications | Yes | Yes | Yes |
| Live dashboard sliders / switches | Yes | Yes | Yes |
| Grid headroom overcurrent protection | Yes | Yes | Yes (FoxESS CT) |
| EV-aware optimiser scheduling | Yes | Yes | No |
| EV charge probability learning | Yes | Yes | No (stays at 0) |
| EVCC battery-mode coordination | Yes | Yes | n/a |

### Dashboard dependencies (HACS)

The bundled dashboard uses several custom Lovelace cards. Install all of them via HACS → Frontend before importing the dashboard:

| Card | Used by | Link |
|---|---|---|
| Mushroom Cards | Status tiles, charge-mode selector, Bil-tilsluttet card, section titles | [GitHub](https://github.com/piitaya/lovelace-mushroom) |
| ApexCharts Card | 24-h price/SoC chart, 48-h Solcelleprognose chart | [GitHub](https://github.com/RomRider/apexcharts-card) |
| Power Flow Card Plus | Animated energy-flow diagram on the home screen (required since v0.40.0) | [GitHub](https://github.com/flixlix/power-flow-card-plus) |
| card-mod | Layout/width styling of the home screen and subviews (required since v0.40.0) | [GitHub](https://github.com/thomasloven/lovelace-card-mod) |
| button-card | Styling helper for cohesive cards (required since v0.40.0) | [GitHub](https://github.com/custom-cards/button-card) |

After installing them all, hard-refresh the browser (⌘+Shift+R on macOS, Ctrl+Shift+R elsewhere) before importing the dashboard YAML.

### FoxESS Modbus entity IDs

The setup wizard auto-detects these. Override them in the config flow if your names differ:

```
sensor.foxessmodbus_battery_soc_1
sensor.foxessmodbus_bms_cell_temp_low_1
sensor.foxessmodbus_battery_charge
sensor.foxessmodbus_battery_discharge
sensor.foxessmodbus_load_power
sensor.foxessmodbus_feed_in
select.foxessmodbus_work_mode
number.foxessmodbus_force_charge_power
number.foxessmodbus_force_discharge_power
```

---

## Decision loop

### Hourly — optimiser run

```
On spot price refresh (typically once per hour):

1. Fetch prices:
   - Energi Data Service Elspotprices (Nord Pool day-ahead, area DK2)
   - Falls back to EVCC /api/tariff/grid if EDS is unreachable
   - Buy-side: (spot + markup + DSO tariff + Energinet tariff + elafgift) × VAT
   - Sell-side: spot − seller-side fee − indfødningstarif (auto-fetched daily)

2. Run DP optimiser (backward induction):
   - State: battery SoC at 1% resolution (0–100% = 101 states)
   - Actions per slot: CHARGE | EXPORT | IDLE
   - Inputs: per-slot buy/sell prices, learned house load profile (24 slots),
             per-slot solar forecast (with per-hour + short-term correction),
             EV hourly probability × learned max rate, charge/discharge
             efficiency, floor SoC, max SoC
   - EXPORT allowed only when:
       sell_price > min_export_price floor
       AND sell_price − cheapest_recharge / efficiency ≥ min_spread
   - CHARGE blocked for hours where EV typically charges (≥ 70% probability)
   - Output: ordered plan {slot_start, action, expected SoC, buy, sell}

3. Plan is stored and drives decisions for the next 60 minutes.
```

### Fast tick — execution

```
1. Fetch EVCC state: grid power, solar, EV charge power, battery mode.
2. Read FoxESS: SoC, cell temp, charge/discharge power, work mode.
3. Update models: house load hourly profile, EV max rate, load history,
                  solar accuracy (long-term + short-term), EV hourly probability,
                  daily solar kWh.
4. Compute grid headroom: limit − 0.5 kW − current import.
5. Look up the plan for the current slot:

   EXPORT if      optimiser says EXPORT
              AND sell price > min export price floor
              AND exportable kWh ≥ 0.5
              AND SoC > floor SoC
              AND EV is not actively charging (now / minpv mode)
              AND EVCC is not managing the battery independently

   GRID CHARGE if optimiser says CHARGE
              AND solar will not fill the battery on its own
              AND importable kWh ≥ 0.5
              AND grid headroom ≥ 0.3 kW
              AND EV is not likely charging this hour

   FORCED CHARGE if buy price ≤ 0 (overrides all other checks)

   FALLBACK if no plan exists yet: reactive logic — export if sell ≥ p75,
   charge if buy ≤ p25.

6. Execute (if the master switch is on): set FoxESS work mode, capped
   charge power, EVCC mode. Optionally cap discharge to max_export_kw.
7. Write export limit register every tick:
     grid charging   → 0 W
     price ≤ floor   → 25 W (blocks solar + battery export)
     price > floor   → 10000 W
8. Send a persistent HA notification on mode transition (optional).
9. Accumulate actual / missed DKK into the daily log.
10. Persist learned state (rates, load history, EV probabilities, solar history).
```

---

## Sensor reference

### Decision and control

| Entity | Description |
|---|---|
| `switch.*_arbitrage_aktiv` | Master on/off switch |
| `switch.*_notifikationer_ved_tilstandsskift` | Mode-change notifications toggle |
| `sensor.*_driftstilstand` | Current mode: `normal` / `exporting` / `grid_charging` / `disabled` |
| `sensor.*_begrundelse_for_tilstand` | Plain-language reason for the current decision |

### Price

| Entity | Description |
|---|---|
| `sensor.*_eksportpris` | Current net export price (DKK/kWh). Never < 0. |
| `sensor.*_net_arbitrage_spread` | Export price minus 24-h minimum buy price |
| `sensor.*_24h_prisminimum/maksimum/gennemsnit` | 24-h price statistics |
| `sensor.*_24h_pris_25/75_percentil` | Quartile thresholds used for fallback decisions |
| `sensor.*_naeste_slots_pris` | Price for the next 30-minute slot |
| `sensor.*_nettarif_denne_time` | DSO + Energinet + elafgift for the current hour (DKK/kWh) |
| `sensor.*_indfodningstarif_dso_energinet` | Auto-fetched feed-in production tariff (DKK/kWh) |
| `sensor.*_minimum_eksportpris` | Configured export price floor |
| `sensor.*_24h_priskort` | 24-h price chart sensor; `slots` attribute = list of `{h, buy, sell}` |
| `sensor.*_dagens_plan` | Today's plan as plain text; `charge_hours` and `export_hours` attributes |

### Number entities (live-editable)

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

| Entity | Range | Description |
|---|---|---|
| `number.*_minimum_arbitrage_spread` | 0.00–3.00 DKK/kWh | Spread threshold before arbitrage triggers |
| `number.*_minimum_eksportpris_*` | 0.00–2.00 DKK/kWh | Minimum export price floor |
| `number.*_eksporteffekt_graense_*` | 0–10 kW | Max battery discharge power during export (0 = no cap) |
| `number.*_salgsgebyr_pr_kwh` | 0.00–0.50 DKK/kWh | Seller-side fee |
| `number.*_spotpris_tillaeg_*` | 0.00–0.50 DKK/kWh | Retailer spot markup |
| `number.*_elafgift_dkk_kwh` | 0.00–3.00 DKK/kWh | Elafgift |
| `number.*_moms_pa_kob` | 0–50% | VAT on purchases |
| `number.*_minimum_soc_eksport` | 10–100% | Battery floor SoC for export |
| `number.*_maksimum_soc_netopladning` | 10–100% | Battery max SoC for grid charging |
| `number.*_net_importgraense` | 5–63 kW | Circuit breaker capacity |

### Solar

| Entity | Description |
|---|---|
| `sensor.*_solcelleproduktion_live` | Real-time PV output (kW) |
| `sensor.*_solcelle_prognose_24h/6h` | Raw Solcast forecast (kWh) |
| `sensor.*_solcelle_prognose_24h/6h_justeret` | Accuracy-corrected forecast |
| `sensor.*_solcelle_prognose_nojagtighed` | Rolling accuracy factor (%) |
| `sensor.*_netto_sol_til_batteri_24h` | Net solar surplus after house load (kWh) |
| `sensor.*_sol_gennemsnit_28_dage` | 28-day average daily solar production (kWh) |
| `sensor.*_saesontilstand` | `summer` or `winter` |
| `sensor.*_solcelleprognose_48t_graf` | 48-h chart sensor; `slots` attribute = per-slot `{start, raw_kw, adj_kw, factor}` |
| `sensor.*_solcelleprognose_fejl_nu` | Short-term forecast deviation (%) over the last 4 closed 15-min slots |

### Battery

| Entity | Description |
|---|---|
| `sensor.*_eksporterbar_energi` | kWh available for export above floor SoC |
| `sensor.*_importerbar_energi` | kWh room to charge below max SoC |
| `sensor.*_tid_til_fuld_opladning` | Hours to reach max SoC at current rate |
| `sensor.*_batteritemperatur_laveste_celle` | Lowest cell temperature |
| `sensor.*_laert_opladningshastighed_*` | Learned charge rate per temperature bucket (kW) |
| `sensor.*_laert_batterikapacitet` | Learned usable capacity (kWh). Active after ~20 samples. |
| `sensor.*_auto_detekteret_effektivitet` | Measured round-trip efficiency from FoxESS lifetime totals (%) |
| `sensor.*_kapacitets_laeringseksempler` | Number of capacity learning samples collected |

### Grid

| Entity | Description |
|---|---|
| `sensor.*_net_importeffekt` | Live grid import power (kW) |
| `sensor.*_net_raaderum` | Headroom before breaker limit (kW) |

### EV and load

| Entity | Description |
|---|---|
| `sensor.*_ev_opladningssandsynlighed_denne_time` | Learned EV charge probability this hour (%) |
| `sensor.*_ev_maks_opladningshastighed_laert` | Learned EV peak AC charge rate (kW) |
| `sensor.*_husstand_forbrug_2h_gennemsnit` | 2-h average house load (kW) |
| `sensor.*_husstand_forbrug_28_dages_gennemsnit` | 28-day average house load (kW) |
| `sensor.*_huslast_laert_denne_time` | Learned house load for the current hour of day (kW); `profile_kw` attribute = 24-slot array |
| `sensor.*_forudsagt_husstand_forbrug_24h` | Predicted house consumption today (kWh) |
| `binary_sensor.*_ev_oplader_solenergi` | EV is charging on solar power (pv mode, > 3 kW) |

### EV controller

| Entity | Description |
|---|---|
| `sensor.*_ev_status` | State machine: `IDLE` / `ARMING` / `CHARGING` / `COOLING`. Attributes include `arming_until`, `cooling_until` (ISO timestamps for live countdown), `target_kw`, `target_amps`, `surplus_kw`. |
| `sensor.*_lader_status` | OCPP status from the charger |
| `sensor.*_lader_effekt` | Live charger power (kW) |
| `sensor.*_lader_info` | Vendor / model / firmware / serial of the charger |
| `sensor.*_lader_sessions_log` | Completed session list. `sessions` attribute = last 20 sessions newest-first with `energy_kwh`, `energy_kwh_solar`, `energy_kwh_grid`, `duration_min`, `start_ts`, `end_ts`. |

### Savings

| Entity | Description |
|---|---|
| `sensor.*_faktisk_besparelse_i_dag/7_dage/30_dage` | Actual savings earned (DKK) |
| `sensor.*_forpasset_besparelse_i_dag/7_dage/30_dage` | Missed savings while disabled (DKK) |

---

## Configuration reference

All settings are in *Settings → Devices & Services → Solar AI → Configure*, or live via dashboard number entities:

| Parameter | Default | Live | Description |
|---|---|---|---|
| Battery capacity | 11.52 kWh | No (config flow) | Fallback. Replaced by learned value after ~20 Force Charge samples. |
| Round-trip efficiency | 92% | No (config flow) | Fallback. Replaced by FoxESS lifetime totals after 100+ kWh cycled. |
| Forecast horizon | 24 h | No (config flow) | Hours of price data to analyse |
| Min SoC during export | 50% | Yes | Battery will not export below this SoC |
| Max SoC for grid charge | 100% | Yes | Battery will not grid-charge above this SoC |
| Min arbitrage spread | 1.00 DKK/kWh | Yes | Minimum sell − buy spread to trigger arbitrage |
| Min export price floor | 0.00 DKK/kWh | Yes | Floor below which the integration will not export |
| Export power cap | 0 kW | Yes | Max battery discharge power during export. 0 = no cap. |
| Grid import limit | 17 kW | Yes | Circuit breaker capacity for overcurrent protection |
| Buy-side VAT | 25% | Yes | VAT on grid electricity purchases |
| Seller-side fee | 0.00 DKK/kWh | Yes | Retailer's per-kWh cut on exports |
| Spot price markup | 0.00 DKK/kWh | Yes | Retailer's add-on to spot price |
| Elafgift | 0.01 DKK/kWh | Yes | Danish electricity duty |
| Indfødningstarif | Auto-fetched | Read-only sensor | Feed-in production tariff deducted from export price. Updated daily. |
| Notifications | Off | Yes | Persistent HA notification on every mode change |
| Grid operator (DSO) | Dinel (Jutland/Fyn) | Options flow | DSO for hourly network tariff and indfødningstarif data |
| Currency | DKK | Options flow | Price and savings sensor currency (DKK, EUR, SEK, NOK, GBP) |
| Live data poll interval | 30 s | Options flow | Fast-poll cadence (10–300 s) |
| Embedded OCPP server | On | Options flow → OCPP Settings | Integration hosts its own OCPP 1.6 server. Turn off to use `lbbrhzn/ocpp` instead. |
| Embedded OCPP port | 9000 | Options flow → OCPP Settings | TCP port the embedded server listens on |
| EV controller enabled | Off | Options flow → OCPP Settings | Master gate for the OCPP-driven EV charge controller |
| EV control loop interval | 10 s | Options flow → OCPP Settings | How often the EV controller re-evaluates surplus (5–60 s) |
| EV start window | 60 s | Options flow → OCPP Settings | Sustained-surplus seconds before charging starts (10–600 s) |
| EV stop window | 180 s | Options flow → OCPP Settings | Sustained-shortage seconds before charging stops (30–1800 s) |
| EV charging detection threshold | 3000 W | Options flow → OCPP Settings | Above this charge power, the EV is considered actually charging (500–10000 W) |
| EV default mode on plug-in | Locked | Options flow → OCPP Settings | Mode applied when a vehicle is freshly connected |
| EV min / max charge rate | 4.14 / 11.0 kW | Dashboard sliders | OCPP current setpoint range (6 A / 16 A on 3-phase) |
| Spot price area | DK2 | `CONF_PRICE_AREA` in `const.py` | Nord Pool price zone. `DK1` = Jutland/Fyn, `DK2` = Zealand/Copenhagen. Config-flow selection planned. |

---

## Services

| Service | Description |
|---|---|
| `battery_arbitrage.force_export` | Activate Feed-in First regardless of prices |
| `battery_arbitrage.force_grid_charge` | Start grid charging immediately |
| `battery_arbitrage.restore_normal` | Cancel active export or charging; return to Self-Use |
| `battery_arbitrage.reset_learning` | Clear all learned rates, load history, and solar samples |

---

## Known limitations

- **Denmark-focused.** The price model is built around DKK/kWh, Nord Pool Elspot via Energi Data Service, and the Danish DatahubPricelist tariff API. Tariff fetching is Danish-specific. The spot price area defaults to DK2; change `DEFAULT_PRICE_AREA` in `const.py` for DK1.
- **FoxESS Modbus required.** Work-mode control uses FoxESS-specific entities. Other inverters require code changes in `coordinator.py`.
- **EVCC required for EV-aware scheduling.** Solar forecasts, live grid power, and EV charge data come from EVCC's API in EVCC and Hybrid modes. FoxESS-only mode loses the EV-aware scheduling features (the OCPP controller still works).
- **DSO coverage.** Network tariff and indfødningstarif auto-fetch covers Dinel (Jutland/Fyn). Other Danish DSOs can be added in `const.py`; GLN numbers are available in the Energi Data Service DatahubPricelist.
- **Learning period.** The system reaches steady-state accuracy after 1–2 weeks of data. The first few days use conservative defaults for charge rates and EV patterns.
- **GBP installs still see some DKK labels.** UK users on Octopus (v0.30.0+) get correct numeric values, but six number-entity sliders (spot markup, elafgift, sell-side fee, min export price, battery degradation cost, min arbitrage spread), two savings sensors, mode-change notifications, and the "Elafgift" label all render hardcoded `DKK/kWh`. The math is unaffected. To be addressed in a follow-up release with template-substituted units.
- **15-second card refresh depends on the data source (v0.36.0+).** The default fast-poll interval is now 15 s, so integration-driven sensors (price stack, savings, EV status, surplus, plan) publish new values every 15 s and cards re-render at that cadence. Upstream data sources have their own polls:
  - **FoxESS Modbus** — poll rate is adapter-specific and not exposed in the UI. `direct` / TCP adapters poll every ~5 s (already faster than 15 s); `aux` serial adapters are slower. No user action needed for direct/LAN setups.
  - **Solcast Solar HA integration** — rate-limited by Solcast's API tier (free tier: 10 calls/day ≈ one refresh every 2.4 h; paid tiers higher). Forecasts server-side change every 30–60 minutes anyway, so a faster local poll wouldn't add freshness.
  - **OCPP charger** — event-driven; the charger pushes `MeterValues` to Solar AI's embedded server when the reading changes, not on a fixed schedule.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

---

## License

MIT.
