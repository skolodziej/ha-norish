"""Tests for the Norish API client."""

from decimal import Decimal
from http import HTTPStatus

from aiohttp import ClientConnectionError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.norish.api import (
    Grocery,
    NorishAuthError,
    NorishClient,
    NorishConnectionError,
    NorishNotFoundError,
    NorishResponseError,
    format_amount,
    normalize_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import API_KEY, BASE_URL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://norish.test", "https://norish.test"),
        ("https://norish.test/", "https://norish.test"),
        ("https://norish.test/api/v1", "https://norish.test"),
        ("https://norish.test/api/v1/", "https://norish.test"),
        ("  HTTPS://Norish.Test/api/v1//  ", "https://norish.test"),
        ("norish.test", "https://norish.test"),
        ("http://192.168.1.5:3000/", "http://192.168.1.5:3000"),
        ("https://example.com/norish/api/v1", "https://example.com/norish"),
        ("https://norish.test/?x=1#y", "https://norish.test"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "ftp://norish.test", "https://"])
def test_normalize_url_invalid(raw: str) -> None:
    with pytest.raises(ValueError, match="url"):
        normalize_url(raw)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (None, None),
        (200, "200"),
        (200.0, "200"),
        (0.5, "0.5"),
        (1.25, "1.25"),
        ("2", "2"),
        ("2.50", "2.5"),
        ("1,5", "1.5"),
        ("", None),
        ("etwas", "etwas"),
        (1000000, "1000000"),
    ],
)
def test_amount_formatting(amount: object, expected: str | None) -> None:
    grocery = Grocery.from_dict(
        {"id": "a", "version": 1, "name": "x", "amount": amount}
    )
    assert format_amount(grocery.amount) == expected


def test_grocery_from_dict_invalid() -> None:
    with pytest.raises(NorishResponseError):
        Grocery.from_dict({"name": "no id"})
    with pytest.raises(NorishResponseError):
        Grocery.from_dict(["not", "a", "dict"])


def test_grocery_from_dict_full() -> None:
    grocery = Grocery.from_dict(
        {
            "id": "a",
            "name": "Milch",
            "amount": 1,
            "unit": " l ",
            "isDone": True,
            "version": 3,
            "storeId": "s",
            "sortOrder": 2,
            "recipeIngredientId": "r",
            "recurringGroceryId": None,
        }
    )
    assert grocery.amount == Decimal(1)
    assert grocery.unit == "l"
    assert grocery.is_done
    assert grocery.sort_order == 2


async def test_auth_header_and_health_without_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/groceries", json=[])
    aioclient_mock.get(f"{BASE_URL}/api/v1/health", json={"status": "ok"})
    client = NorishClient(async_get_clientsession(hass), BASE_URL, API_KEY)
    assert await client.async_get_groceries() == []
    assert await client.async_get_health() == {"status": "ok"}
    (_, _, _, groceries_headers), (_, _, _, health_headers) = aioclient_mock.mock_calls
    assert groceries_headers["x-api-key"] == API_KEY
    assert "x-api-key" not in health_headers


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": HTTPStatus.UNAUTHORIZED}, NorishAuthError),
        ({"status": HTTPStatus.FORBIDDEN}, NorishAuthError),
        ({"status": HTTPStatus.NOT_FOUND}, NorishNotFoundError),
        ({"status": HTTPStatus.INTERNAL_SERVER_ERROR}, NorishResponseError),
        ({"text": "<html>login</html>"}, NorishResponseError),
        ({"json": {"not": "a list"}}, NorishResponseError),
        ({"exc": ClientConnectionError()}, NorishConnectionError),
        ({"exc": TimeoutError()}, NorishConnectionError),
    ],
)
async def test_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    error: type[Exception],
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/v1/groceries", **kwargs)
    client = NorishClient(async_get_clientsession(hass), BASE_URL, API_KEY)
    with pytest.raises(error) as exc_info:
        await client.async_get_groceries()
    assert API_KEY not in str(exc_info.value)


async def test_delete_sends_version(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.delete(
        f"{BASE_URL}/api/v1/groceries/abc?version=7",
        json={"success": True, "stale": False},
    )
    client = NorishClient(async_get_clientsession(hass), BASE_URL, API_KEY)
    result = await client.async_delete_grocery("abc", 7)
    assert not result.stale
    assert aioclient_mock.mock_calls[0][1].query["version"] == "7"
