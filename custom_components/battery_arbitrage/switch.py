"""Switch platform for Battery Arbitrage — master enable/disable toggle."""
from __future__ import annotations

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
