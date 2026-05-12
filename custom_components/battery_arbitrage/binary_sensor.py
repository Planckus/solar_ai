"""Binary sensor platform for Battery Arbitrage."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BatteryArbitrageCoordinator
from .sensor import _device_info


@dataclass(frozen=True, kw_only=True)
class BatteryArbitrageBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value extractor."""

    value_fn: Callable[[dict[str, Any]], bool | None] = lambda _: None


BINARY_SENSORS: tuple[BatteryArbitrageBinarySensorDescription, ...] = (
    BatteryArbitrageBinarySensorDescription(
        key="should_export",
        translation_key="should_export",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:transmission-tower-export",
        value_fn=lambda d: d.get("should_export", False),
    ),
    BatteryArbitrageBinarySensorDescription(
        key="should_grid_charge",
        translation_key="should_grid_charge",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:transmission-tower-import",
        value_fn=lambda d: d.get("should_grid_charge", False),
    ),
    BatteryArbitrageBinarySensorDescription(
        key="vacation_mode",
        translation_key="vacation_mode",
        device_class=BinarySensorDeviceClass.PRESENCE,
        icon="mdi:airplane",
        # Inverted: presence = False means away/vacation
        value_fn=lambda d: not d.get("vacation_mode", False),
    ),
    BatteryArbitrageBinarySensorDescription(
        key="solar_will_fill",
        translation_key="solar_will_fill",
        icon="mdi:solar-power",
        value_fn=lambda d: d.get("solar_will_fill", False),
    ),
    BatteryArbitrageBinarySensorDescription(
        key="ev_connected",
        translation_key="ev_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:ev-plug-type2",
        value_fn=lambda d: d.get("ev_connected", False),
    ),
    BatteryArbitrageBinarySensorDescription(
        key="ev_charging_now",
        translation_key="ev_charging_now",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:car-electric",
        value_fn=lambda d: d.get("ev_charging_now", False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Arbitrage binary sensors."""
    coordinator: BatteryArbitrageCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        BatteryArbitrageBinarySensor(coordinator, entry, desc)
        for desc in BINARY_SENSORS
    )


class BatteryArbitrageBinarySensor(
    CoordinatorEntity[BatteryArbitrageCoordinator], BinarySensorEntity
):
    """A single Battery Arbitrage binary sensor."""

    entity_description: BatteryArbitrageBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatteryArbitrageCoordinator,
        entry: ConfigEntry,
        description: BatteryArbitrageBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
