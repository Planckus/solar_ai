"""Switch platform for Battery Arbitrage — master enable/disable toggle."""
from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN, EV_SCHEDULE_DAYS, EV_SCHEDULE_DEFAULT_DAYS, EV_SCHEDULES_MAX,
    CONF_OCPP_EMBEDDED, DEFAULT_OCPP_EMBEDDED,
)
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


_NOTIFY_SWITCHES = [
    # (translation_key, stored_key, icon)
    ("notify_export_start",        "notify_export_start",        "mdi:export"),
    ("notify_export_stop",         "notify_export_stop",         "mdi:export-variant"),
    ("notify_charge_start",        "notify_charge_start",        "mdi:battery-charging-50"),
    ("notify_charge_stop",         "notify_charge_stop",         "mdi:battery-check"),
    ("notify_solar_floor_blocked", "notify_solar_floor_blocked", "mdi:solar-power-variant-outline"),
    ("notify_solar_floor_resumed", "notify_solar_floor_resumed", "mdi:solar-power-variant"),
    ("notify_disk_low",            "notify_disk_low",            "mdi:harddisk-remove"),
]


def _format_device_name(service: str) -> str:
    """Turn 'mobile_app_my_phone' into 'My Phone'."""
    return service.removeprefix("mobile_app_").replace("_", " ").title()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Arbitrage switches."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        BatteryArbitrageSwitch(coordinator, entry),
        BatteryArbitrageNotificationsSwitch(coordinator, entry),
        BatteryArbitragePriceResolutionSwitch(coordinator, entry),
    ]
    # Notification event-type toggles
    for trans_key, stored_key, icon in _NOTIFY_SWITCHES:
        entities.append(BatteryArbitrageNotifyEventSwitch(coordinator, entry, trans_key, stored_key, icon))
    # One toggle per discovered HA Companion mobile app
    notify_services = hass.services.async_services().get("notify", {})
    for svc_name in sorted(notify_services):
        if svc_name.startswith("mobile_app_"):
            full_service = f"notify.{svc_name}"
            friendly = _format_device_name(svc_name)
            entities.append(
                BatteryArbitrageNotifyTargetSwitch(coordinator, entry, full_service, friendly)
            )
    # v0.38.0 — one enabled-switch per EV schedule slot (always created
    # so the dashboard cards always have an entity to bind to).
    for idx in range(1, EV_SCHEDULES_MAX + 1):
        entities.append(BatteryArbitrageEvScheduleSlotEnabledSwitch(coordinator, entry, idx))
    # v0.50.0 — seven weekday toggles per schedule slot, so the active
    # weekdays of each charge plan are editable from the GUI (e.g. only
    # Mon/Tue/Fri). Backed by `_stored["ev_schedules"][slot].days`.
    for idx in range(1, EV_SCHEDULES_MAX + 1):
        for day in EV_SCHEDULE_DAYS:
            entities.append(BatteryArbitrageEvScheduleSlotDaySwitch(coordinator, entry, idx, day))
    # v0.39.0 — opt-in switch for auto-Full on negative buy price.
    entities.append(BatteryArbitrageAutoFullSwitch(coordinator, entry))
    # v0.47.0 — opt-in dynamic self-learning discharge floor.
    entities.append(BatteryArbitrageDynamicFloorSwitch(coordinator, entry))
    # v0.57.0 — embedded OCPP server on/off (Advanced pane). Reloads on change.
    entities.append(BatteryArbitrageOcppServerSwitch(coordinator, entry))
    # v0.59.20 — opt-in cross-source forecast fallback (Strømligning ↔ EDS).
    entities.append(BatteryArbitragePriceFallbackSwitch(coordinator, entry))
    async_add_entities(entities)


class BatteryArbitrageSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Master on/off switch for the arbitrage system.

    When turned off the coordinator still polls (so sensors stay fresh) but
    will NOT change work modes or EVCC battery mode.  Turning it off while
    exporting or grid-charging immediately restores normal operation.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:flash-auto"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_enabled"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.enabled = True
        # Re-disable the legacy automation when arbitrage is re-enabled
        await self.coordinator.async_disable_legacy_automation()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.enabled = False
        # Restore the legacy automation and inverter/EVCC to normal
        await self.coordinator.async_restore_legacy_automation()
        await self.coordinator.async_restore_normal()
        self.async_write_ha_state()


class BatteryArbitrageNotificationsSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle for HA persistent notifications on mode changes.

    When on, Solar AI fires a persistent notification whenever it transitions
    between Self-use / Exporting / Grid charging.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "notifications_enabled"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:bell-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_notifications_enabled"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("notifications_enabled", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["notifications_enabled"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["notifications_enabled"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitragePriceResolutionSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle between 15-minute and 1-hour price chart resolution.

    When on, the 24h price chart sensor emits one row per native DSO slot
    (typically 15 minutes).  When off (default) it emits one row per hour.
    The arbitrage model always uses native resolution internally regardless
    of this setting.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "price_resolution_15min"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_price_resolution_15min"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("price_resolution_15min", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["price_resolution_15min"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["price_resolution_15min"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitragePriceFallbackSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Opt-in cross-source price-forecast fallback (v0.59.20).

    When on, and Energi Data Service returns no day-ahead prices, the forecast
    is derived from the cached Strømligning prices (their spot component) so the
    chart and optimiser don't go blind during an EDS gap. Off by default —
    single-source users are unaffected. Only meaningful when the buy-price mode
    is Strømligning (otherwise there's no Strømligning cache to fall back to).
    """

    _attr_has_entity_name = True
    _attr_translation_key = "price_cross_source_fallback"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:swap-horizontal-bold"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_price_cross_source_fallback"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("price_cross_source_fallback", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["price_cross_source_fallback"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["price_cross_source_fallback"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitrageOcppServerSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Enable/disable the embedded OCPP server (v0.57.0).

    The server is the generic, multi-brand charger path (Easee, Zaptec,
    Wallbox, any OCPP 1.6 unit) and binds a port at setup, so toggling it
    isn't a per-cycle setting — changing it reloads the integration, which
    starts or stops the server via the normal setup/unload path. Backed by
    `_stored[CONF_OCPP_EMBEDDED]` (overrides the config-entry value), read at
    setup via `coordinator._setting`.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "ocpp_embedded"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:server-network"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_ocpp_embedded"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._setting(CONF_OCPP_EMBEDDED, DEFAULT_OCPP_EMBEDDED))

    async def _set(self, value: bool) -> None:
        self.coordinator._stored[CONF_OCPP_EMBEDDED] = value
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()
        # Start/stop the server via a full reload. Scheduled as a task so this
        # service call finishes before the entry (and this entity) is torn down.
        if self.hass:
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self._entry.entry_id)
            )

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set(False)


class BatteryArbitrageNotifyEventSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle for a specific mobile push-notification event type.

    One instance is created for each of the four events:
    export start, export stop, charge start, charge stop.
    When on, Solar AI sends a push notification via notify.notify
    (all registered HA Companion mobile apps) when that event fires.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        translation_key: str,
        stored_key: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._stored_key = stored_key
        self._attr_unique_id = f"{entry.entry_id}_{stored_key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get(self._stored_key, False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored[self._stored_key] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored[self._stored_key] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitrageNotifyTargetSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Toggle for including a specific mobile device in push notifications.

    One instance is created per discovered notify.mobile_app_* service.
    When on, this device receives all enabled push notification types.
    The full service name (e.g. "notify.mobile_app_my_phone") is stored
    in the coordinator's notify_targets list.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:cellphone-message"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        full_service: str,
        friendly_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._full_service = full_service
        # Slug the service name for a stable unique ID
        slug = full_service.replace(".", "_")
        self._attr_unique_id = f"{entry.entry_id}_target_{slug}"
        self._attr_name = f"Notifikation: {friendly_name}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._full_service in self.coordinator._stored.get("notify_targets", [])

    async def async_turn_on(self, **kwargs: object) -> None:
        targets: list[str] = list(self.coordinator._stored.get("notify_targets", []))
        if self._full_service not in targets:
            targets.append(self._full_service)
        self.coordinator._stored["notify_targets"] = targets
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        targets = [t for t in self.coordinator._stored.get("notify_targets", []) if t != self._full_service]
        self.coordinator._stored["notify_targets"] = targets
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()



class BatteryArbitrageEvScheduleSlotEnabledSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """Per-slot enabled toggle for native EV schedules (v0.38.0).

    Backed by `_stored["ev_schedules"][slot].enabled`. When off, the
    slot is skipped by `_resolve_effective_ev_mode` even if its time
    window matches now. Lets the user pause a schedule without losing
    the day/time configuration. Toggling on a slot that does not yet
    exist creates it with default times so the switch always has
    something to write to.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-check"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        slot_idx: int,
    ) -> None:
        super().__init__(coordinator)
        self._slot_idx = slot_idx
        self._attr_translation_key = f"ev_schedule_slot_{slot_idx}_enabled"
        self._attr_unique_id = f"{entry.entry_id}_ev_schedule_slot_{slot_idx}_enabled"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_schedules_changed",
                self.async_write_ha_state,
            )
        )

    @property
    def is_on(self) -> bool:
        slot = self.coordinator.get_schedule_slot(self._slot_idx)
        return bool(slot and slot.get("enabled"))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.set_schedule_slot_enabled(self._slot_idx, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.set_schedule_slot_enabled(self._slot_idx, False)
        self.async_write_ha_state()


# Localised weekday names for the per-day toggle friendly names. The HA
# language at entity-creation time fixes the entity_id slug (Danish on a
# Danish install). Falls back to English.
_EV_DAY_NAMES = {
    "da": {"mon": "Mandag", "tue": "Tirsdag", "wed": "Onsdag", "thu": "Torsdag",
           "fri": "Fredag", "sat": "Lørdag", "sun": "Søndag"},
    "en": {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
           "fri": "Friday", "sat": "Saturday", "sun": "Sunday"},
}
_EV_SCHEDULE_PREFIX = {"da": "Skema", "en": "Schedule"}


class BatteryArbitrageEvScheduleSlotDaySwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """One weekday on/off toggle for a native EV schedule slot (v0.50.0).

    Seven instances per slot. When on, the slot's `days` list includes this
    weekday, so `_resolve_effective_ev_mode` activates the slot on that day.
    Lets the user pick arbitrary weekdays per charge plan (e.g. Mon/Tue/Fri)
    entirely from the GUI. Toggling a day on a slot that does not yet exist
    creates it with defaults so there is always something to write to.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-today"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        slot_idx: int,
        day: str,
    ) -> None:
        super().__init__(coordinator)
        self._slot_idx = slot_idx
        self._day = day
        lang = (getattr(coordinator.hass.config, "language", "en") or "en")[:2]
        names = _EV_DAY_NAMES.get(lang, _EV_DAY_NAMES["en"])
        prefix = _EV_SCHEDULE_PREFIX.get(lang, _EV_SCHEDULE_PREFIX["en"])
        # Name is unique per slot+day so the generated entity_id is stable.
        self._attr_name = f"{prefix} {slot_idx} {names[day]}"
        self._attr_unique_id = f"{entry.entry_id}_ev_schedule_slot_{slot_idx}_day_{day}"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{DOMAIN}_schedules_changed",
                self.async_write_ha_state,
            )
        )

    @property
    def is_on(self) -> bool:
        slot = self.coordinator.get_schedule_slot(self._slot_idx)
        if slot is None:
            # Unconfigured slot reports the default day set, so the toggles
            # show what would apply once the slot is first edited.
            return self._day in EV_SCHEDULE_DEFAULT_DAYS
        return self._day in (slot.get("days") or [])

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator.set_schedule_slot_day(self._slot_idx, self._day, True)
        async_dispatcher_send(self.hass, f"{DOMAIN}_schedules_changed")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator.set_schedule_slot_day(self._slot_idx, self._day, False)
        async_dispatcher_send(self.hass, f"{DOMAIN}_schedules_changed")
        self.async_write_ha_state()



class BatteryArbitrageAutoFullSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """v0.39.0 — Opt-in switch for auto-Full on negative buy price.

    When ON, the coordinator auto-promotes the EV master mode to Full
    whenever buy_price ≤ 0 for AUTO_FULL_DEBOUNCE_SECONDS (5 min) while
    the EV is plugged in. The previous mode is stashed and restored on
    the next floor-block-close edge.

    Manual mode changes clear the auto state (the user's choice wins).
    EV unplug clears the auto state. Default OFF — the feature is
    opt-in for backwards-compatible behaviour.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "auto_full_on_negative_price"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:cash-minus"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_auto_full_on_negative_price"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("auto_full_on_negative_price", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["auto_full_on_negative_price"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["auto_full_on_negative_price"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()


class BatteryArbitrageDynamicFloorSwitch(
    CoordinatorEntity[BatteryArbitrageCoordinator], SwitchEntity
):
    """v0.47.0 — Opt-in dynamic self-learning discharge floor.

    When ON, the export floor is computed each cycle as the SoC needed to run
    the house (projected load) until the next refill — sunrise solar or a cheap
    grid window — times a learned safety margin, instead of the fixed floor
    slider. The margin self-corrects daily from whether the reserve actually
    lasted. Default OFF — the static floor is used until enabled.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "dynamic_discharge_floor"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:battery-arrow-down-outline"

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_dynamic_discharge_floor"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator._stored.get("dynamic_discharge_floor", False))

    async def async_turn_on(self, **kwargs: object) -> None:
        self.coordinator._stored["dynamic_discharge_floor"] = True
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self.coordinator._stored["dynamic_discharge_floor"] = False
        await self.coordinator._store.async_save(self.coordinator._stored)
        self.async_write_ha_state()
