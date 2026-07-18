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
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[BatteryArbitrageBinarySensorDescription, ...] = (
    BatteryArbitrageBinarySensorDescription(
        key="should_export",
        translation_key="should_export",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:transmission-tower-export",
        value_fn=lambda d: d.get("should_export", False),
    ),
    # v0.39.2 — Solar export stop (price-floor block) live indicator.
    # Backs the EV/OCPP tab chip that lets the user see at a glance that
    # the inverter is currently clipping PV because the live export
    # price is at or below their configured min_export_price.
    BatteryArbitrageBinarySensorDescription(
        key="export_stop_active",
        translation_key="export_stop_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:transmission-tower-off",
        value_fn=lambda d: d.get("export_stop_active", False),
        attr_fn=lambda d: {
            "since": d.get("export_stop_start_ts"),
            "floor": d.get("export_stop_floor"),
            "price_at_start": d.get("export_stop_price_at_start"),
        },
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
        attr_fn=lambda d: {"charge_kw": f"{round(d.get('ev_charge_power_w', 0) / 1000, 1)} kW" if d.get("ev_charging_now") else "—"},
    ),
    BatteryArbitrageBinarySensorDescription(
        key="ev_charging_solar",
        translation_key="ev_charging_solar",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:solar-power",
        value_fn=lambda d: d.get("ev_charging_solar", False),
        attr_fn=lambda d: {"charge_kw": f"{round(d.get('ev_charge_power_w', 0) / 1000, 1)} kW" if d.get("ev_charging_solar") else "—"},
    ),
    # v0.49.0 — low disk-space alarm (trips below the configured % free)
    BatteryArbitrageBinarySensorDescription(
        key="disk_low",
        translation_key="disk_low",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:harddisk-remove",
        value_fn=lambda d: d.get("disk_low", False),
        attr_fn=lambda d: {
            "pct_free": d.get("disk_pct_free"),
            "free_gb": d.get("disk_free_gb"),
            "threshold_pct": d.get("disk_alarm_threshold_pct"),
            "path": d.get("disk_path"),
        },
    ),
    # v0.59.19 — price-feed health. On = degraded (too few price slots, or the
    # last fetch produced no rates); arbitrage pauses on self-consumption until
    # it recovers.
    BatteryArbitrageBinarySensorDescription(
        key="price_data_degraded",
        translation_key="price_data_degraded",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:database-alert",
        value_fn=lambda d: d.get("price_data_degraded", False),
        attr_fn=lambda d: {
            "price_slots": d.get("price_slots_count"),
            "last_good_fetch": d.get("price_last_good_iso"),
        },
    ),
    # v0.64.0 — Tier-1 model-health monitor. On = a learned model has drifted,
    # pinned at a safety clamp, or its predictions are persistently wrong. The
    # `issues` attribute lists what and why. Detection only — no model is changed.
    # v0.75.13 — `notes` is a second, non-alarming list: conditions worth
    # surfacing but that don't flip this sensor on (e.g. the reserve factor
    # pinned at its MINIMUM, which doesn't mean the same thing as pinning at
    # its maximum).
    BatteryArbitrageBinarySensorDescription(
        key="model_health",
        translation_key="model_health",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:brain",
        value_fn=lambda d: not d.get("model_health_ok", True),
        attr_fn=lambda d: {
            "issues": d.get("model_health_issues") or ["none"],
            "notes": d.get("model_health_notes") or ["none"],
        },
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None or self.coordinator.data is None:
            return None
        return self.entity_description.attr_fn(self.coordinator.data)
