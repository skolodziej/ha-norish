"""Tests for the Norish todo entity."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.norish.const import CONF_SHOW_STORE, DOMAIN
from homeassistant.components.todo import (
    ATTR_DESCRIPTION,
    ATTR_ITEM,
    ATTR_RENAME,
    ATTR_STATUS,
    DOMAIN as TODO_DOMAIN,
    TodoItem,
    TodoServices,
)
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import ENTITY_ID, STORE_REWE, FakeNorish


async def _get_items(
    hass: HomeAssistant, entity_id: str = ENTITY_ID
) -> list[dict[str, Any]]:
    result = await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.GET_ITEMS,
        {},
        target={ATTR_ENTITY_ID: entity_id},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["items"]


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any]) -> None:
    await hass.services.async_call(
        TODO_DOMAIN, service, data, target={ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entity_and_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    entry = entity_registry.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == f"{init_integration.entry_id}_groceries"
    assert entry.translation_key == "groceries"
    state = hass.states.get(ENTITY_ID)
    assert state.attributes["friendly_name"] == "Norish Shopping list"


@pytest.mark.parametrize(
    ("fields", "show_store", "description"),
    [
        ({"amount": 200, "unit": "g"}, True, "200 g"),
        ({"amount": 200, "unit": "g", "storeId": STORE_REWE}, True, "200 g · Rewe"),
        ({"amount": 200, "unit": "g", "storeId": STORE_REWE}, False, "200 g"),
        ({"amount": 2}, True, "2"),
        ({"amount": 0.5, "unit": "l"}, True, "0.5 l"),
        ({"amount": "1.50", "unit": "kg"}, True, "1.5 kg"),
        ({"unit": "Prise"}, True, "Prise"),
        ({"storeId": STORE_REWE}, True, "Rewe"),
        ({"storeId": STORE_REWE}, False, None),
        ({"storeId": "unknown-store"}, True, None),
        ({}, True, None),
    ],
)
async def test_mapping(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_norish: FakeNorish,
    fields: dict[str, Any],
    show_store: bool,
    description: str | None,
) -> None:
    item = mock_norish.add("Mehl", **fields)
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_SHOW_STORE: show_store}
    )
    await _setup(hass, config_entry)
    items = await _get_items(hass)
    expected: dict[str, Any] = {
        "uid": item["id"],
        "summary": "Mehl",
        "status": "needs_action",
    }
    if description:
        expected["description"] = description
    assert items == [expected]


async def test_status_and_order(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("C", sortOrder=2)
    mock_norish.add("A", sortOrder=0, isDone=True)
    mock_norish.add("X", sortOrder=None)
    mock_norish.add("B", sortOrder=1)
    await _setup(hass, config_entry)
    items = await _get_items(hass)
    assert [i["summary"] for i in items] == ["A", "B", "C", "X"]
    assert items[0]["status"] == "completed"
    assert hass.states.get(ENTITY_ID).state == "3"


async def test_get_items_directly_after_add_item(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    """The new item must be visible without waiting for the next poll."""
    polls = mock_norish.count("GET", "/groceries")
    await _call(hass, TodoServices.ADD_ITEM, {ATTR_ITEM: "Eier"})
    items = await _get_items(hass)
    assert [i["summary"] for i in items] == ["Eier"]
    (created,) = mock_norish.groceries.values()
    assert items[0]["uid"] == created["id"]
    assert created["amount"] is None
    assert created["unit"] is None
    assert hass.states.get(ENTITY_ID).state == "1"
    # Taken from the POST response, no extra reload needed.
    assert mock_norish.count("GET", "/groceries") == polls

    await _call(hass, TodoServices.ADD_ITEM, {ATTR_ITEM: "Butter"})
    assert [i["summary"] for i in await _get_items(hass)] == ["Eier", "Butter"]


async def test_add_item_without_object_in_response_reloads(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.create_returns_object = False
    polls = mock_norish.count("GET", "/groceries")
    await _call(hass, TodoServices.ADD_ITEM, {ATTR_ITEM: "Eier"})
    assert [i["summary"] for i in await _get_items(hass)] == ["Eier"]
    assert mock_norish.count("GET", "/groceries") == polls + 1


async def test_add_empty_item(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    entity = hass.data["todo"].get_entity(ENTITY_ID)
    with pytest.raises(ServiceValidationError) as exc_info:
        await entity.async_create_todo_item(TodoItem(summary="   "))
    assert exc_info.value.translation_key == "empty_name"


async def test_check_and_uncheck(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    item = mock_norish.add("Milch", amount=1, unit="l")
    await _setup(hass, config_entry)

    await _call(
        hass, TodoServices.UPDATE_ITEM, {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"}
    )
    assert mock_norish.groceries[item["id"]]["isDone"] is True
    assert (await _get_items(hass))[0]["status"] == "completed"
    assert hass.states.get(ENTITY_ID).state == "0"

    await _call(
        hass,
        TodoServices.UPDATE_ITEM,
        {ATTR_ITEM: item["id"], ATTR_STATUS: "needs_action"},
    )
    assert mock_norish.groceries[item["id"]]["isDone"] is False
    assert (await _get_items(hass))[0]["status"] == "needs_action"
    assert mock_norish.count("PATCH", "/groceries/{id}/done") == 1
    assert mock_norish.count("PATCH", "/groceries/{id}/undone") == 1


async def test_check_unchanged_status_is_noop(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("Milch", isDone=True)
    await _setup(hass, config_entry)
    await _call(
        hass, TodoServices.UPDATE_ITEM, {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"}
    )
    assert mock_norish.count("PATCH", "/groceries/{id}/done") == 0


async def test_check_stale_retry(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    item = mock_norish.add("Milch")
    await _setup(hass, config_entry)
    polls = mock_norish.count("GET", "/groceries")

    mock_norish.concurrent_changes = 1
    await _call(
        hass, TodoServices.UPDATE_ITEM, {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"}
    )
    assert mock_norish.count("PATCH", "/groceries/{id}/done") == 2
    assert mock_norish.count("GET", "/groceries") == polls + 1
    assert mock_norish.groceries[item["id"]]["isDone"] is True
    assert (await _get_items(hass))[0]["status"] == "completed"


async def test_check_stale_after_reload_already_done(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    """Someone else checked the item meanwhile: no second write needed."""
    item = mock_norish.add("Milch")
    await _setup(hass, config_entry)
    mock_norish.groceries[item["id"]].update(isDone=True, version=5)
    await _call(
        hass, TodoServices.UPDATE_ITEM, {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"}
    )
    assert mock_norish.count("PATCH", "/groceries/{id}/done") == 1
    assert (await _get_items(hass))[0]["status"] == "completed"


async def test_check_stale_twice_fails(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("Milch")
    await _setup(hass, config_entry)
    mock_norish.concurrent_changes = 2
    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(
            hass,
            TodoServices.UPDATE_ITEM,
            {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"},
        )
    assert exc_info.value.translation_key == "stale_version"
    assert mock_norish.count("PATCH", "/groceries/{id}/done") == 2


async def test_check_item_deleted_in_norish(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    item = mock_norish.add("Milch")
    await _setup(hass, config_entry)
    del mock_norish.groceries[item["id"]]
    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(
            hass,
            TodoServices.UPDATE_ITEM,
            {ATTR_ITEM: "Milch", ATTR_STATUS: "completed"},
        )
    assert exc_info.value.translation_key == "item_not_found"
    assert await _get_items(hass) == []


async def test_rename_not_supported(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("Milch")
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(
            hass, TodoServices.UPDATE_ITEM, {ATTR_ITEM: "Milch", ATTR_RENAME: "Hafer"}
        )
    assert exc_info.value.translation_key == "rename_not_supported"
    assert mock_norish.requests[-1][0] == "GET"


async def test_description_not_supported(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("Milch", amount=1, unit="l")
    await _setup(hass, config_entry)
    # The feature is not advertised, so HA itself rejects the service field.
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            TodoServices.UPDATE_ITEM,
            {ATTR_ITEM: "Milch", ATTR_DESCRIPTION: "2 l"},
        )
    # The entity also rejects changed descriptions (e.g. from the frontend).
    entity = hass.data["todo"].get_entity(ENTITY_ID)
    current = entity.todo_items[0]
    current.description = "2 l"
    with pytest.raises(ServiceValidationError) as exc_info:
        await entity.async_update_todo_item(current)
    assert exc_info.value.translation_key == "description_not_supported"


async def test_delete_multiple(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    a = mock_norish.add("A")
    mock_norish.add("B")
    c = mock_norish.add("C")
    await _setup(hass, config_entry)
    await _call(hass, TodoServices.REMOVE_ITEM, {ATTR_ITEM: [a["id"], "C"]})
    assert [i["summary"] for i in await _get_items(hass)] == ["B"]
    assert a["id"] not in mock_norish.groceries
    assert c["id"] not in mock_norish.groceries
    assert mock_norish.count("DELETE", "/groceries/{id}") == 2


async def test_delete_stale_retry(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    a = mock_norish.add("A")
    await _setup(hass, config_entry)
    mock_norish.concurrent_changes = 1
    await _call(hass, TodoServices.REMOVE_ITEM, {ATTR_ITEM: "A"})
    assert a["id"] not in mock_norish.groceries
    assert mock_norish.count("DELETE", "/groceries/{id}") == 2
    assert await _get_items(hass) == []


async def test_delete_stale_twice_keeps_consistent_state(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.add("A")
    b = mock_norish.add("B")
    await _setup(hass, config_entry)
    # A is deleted, B conflicts on every attempt.
    mock_norish.always_stale.add(b["id"])
    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, TodoServices.REMOVE_ITEM, {ATTR_ITEM: ["A", "B"]})
    assert exc_info.value.translation_key == "stale_version"
    assert [i["summary"] for i in await _get_items(hass)] == ["B"]


async def test_delete_already_gone(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    a = mock_norish.add("A")
    await _setup(hass, config_entry)
    del mock_norish.groceries[a["id"]]
    await _call(hass, TodoServices.REMOVE_ITEM, {ATTR_ITEM: "A"})
    assert await _get_items(hass) == []


async def test_write_connection_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.down = True
    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, TodoServices.ADD_ITEM, {ATTR_ITEM: "Eier"})
    assert exc_info.value.translation_key == "cannot_connect"


async def test_write_auth_error_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    mock_norish.auth_ok = False
    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, TodoServices.ADD_ITEM, {ATTR_ITEM: "Eier"})
    assert exc_info.value.translation_key == "invalid_auth"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
