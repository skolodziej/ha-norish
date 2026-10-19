"""Base entity for Norish."""

from __future__ import annotations

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NorishDataUpdateCoordinator


class NorishEntity(CoordinatorEntity[NorishDataUpdateCoordinator]):
    """Common attributes of Norish entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NorishDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            translation_key="norish",
            manufacturer="Norish",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data[CONF_URL],
        )
