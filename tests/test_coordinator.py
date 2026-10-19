"""Tests for setup and the Norish coordinator."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.norish.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import ENTITY_ID, STORE_REWE, FakeNorish


async def _tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int
) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == "0"
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.down = True
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.auth_ok = False
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_polling_and_store_cache(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_norish: FakeNorish,
    freezer: FrozenDateTimeFactory,
) -> None:
    assert mock_norish.count("GET", "/groceries") == 1
    assert mock_norish.count("GET", "/stores") == 1

    mock_norish.add("Milch")
    await _tick(hass, freezer, 60)
    assert hass.states.get(ENTITY_ID).state == "1"
    assert mock_norish.count("GET", "/groceries") == 2
    # Stores are cached between polls.
    assert mock_norish.count("GET", "/stores") == 1

    for _ in range(15):
        await _tick(hass, freezer, 60)
    assert mock_norish.count("GET", "/stores") == 2


async def test_unknown_store_triggers_store_refresh(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_norish: FakeNorish,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_norish.stores.append({"id": "new-store", "name": "Migros"})
    mock_norish.add("Brot", storeId="new-store")
    await _tick(hass, freezer, 60)
    assert mock_norish.count("GET", "/stores") == 2
    assert "new-store" in init_integration.runtime_data.data.stores
    # Known stores do not cause further requests.
    await _tick(hass, freezer, 60)
    assert mock_norish.count("GET", "/stores") == 2


async def test_store_failure_is_not_fatal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_norish: FakeNorish,
) -> None:
    mock_norish.stores = "broken"  # type: ignore[assignment]
    mock_norish.add("Milch", storeId=STORE_REWE)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert hass.states.get(ENTITY_ID).state == "1"


async def test_connection_loss_makes_entity_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_norish: FakeNorish,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_norish.down = True
    await _tick(hass, freezer, 60)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    mock_norish.down = False
    await _tick(hass, freezer, 60)
    assert hass.states.get(ENTITY_ID).state == "0"


async def test_auth_failure_during_poll_starts_reauth(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_norish: FakeNorish,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_norish.auth_ok = False
    await _tick(hass, freezer, 60)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
