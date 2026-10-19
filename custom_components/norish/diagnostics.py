"""Diagnostics for Norish."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import NorishConfigEntry

TO_REDACT = {CONF_API_KEY, CONF_URL, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NorishConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "update_interval": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
        "groceries": [
            {**asdict(g), "amount": None if g.amount is None else str(g.amount)}
            for g in data.groceries
        ],
        "stores": [asdict(s) for s in data.stores.values()],
    }
