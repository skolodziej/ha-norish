"""Tests for Norish unit short forms."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.norish.units import short_unit
from homeassistant.core import HomeAssistant

from .conftest import STORE_REWE, FakeNorish
from .test_todo import _get_items, _setup


@pytest.mark.parametrize(
    ("unit", "language", "expected"),
    [
        ("gram", "de", "g"),
        ("gram", "en", "g"),
        ("kilogram", "de", "kg"),
        ("milliliter", "de", "ml"),
        ("liter", "en", "l"),
        ("teaspoon", "de", "TL"),
        ("teaspoon", "en", "tsp"),
        ("tablespoon", "de-CH", "EL"),
        ("tablespoon", "en-GB", "tbsp"),
        ("heaping_tablespoon", "de", "geh. EL"),
        ("pinch", "de", "Prise"),
        ("piece", "de", "Stk."),
        ("Gram", "de", "g"),
        ("teaspoon", "fr", "tsp"),
        ("Becher XL", "de", "Becher XL"),
        ("g", "de", "g"),
    ],
)
def test_short_unit(unit: str, language: str, expected: str) -> None:
    assert short_unit(unit, language) == expected


@pytest.mark.parametrize(
    ("language", "entity_id", "expected"),
    [
        (
            "de",
            "todo.norish_einkaufsliste",
            ["500 g", "2 EL · Rewe", "1 Stk.", "3 Becher XL"],
        ),
        (
            "en",
            "todo.norish_shopping_list",
            ["500 g", "2 tbsp · Rewe", "1 piece", "3 Becher XL"],
        ),
    ],
)
async def test_descriptions_use_short_units(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_norish: FakeNorish,
    language: str,
    entity_id: str,
    expected: list[str],
) -> None:
    hass.config.language = language
    mock_norish.add("Mehl", amount=500, unit="gram")
    mock_norish.add("Öl", amount=2, unit="tablespoon", storeId=STORE_REWE)
    mock_norish.add("Zwiebel", amount=1, unit="piece")
    mock_norish.add("Joghurt", amount=3, unit="Becher XL")
    await _setup(hass, config_entry)
    assert [i["description"] for i in await _get_items(hass, entity_id)] == expected


async def test_status_update_with_short_unit_description(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    """The shortened description must not be mistaken for an edit."""
    from homeassistant.components.todo import (
        ATTR_ITEM,
        ATTR_STATUS,
        DOMAIN as TODO_DOMAIN,
        TodoServices,
    )
    from homeassistant.const import ATTR_ENTITY_ID

    hass.config.language = "de"
    item = mock_norish.add("Mehl", amount=500, unit="gram")
    await _setup(hass, config_entry)
    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ITEM: "Mehl", ATTR_STATUS: "completed"},
        target={ATTR_ENTITY_ID: "todo.norish_einkaufsliste"},
        blocking=True,
    )
    assert mock_norish.groceries[item["id"]]["isDone"] is True
