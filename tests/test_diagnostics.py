"""Tests for Norish diagnostics."""

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.norish.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant

from .conftest import API_KEY, FakeNorish


async def test_diagnostics_redacted(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    dumped = json.dumps(diag)
    assert API_KEY not in dumped
    assert "norish.test" not in dumped
    assert diag["entry"]["data"] == {"url": "**REDACTED**", "api_key": "**REDACTED**"}
    assert diag["last_update_success"] is True
    assert diag["stores"] == [{"id": mock_norish.stores[0]["id"], "name": "Rewe"}]
