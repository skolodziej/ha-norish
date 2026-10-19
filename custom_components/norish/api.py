"""Minimal async client for the Norish REST API (v1)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL

from homeassistant.util.json import json_loads

from .const import LOGGER

API_PATH = "/api/v1"
REQUEST_TIMEOUT = ClientTimeout(total=15)


class NorishError(Exception):
    """Base error for the Norish API."""


class NorishConnectionError(NorishError):
    """The Norish instance could not be reached."""


class NorishAuthError(NorishError):
    """The API key was rejected."""


class NorishNotFoundError(NorishError):
    """The requested resource does not exist."""


class NorishResponseError(NorishError):
    """The Norish instance returned an unexpected response."""


def normalize_url(url: str) -> str:
    """Return the instance base URL without trailing slash or API path.

    Accepts e.g. ``rezepte.example.com``, ``https://rezepte.example.com/``
    or ``https://rezepte.example.com/api/v1/``.
    """
    url = url.strip()
    if not url:
        raise ValueError("empty url")
    if "://" not in url:
        url = f"https://{url}"
    parsed = URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise ValueError("invalid url")
    path = parsed.path.rstrip("/")
    if path.endswith(API_PATH):
        path = path[: -len(API_PATH)]
    return str(
        parsed.with_path(path or "/").with_query(None).with_fragment(None)
    ).rstrip("/")


def _parse_amount(value: Any) -> Decimal | str | None:
    """Parse an amount which the API may return as number or string."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text.replace(",", "."))
        except InvalidOperation:
            return text
    return None


def format_amount(amount: Decimal | str | None) -> str | None:
    """Format an amount without superfluous decimals, e.g. ``200`` or ``0.5``."""
    if amount is None:
        return None
    if isinstance(amount, str):
        return amount
    if not amount.is_finite():
        return None
    if amount == amount.to_integral_value():
        return str(int(amount))
    return format(amount.normalize(), "f")


@dataclass(frozen=True, slots=True)
class Grocery:
    """A grocery item on the shopping list."""

    id: str
    name: str
    amount: Decimal | str | None
    unit: str | None
    is_done: bool
    version: int
    sort_order: int | None
    store_id: str | None
    recipe_ingredient_id: str | None
    recurring_grocery_id: str | None

    @classmethod
    def from_dict(cls, data: Any) -> Grocery:
        """Create a grocery from an API response object."""
        if not isinstance(data, dict):
            raise NorishResponseError("Grocery is not an object")
        try:
            grocery_id = str(data["id"])
            version = int(data["version"])
        except (KeyError, TypeError, ValueError) as err:
            raise NorishResponseError("Grocery without id or version") from err
        sort_order = data.get("sortOrder")
        unit = data.get("unit")
        return cls(
            id=grocery_id,
            name=str(data.get("name") or ""),
            amount=_parse_amount(data.get("amount")),
            unit=str(unit).strip() or None if unit is not None else None,
            is_done=bool(data.get("isDone")),
            version=version,
            sort_order=int(sort_order) if isinstance(sort_order, int | float) else None,
            store_id=data.get("storeId") or None,
            recipe_ingredient_id=data.get("recipeIngredientId"),
            recurring_grocery_id=data.get("recurringGroceryId"),
        )


@dataclass(frozen=True, slots=True)
class Store:
    """A store groceries can be assigned to."""

    id: str
    name: str

    @classmethod
    def from_dict(cls, data: Any) -> Store:
        """Create a store from an API response object."""
        if not isinstance(data, dict) or "id" not in data:
            raise NorishResponseError("Store without id")
        return cls(id=str(data["id"]), name=str(data.get("name") or ""))


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Result of a versioned write operation."""

    stale: bool
    grocery: Grocery | None = None


class NorishClient:
    """Client for a single Norish instance."""

    def __init__(self, session: ClientSession, base_url: str, api_key: str) -> None:
        """Initialize the client with an already normalized base URL."""
        self._session = session
        self._api_url = URL(base_url) / "api" / "v1"
        self._api_key = api_key

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Any:
        """Perform a request and return the decoded JSON body."""
        url = self._api_url.joinpath(*path.strip("/").split("/"))
        headers = {"Accept": "application/json"}
        if auth:
            headers["x-api-key"] = self._api_key
        LOGGER.debug("Norish request %s %s", method, url.path)
        try:
            response = await self._session.request(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            status = response.status
            body = await response.read()
        except TimeoutError as err:
            raise NorishConnectionError("Timeout while connecting to Norish") from err
        except ClientError as err:
            raise NorishConnectionError(
                f"Error connecting to Norish: {type(err).__name__}"
            ) from err

        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            raise NorishAuthError(f"API key rejected (HTTP {status})")
        if status == HTTPStatus.NOT_FOUND:
            raise NorishNotFoundError(f"{url.path} not found")
        if status >= HTTPStatus.BAD_REQUEST:
            raise NorishResponseError(f"Unexpected HTTP status {status}")
        if not body:
            return None
        try:
            return json_loads(body)
        except ValueError as err:
            raise NorishResponseError("Response is not valid JSON") from err

    async def async_get_health(self) -> dict[str, Any]:
        """Return the public health status."""
        data = await self._request("GET", "health", auth=False)
        if not isinstance(data, dict):
            raise NorishResponseError("Unexpected health response")
        return data

    async def async_get_groceries(self) -> list[Grocery]:
        """Return all groceries."""
        data = await self._request("GET", "groceries")
        if not isinstance(data, list):
            raise NorishResponseError("Groceries response is not a list")
        return [Grocery.from_dict(item) for item in data]

    async def async_get_stores(self) -> list[Store]:
        """Return all stores."""
        data = await self._request("GET", "stores")
        if not isinstance(data, list):
            raise NorishResponseError("Stores response is not a list")
        return [Store.from_dict(item) for item in data]

    async def async_create_grocery(
        self,
        name: str,
        *,
        amount: float | None = None,
        unit: str | None = None,
        store_id: str | None = None,
    ) -> Grocery | None:
        """Create a grocery and return it, if the response contains it."""
        payload: dict[str, Any] = {"name": name, "amount": amount, "unit": unit}
        if store_id is not None:
            payload["storeId"] = store_id
        data = await self._request("POST", "groceries", json=payload)
        try:
            return Grocery.from_dict(data)
        except NorishResponseError:
            LOGGER.debug("Create response did not contain a grocery object")
            return None

    async def async_set_done(
        self, grocery_id: str, version: int, done: bool
    ) -> WriteResult:
        """Mark a grocery as done or not done."""
        action = "done" if done else "undone"
        data = await self._request(
            "PATCH", f"groceries/{grocery_id}/{action}", json={"version": version}
        )
        if not isinstance(data, dict):
            raise NorishResponseError("Unexpected response to status update")
        grocery: Grocery | None = None
        if isinstance(data.get("grocery"), dict):
            try:
                grocery = Grocery.from_dict(data["grocery"])
            except NorishResponseError:
                grocery = None
        return WriteResult(stale=bool(data.get("stale")), grocery=grocery)

    async def async_delete_grocery(self, grocery_id: str, version: int) -> WriteResult:
        """Delete a grocery."""
        data = await self._request(
            "DELETE", f"groceries/{grocery_id}", params={"version": str(version)}
        )
        if not isinstance(data, dict):
            raise NorishResponseError("Unexpected response to delete")
        stale = bool(data.get("stale"))
        if not stale and data.get("success") is False:
            raise NorishResponseError("Delete was not successful")
        return WriteResult(stale=stale)
