"""Battery Arbitrage integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BATTERY_CHARGE_ENTITY,
    CONF_BATTERY_CHARGE_TOTAL_ENTITY,
    CONF_BATTERY_DISCHARGE_ENTITY,
    CONF_BATTERY_DISCHARGE_TOTAL_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CELL_TEMP_ENTITY,
    CONF_CURRENCY,
    CONF_DSO_GLN,
    CONF_FAST_POLL_INTERVAL,
    CONF_SOLAR_FORECAST_SOURCE,
    CONF_LIVE_DATA_SOURCE,
    CONF_EV_CONTROLLER_ENABLED,
    CONF_EV_DEFAULT_MODE,
    CONF_EV_CONTROL_INTERVAL_SECONDS,
    CONF_EV_START_WINDOW_SECONDS,
    CONF_EV_STOP_WINDOW_SECONDS,
    CONF_EV_CHARGE_THRESHOLD_W,
    CONF_EV_BATTERY_PRIORITY_SOC,
    CONF_OCPP_EMBEDDED,
    CONF_OCPP_PORT,
    CONF_OCPP_RESTART_STRICT,
    CONF_OCPP_REMOTE_START_COOLDOWN_S,
    CONF_BUY_PRICE_MODE,
    CONF_STROMLIGNING_SUPPLIER_ID,
    CONF_STROMLIGNING_PRODUCT_ID,
    CONF_STROMLIGNING_CUSTOMER_GROUP,
    CONF_STROMLIGNING_USE_MANUAL_OVERRIDES,
    CONF_SELL_SIDE_COMPANY,
    CONF_COUNTRY,
    CONF_OCTOPUS_PRODUCT_CODE,
    CONF_OCTOPUS_REGION,
    CONF_PRICE_AREA,
    CONF_TARIFF_FETCH_ENABLED,
    CONF_EV_SCHEDULE_LINKS,
    CONF_EV_SCHEDULED_FALLBACK_MODE,
    EV_SCHEDULES_MAX,
    CONF_FAST_POLL_INTERVAL,
    DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
    DEFAULT_EV_START_WINDOW_SECONDS,
    DEFAULT_EV_STOP_WINDOW_SECONDS,
    DEFAULT_EV_CHARGE_THRESHOLD_W,
    DEFAULT_EV_BATTERY_PRIORITY_SOC,
    DEFAULT_OCPP_EMBEDDED,
    DEFAULT_OCPP_PORT,
    DEFAULT_OCPP_RESTART_STRICT,
    DEFAULT_OCPP_REMOTE_START_COOLDOWN_S,
    DEFAULT_BUY_PRICE_MODE,
    DEFAULT_STROMLIGNING_CUSTOMER_GROUP,
    DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES,
    DEFAULT_SELL_SIDE_COMPANY,
    DEFAULT_COUNTRY,
    DEFAULT_OCTOPUS_REGION,
    DEFAULT_PRICE_AREA,
    DEFAULT_TARIFF_FETCH_ENABLED,
    DEFAULT_EV_SCHEDULED_FALLBACK_MODE,
    DEFAULT_FAST_POLL_SECONDS,
    CONF_SPOT_MARKUP,
    CONF_SPOT_PRICE_ENTITY,
    CONF_STROMLIGNING_ENTITY,
    CONF_CREATE_DASHBOARD,
    DOMAIN,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_FLOOR_SOC,
    CONF_BATTERY_MAX_SOC,
    CONF_FORECAST_HOURS,
    CONF_MIN_SPREAD_ARBITRAGE,
    CONF_ROUND_TRIP_EFFICIENCY,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_FLOOR_SOC,
    DEFAULT_BATTERY_MAX_SOC,
    DEFAULT_CURRENCY,
    DEFAULT_DSO_GLN,
    DEFAULT_FAST_POLL_SECONDS,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_MIN_SPREAD_ARBITRAGE,
    DEFAULT_ROUND_TRIP_EFFICIENCY,
    DEFAULT_SOLAR_FORECAST_SOURCE,
    DEFAULT_LIVE_DATA_SOURCE,
    DEFAULT_EV_CONTROLLER_ENABLED,
    DEFAULT_EV_DEFAULT_MODE,
    DEFAULT_SPOT_MARKUP,
    FOXESS_BATTERY_CHARGE_POWER,
    FOXESS_BATTERY_CHARGE_TOTAL,
    FOXESS_BATTERY_DISCHARGE_POWER,
    FOXESS_BATTERY_DISCHARGE_TOTAL,
    FOXESS_BATTERY_SOC,
    FOXESS_CELL_TEMP_LOW,
    STROMLIGNING_SPOTPRICE_EX_VAT,
)
from .coordinator import BatteryArbitrageCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.TIME,        # v0.38.0 — per-schedule-slot start/end time pickers
]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current schema version.

    Called automatically by HA whenever entry.version < ConfigFlow.VERSION.
    Each version block migrates one step and falls through to the next, so
    upgrading multiple versions in a single restart works correctly.

    To add a new migration in future:
      1. Bump VERSION in config_flow.py (e.g. 2 → 3)
      2. Add an `if entry.version < 3:` block below that fills in / renames fields
    """
    _LOGGER.info("Battery Arbitrage: migrating config entry v%s → v%s",
                 entry.version, entry.domain)

    new_data = dict(entry.data)

    if entry.version < 2:
        # v1 → v2: establish a clean baseline with all known fields present.
        # Users who installed at v0.1.0 already had all of these, but any
        # edge-case partial install will be made whole here.
        new_data.setdefault(CONF_BATTERY_CAPACITY,       DEFAULT_BATTERY_CAPACITY)
        new_data.setdefault(CONF_BATTERY_FLOOR_SOC,      DEFAULT_BATTERY_FLOOR_SOC)
        new_data.setdefault(CONF_BATTERY_MAX_SOC,         DEFAULT_BATTERY_MAX_SOC)
        new_data.setdefault(CONF_ROUND_TRIP_EFFICIENCY,   DEFAULT_ROUND_TRIP_EFFICIENCY)
        new_data.setdefault(CONF_MIN_SPREAD_ARBITRAGE,    DEFAULT_MIN_SPREAD_ARBITRAGE)
        new_data.setdefault(CONF_FORECAST_HOURS,          DEFAULT_FORECAST_HOURS)

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v2")

    if entry.version < 3:
        # v2 → v3: add currency selector (defaults to DKK for existing installs)
        new_data.setdefault(CONF_CURRENCY, DEFAULT_CURRENCY)
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v3")

    if entry.version < 4:
        # v3 → v4: add configurable fast poll interval (defaults to 30 s)
        new_data.setdefault(CONF_FAST_POLL_INTERVAL, DEFAULT_FAST_POLL_SECONDS)
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v4")

    if entry.version < 5:
        # v4 → v5: add DSO GLN for tariff schedule fetching (defaults to Dinel)
        new_data.setdefault(CONF_DSO_GLN, DEFAULT_DSO_GLN)
        hass.config_entries.async_update_entry(entry, data=new_data, version=5)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v5")

    if entry.version < 6:
        # v5 → v6: fix old Dinel capacity-charges GLN → correct nettarif C time GLN;
        # also seed the new spot_markup field (retailer's per-kWh margin).
        _OLD_DINEL_CAPACITY_GLN = "5790000610976"
        if new_data.get(CONF_DSO_GLN) == _OLD_DINEL_CAPACITY_GLN:
            new_data[CONF_DSO_GLN] = DEFAULT_DSO_GLN
            _LOGGER.info(
                "Battery Arbitrage: corrected Dinel DSO GLN from %s to %s",
                _OLD_DINEL_CAPACITY_GLN, DEFAULT_DSO_GLN,
            )
        new_data.setdefault(CONF_SPOT_MARKUP, DEFAULT_SPOT_MARKUP)
        hass.config_entries.async_update_entry(entry, data=new_data, version=6)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v6")

    if entry.version < 7:
        # v6 → v7: rename stromligning_entity → spot_price_entity for generic price source
        # support.  Preserves the user's existing entity selection verbatim.
        old_entity = new_data.pop(CONF_STROMLIGNING_ENTITY, None)
        if old_entity:
            new_data[CONF_SPOT_PRICE_ENTITY] = old_entity
            _LOGGER.info(
                "Battery Arbitrage: migrated spot price entity key (%s)", old_entity
            )
        else:
            # Seed with the well-known Strømligning default so existing installs don't break
            new_data.setdefault(CONF_SPOT_PRICE_ENTITY, STROMLIGNING_SPOTPRICE_EX_VAT)
        hass.config_entries.async_update_entry(entry, data=new_data, version=7)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v7")

    if entry.version < 8:
        # v7 → v8: add configurable battery sensor entity IDs.
        # Existing installs get the FoxESS Modbus defaults — zero behaviour change.
        new_data.setdefault(CONF_BATTERY_SOC_ENTITY,             FOXESS_BATTERY_SOC)
        new_data.setdefault(CONF_CELL_TEMP_ENTITY,               FOXESS_CELL_TEMP_LOW)
        new_data.setdefault(CONF_BATTERY_CHARGE_ENTITY,          FOXESS_BATTERY_CHARGE_POWER)
        new_data.setdefault(CONF_BATTERY_DISCHARGE_ENTITY,       FOXESS_BATTERY_DISCHARGE_POWER)
        new_data.setdefault(CONF_BATTERY_CHARGE_TOTAL_ENTITY,    FOXESS_BATTERY_CHARGE_TOTAL)
        new_data.setdefault(CONF_BATTERY_DISCHARGE_TOTAL_ENTITY, FOXESS_BATTERY_DISCHARGE_TOTAL)
        hass.config_entries.async_update_entry(entry, data=new_data, version=8)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v8")

    if entry.version < 9:
        # v8 → v9: add solar forecast source picker. Existing installs keep
        # EVCC as the source so behaviour is unchanged.
        new_data.setdefault(CONF_SOLAR_FORECAST_SOURCE, DEFAULT_SOLAR_FORECAST_SOURCE)
        hass.config_entries.async_update_entry(entry, data=new_data, version=9)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v9")

    if entry.version < 10:
        # v9 → v10: add live data source picker (EVCC / Hybrid / FoxESS).
        # Existing installs keep EVCC as the source so behaviour is unchanged.
        new_data.setdefault(CONF_LIVE_DATA_SOURCE, DEFAULT_LIVE_DATA_SOURCE)
        hass.config_entries.async_update_entry(entry, data=new_data, version=10)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v10")

    if entry.version < 11:
        # v10 → v11: add EV charge controller default mode (Phase B1).
        # Existing installs default to "locked" so no surprise behaviour.
        new_data.setdefault(CONF_EV_DEFAULT_MODE, DEFAULT_EV_DEFAULT_MODE)
        hass.config_entries.async_update_entry(entry, data=new_data, version=11)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v11")

    if entry.version < 12:
        # v11 → v12: EV charge controller becomes opt-in. Existing installs get
        # ev_controller_enabled = False — the controller stays inert until the
        # user explicitly turns it on in Options.
        new_data.setdefault(CONF_EV_CONTROLLER_ENABLED, DEFAULT_EV_CONTROLLER_ENABLED)
        hass.config_entries.async_update_entry(entry, data=new_data, version=12)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v12")

    if entry.version < 13:
        # v12 → v13: EV control loop becomes time-based and configurable
        # (v0.26.0). Seed defaults for existing installs so behaviour matches
        # the previous 2-tick @ 30 s hysteresis closely (60 s start, 180 s stop,
        # 10 s loop, 3 000 W charge-detection threshold).
        new_data.setdefault(
            CONF_EV_CONTROL_INTERVAL_SECONDS,
            DEFAULT_EV_CONTROL_INTERVAL_SECONDS,
        )
        new_data.setdefault(
            CONF_EV_START_WINDOW_SECONDS,
            DEFAULT_EV_START_WINDOW_SECONDS,
        )
        new_data.setdefault(
            CONF_EV_STOP_WINDOW_SECONDS,
            DEFAULT_EV_STOP_WINDOW_SECONDS,
        )
        new_data.setdefault(
            CONF_EV_CHARGE_THRESHOLD_W,
            DEFAULT_EV_CHARGE_THRESHOLD_W,
        )
        hass.config_entries.async_update_entry(entry, data=new_data, version=13)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v13")

    if entry.version < 14:
        # v13 → v14: battery-priority SoC threshold for EV charging (v0.26.4).
        # Default 80 % — EV waits while battery fills toward this threshold.
        new_data.setdefault(
            CONF_EV_BATTERY_PRIORITY_SOC,
            DEFAULT_EV_BATTERY_PRIORITY_SOC,
        )
        hass.config_entries.async_update_entry(entry, data=new_data, version=14)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v14")

    if entry.version < 15:
        # v14 → v15: embedded OCPP server replaces lbbrhzn/ocpp dependency
        # (v0.27.0). Seed defaults: embedded=True, port=9000.
        # Users on lbbrhzn/ocpp can opt out by toggling embedded=False in
        # the OCPP Settings step.
        new_data.setdefault(CONF_OCPP_EMBEDDED, DEFAULT_OCPP_EMBEDDED)
        new_data.setdefault(CONF_OCPP_PORT, DEFAULT_OCPP_PORT)
        # v0.28.7 migration: ensure new OCPP compatibility fields have defaults
        new_data.setdefault(CONF_OCPP_RESTART_STRICT, DEFAULT_OCPP_RESTART_STRICT)
        new_data.setdefault(CONF_OCPP_REMOTE_START_COOLDOWN_S, DEFAULT_OCPP_REMOTE_START_COOLDOWN_S)
        # v0.29.0 migration: introduce Strømligning retailer pricing as a new
        # optional buy-price source. Default is "manual" so existing installs
        # keep their current behaviour unchanged.
        new_data.setdefault(CONF_BUY_PRICE_MODE, DEFAULT_BUY_PRICE_MODE)
        new_data.setdefault(CONF_STROMLIGNING_SUPPLIER_ID, "")
        new_data.setdefault(CONF_STROMLIGNING_PRODUCT_ID, "")
        new_data.setdefault(CONF_STROMLIGNING_CUSTOMER_GROUP, DEFAULT_STROMLIGNING_CUSTOMER_GROUP)
        new_data.setdefault(CONF_STROMLIGNING_USE_MANUAL_OVERRIDES, DEFAULT_STROMLIGNING_USE_MANUAL_OVERRIDES)
        new_data.setdefault(CONF_SELL_SIDE_COMPANY, DEFAULT_SELL_SIDE_COMPANY)
        # v0.30.0 migration: country picker + UK Octopus support. Existing
        # installs default to Denmark (Strømligning path). UK fields are
        # empty until the user opts in via Configure → Buy-price source.
        new_data.setdefault(CONF_COUNTRY, DEFAULT_COUNTRY)
        new_data.setdefault(CONF_OCTOPUS_PRODUCT_CODE, "")
        new_data.setdefault(CONF_OCTOPUS_REGION, DEFAULT_OCTOPUS_REGION)
        # v0.30.1: lift CONF_PRICE_AREA from the const.py-only default into
        # the config entry, and add the CONF_TARIFF_FETCH_ENABLED toggle.
        # Existing installs default to DK2 + tariff fetch on (current behaviour).
        new_data.setdefault(CONF_PRICE_AREA, DEFAULT_PRICE_AREA)
        new_data.setdefault(CONF_TARIFF_FETCH_ENABLED, DEFAULT_TARIFF_FETCH_ENABLED)
        # v0.36.0: Phase A EV scheduling — empty list is the safe default;
        # the user enables it by setting EV mode to "scheduled" and adding
        # links via Configure → EV schedules.
        new_data.setdefault(CONF_EV_SCHEDULE_LINKS, [])
        new_data.setdefault(CONF_EV_SCHEDULED_FALLBACK_MODE, DEFAULT_EV_SCHEDULED_FALLBACK_MODE)
        # v0.36.0: default fast-poll dropped 30 → 15 so cards refresh every
        # 15 s. Bump existing entries that are still on the OLD default
        # (30) — preserves any explicit user customization.
        if new_data.get(CONF_FAST_POLL_INTERVAL) == 30:
            new_data[CONF_FAST_POLL_INTERVAL] = DEFAULT_FAST_POLL_SECONDS
        hass.config_entries.async_update_entry(entry, data=new_data, version=15)
        _LOGGER.info("Battery Arbitrage: migrated config entry to v15")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Battery Arbitrage from a config entry."""
    coordinator = BatteryArbitrageCoordinator(hass, dict(entry.data))
    await coordinator.async_load_storage()
    await coordinator.async_config_entry_first_refresh()

    # Disable the legacy export-limit automation so it can't fight us over register 46616
    await coordinator.async_disable_legacy_automation()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Start the embedded OCPP server BEFORE forwarding to platforms so the
    # sensor entities can immediately read from `coordinator.ocpp_server`.
    # (v0.27.0). Skipped cleanly if user opted out via embedded=False.
    if entry.data.get(CONF_OCPP_EMBEDDED, DEFAULT_OCPP_EMBEDDED):
        from .ocpp_server import OcppServer
        port = int(entry.data.get(CONF_OCPP_PORT, DEFAULT_OCPP_PORT))
        # Share the persisted_metadata dict by reference (v0.27.3) — so the
        # OcppServer can pre-populate ChargePoint instances from values that
        # survived the HA restart, and so updates from the server propagate
        # back into _stored without an explicit write step.
        persisted_md = coordinator._stored.setdefault("charger_metadata", {})
        coordinator.ocpp_server = OcppServer(
            port=port,
            persisted_metadata=persisted_md,
            remote_start_cooldown_s=int(entry.data.get(
                CONF_OCPP_REMOTE_START_COOLDOWN_S,
                DEFAULT_OCPP_REMOTE_START_COOLDOWN_S,
            )),
        )
        try:
            await coordinator.ocpp_server.start()
        except OSError as err:
            _LOGGER.error(
                "Embedded OCPP server failed to start on port %d: %s. "
                "Continuing without it — EV controller will be inactive.",
                port, err,
            )
            coordinator.ocpp_server = None
    else:
        _LOGGER.info(
            "Embedded OCPP server disabled in config (using legacy lbbrhzn/ocpp)",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register integration services (only once, even with multiple entries)
    _register_services(hass)

    # v0.51.0 — opt-in: auto-create the bundled Solar AI dashboard, once.
    # Guarded by a stored flag so it never re-creates a dashboard the user
    # later deleted, and never blocks entry setup if Lovelace internals change.
    uses_our_dashboard = bool(
        entry.data.get(CONF_CREATE_DASHBOARD, False)
        or coordinator._stored.get("dashboard_auto_created")
    )
    if entry.data.get(CONF_CREATE_DASHBOARD, False) and not coordinator._stored.get(
        "dashboard_auto_created"
    ):
        from .dashboard_setup import async_create_dashboard
        if await async_create_dashboard(hass):
            coordinator._stored["dashboard_auto_created"] = True
            hass.async_create_task(coordinator._store.async_save(coordinator._stored))
    # v0.51.0 — flag any missing custom Lovelace cards via Repairs (re-checked
    # each setup, so it clears once the user installs them). Only for users who
    # are on the bundled dashboard, to avoid noise for custom-dashboard setups.
    if uses_our_dashboard:
        from .dashboard_setup import async_check_dashboard_cards
        await async_check_dashboard_cards(hass)

    # Start the decoupled EV control loop (v0.26.0). It runs at its own
    # configurable cadence regardless of the main fast-poll. Inert when the
    # controller is disabled — the loop's first action is to check the master
    # gate inside _run_ev_controller.
    await coordinator.async_start_ev_control_loop()

    # D — one-time post-setup health summary. After the first refresh, confirm
    # the key inputs are actually reading so the user knows it works (or sees
    # exactly what's missing) instead of guessing. Shown once per install.
    if not coordinator._stored.get("setup_health_notified"):
        # The summary is a nicety — it must NEVER block entry setup. Any failure
        # here is logged and swallowed so the integration always finishes loading.
        try:
            _notify_setup_health(hass, entry)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Solar AI setup-health summary failed (non-fatal)")
        else:
            coordinator._stored["setup_health_notified"] = True
            hass.async_create_task(coordinator._store.async_save(coordinator._stored))

    return True


def _notify_setup_health(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise a one-time persistent notification summarising whether Solar AI's
    key data sources are reading, right after setup (D)."""
    from homeassistant.components import persistent_notification
    from .const import (
        CONF_BATTERY_SOC_ENTITY,
        CONF_FOXESS_PV_POWER_ENTITY,
        CONF_SPOT_PRICE_ENTITY,
    )

    def _check(entity_id: str | None) -> str:
        if not entity_id:
            return "not configured"
        st = hass.states.get(entity_id)
        if st is None or st.state in ("unknown", "unavailable", "none", ""):
            return f"NOT reading yet ({entity_id})"
        unit = st.attributes.get("unit_of_measurement") or ""
        return f"OK — {st.state} {unit}".rstrip() + f" ({entity_id})"

    soc = _check(entry.data.get(CONF_BATTERY_SOC_ENTITY))
    pv = _check(entry.data.get(CONF_FOXESS_PV_POWER_ENTITY))
    spot = _check(entry.data.get(CONF_SPOT_PRICE_ENTITY))

    message = (
        "Solar AI is set up. Quick check of your data sources:\n\n"
        f"- Battery SoC: {soc}\n"
        f"- Solar power: {pv}\n"
        f"- Spot price: {spot}\n\n"
        "Anything marked \"NOT reading yet\" may just need a minute to populate "
        "after a restart — re-check under Developer Tools -> States. Prices and "
        "network tariffs are fetched automatically for your area.\n\n"
        "Solar AI starts in monitoring mode. When you're happy with what it "
        "plans, enable control with the **Solar AI on/off** switch in Settings."
    )
    persistent_notification.async_create(
        hass, message,
        title="Solar AI - setup check",
        notification_id=f"{DOMAIN}_setup_health",
    )


def _register_services(hass: HomeAssistant) -> None:
    """Register Battery Arbitrage services (idempotent)."""
    if hass.services.has_service(DOMAIN, "force_export"):
        return  # already registered

    def _get_coordinator(call: ServiceCall) -> BatteryArbitrageCoordinator | None:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        return coordinators[0] if coordinators else None

    async def handle_force_export(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator._transition_to("exporting")
            coordinator._current_mode = "exporting"
            coordinator._mode_reason = "Manually forced via service"

    async def handle_force_grid_charge(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator._transition_to("grid_charging")
            coordinator._current_mode = "grid_charging"
            coordinator._mode_reason = "Manually forced via service"

    async def handle_restore_normal(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            await coordinator.async_restore_normal()

    async def handle_reset_learning(call: ServiceCall) -> None:
        coordinator = _get_coordinator(call)
        if coordinator:
            coordinator.reset_learned_rates()

    async def handle_add_schedule_slot(call: ServiceCall) -> None:
        """v0.38.0 — Allocate the next free EV-schedule slot in coordinator
        storage and seed it with defaults. No HA `schedule.*` helper is
        created (the v0.37.0 link-based path is gone). The new slot
        materialises instantly across mode select, enabled switch,
        start/end time, and slot-summary sensor."""
        coordinator = _get_coordinator(call)
        if not coordinator:
            return
        new_slot = coordinator.add_schedule_slot_native()
        if new_slot is None:
            _LOGGER.info("add_schedule_slot: all %d slots already in use",
                         EV_SCHEDULES_MAX)
            return
        _LOGGER.info("add_schedule_slot: allocated slot %d (defaults)", new_slot)
        # Notify entities so they re-render
        async_dispatcher_send(hass, f"{DOMAIN}_schedules_changed")

    async def handle_remove_schedule_slot(call: ServiceCall) -> None:
        """v0.38.0 — Remove an EV-schedule slot's data from coordinator
        storage. Slot's entities stay (always-materialised 1..MAX) and
        report as 'empty' until the slot is re-added."""
        slot = int(call.data.get("slot", 0))
        if not (1 <= slot <= EV_SCHEDULES_MAX):
            _LOGGER.warning("remove_schedule_slot: slot %d out of range 1..%d",
                            slot, EV_SCHEDULES_MAX)
            return
        coordinator = _get_coordinator(call)
        if not coordinator:
            return
        coordinator.delete_schedule_slot(slot)
        _LOGGER.info("remove_schedule_slot: cleared slot %d", slot)
        async_dispatcher_send(hass, f"{DOMAIN}_schedules_changed")

    async def handle_toggle_schedule_day(call: ServiceCall) -> None:
        """v0.38.0 — Flip a single weekday on/off for a slot."""
        slot = int(call.data.get("slot", 0))
        day = str(call.data.get("day", "")).lower()[:3]
        coordinator = _get_coordinator(call)
        if not coordinator:
            return
        coordinator.toggle_schedule_slot_day(slot, day)
        async_dispatcher_send(hass, f"{DOMAIN}_schedules_changed")

    async def handle_set_schedule_days(call: ServiceCall) -> None:
        """v0.38.0 — Replace a slot's weekday list with the supplied list."""
        slot = int(call.data.get("slot", 0))
        raw = call.data.get("days", [])
        if isinstance(raw, str):
            raw = [d.strip() for d in raw.split(",")]
        days = [str(d).lower()[:3] for d in (raw or [])]
        coordinator = _get_coordinator(call)
        if not coordinator:
            return
        coordinator.set_schedule_slot_days(slot, days)
        async_dispatcher_send(hass, f"{DOMAIN}_schedules_changed")

    hass.services.async_register(DOMAIN, "force_export", handle_force_export)
    hass.services.async_register(DOMAIN, "force_grid_charge", handle_force_grid_charge)
    hass.services.async_register(DOMAIN, "restore_normal", handle_restore_normal)
    hass.services.async_register(DOMAIN, "reset_learning", handle_reset_learning)
    hass.services.async_register(DOMAIN, "add_schedule_slot", handle_add_schedule_slot)
    hass.services.async_register(DOMAIN, "remove_schedule_slot", handle_remove_schedule_slot)
    hass.services.async_register(DOMAIN, "toggle_schedule_day", handle_toggle_schedule_day)
    hass.services.async_register(DOMAIN, "set_schedule_days", handle_set_schedule_days)

    async def handle_create_dashboard(call: ServiceCall) -> None:
        """v0.51.0 — create or refresh the bundled Solar AI dashboard.

        `force: true` overwrites an existing Solar AI dashboard with the
        bundled version (e.g. to pull in dashboard improvements after an
        update); otherwise an existing one is left untouched.
        """
        from .dashboard_setup import async_create_dashboard, async_check_dashboard_cards
        await async_create_dashboard(hass, force=bool(call.data.get("force", False)))
        await async_check_dashboard_cards(hass)

    hass.services.async_register(DOMAIN, "create_dashboard", handle_create_dashboard)

    async def handle_force_stop_charger(call: ServiceCall) -> None:
        """v0.37.0 — Force-stop a runaway OCPP session.

        Use when Solar AI has lost the transaction id (e.g. after multiple
        HA restarts) and the charger keeps drawing power despite the EV
        controller commanding 0 A. Sends `RemoteStopTransaction` against
        a list of candidate transaction ids until the charger accepts one:
            1) the user-supplied `transaction_id` if any
            2) the ChargePoint's own `session_transaction_id` if tracked
            3) the well-known fallback values 1 and 0 (most chargers stop
               the only active transaction regardless of the id supplied)

        Targets all connected chargers unless `charger_id` is given.
        Returns nothing — check `sensor.solar_ai_lader_status` to see
        whether the charger transitioned out of `Charging`.
        """
        coordinator = _get_coordinator(call)
        if not coordinator or not getattr(coordinator, "ocpp_server", None):
            _LOGGER.warning("force_stop_charger: no OCPP server running")
            return
        server = coordinator.ocpp_server
        target_id = (call.data.get("charger_id") or "").strip()
        custom_tx = call.data.get("transaction_id")
        try:
            custom_tx = int(custom_tx) if custom_tx is not None else None
        except (TypeError, ValueError):
            custom_tx = None

        chargers = [(cid, cp) for cid, cp in server.charge_points.items()
                    if not target_id or cid == target_id]
        if not chargers:
            _LOGGER.warning(
                "force_stop_charger: no connected chargers (target=%r)", target_id or "any"
            )
            return

        for cid, cp in chargers:
            tried: list[int] = []
            for tx in (custom_tx, getattr(cp, "session_transaction_id", None), 1, 0):
                if tx is None or tx in tried:
                    continue
                tried.append(tx)
                try:
                    ok = await cp.remote_stop_transaction(int(tx))
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "force_stop_charger %s: tx=%s raised %s", cid, tx, err,
                    )
                    continue
                _LOGGER.info(
                    "force_stop_charger %s: RemoteStopTransaction(tx=%s) accepted=%s",
                    cid, tx, ok,
                )
                if ok:
                    break

    hass.services.async_register(DOMAIN, "force_stop_charger", handle_force_stop_charger)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Battery Arbitrage config entry — restore HA to normal state."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Stop the EV control loop first (so it doesn't keep firing while we
    # restore the inverter and tear platforms down).
    await coordinator.async_stop_ev_control_loop()

    # Release the house-battery lock if it's currently engaged (v0.27.2).
    # Otherwise a restart mid-FULL-mode-charge would leave the battery
    # permanently locked from discharging.
    if coordinator._ev_battery_locked:
        try:
            await coordinator._set_battery_lock(False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Battery unlock on unload failed: %s", err)

    # Stop the embedded OCPP server (v0.27.0) — releases the port so a
    # subsequent reload can bind it again.
    if coordinator.ocpp_server is not None:
        try:
            await coordinator.ocpp_server.stop()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Embedded OCPP server stop failed: %s", err)
        coordinator.ocpp_server = None

    # Restore the legacy automation and inverter/EVCC before unloading
    await coordinator.async_restore_legacy_automation()
    await coordinator.async_restore_normal()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove stored data when integration is deleted."""
    from homeassistant.helpers.storage import Store
    from .const import STORAGE_KEY, STORAGE_VERSION

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    await store.async_remove()
    _LOGGER.info("Battery Arbitrage: storage cleaned up")


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry option updates."""
    await hass.config_entries.async_reload(entry.entry_id)
