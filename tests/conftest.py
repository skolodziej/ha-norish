"""Fixtures for Norish tests: an in-memory fake of the Norish API."""

from __future__ import annotations

from http import HTTPStatus
import re
from typing import Any
import uuid

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.norish.const import DOMAIN
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant

BASE_URL = "https://norish.test"
API_KEY = "test-key-123"
ENTITY_ID = "todo.norish_shopping_list"
STORE_REWE = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


class FakeNorish:
    """Stateful fake Norish server with optimistic locking."""

    def __init__(self) -> None:
        self.groceries: dict[str, dict[str, Any]] = {}
        self.stores: list[dict[str, Any]] = [{"id": STORE_REWE, "name": "Rewe"}]
        self.auth_ok = True
        self.down = False
        self.healthy = True
        self.fail_status: HTTPStatus | None = None
        # Bump the version before each versioned write (simulates a
        # concurrent change). Number of remaining bumps.
        self.concurrent_changes = 0
        # Item ids that get a concurrent change before every versioned write.
        self.always_stale: set[str] = set()
        self.create_returns_object = True
        self.requests: list[tuple[str, str]] = []

    def add(self, name: str, **fields: Any) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "name": name,
            "amount": None,
            "unit": None,
            "isDone": False,
            "version": 1,
            "storeId": None,
            "sortOrder": len(self.groceries),
            "recipeIngredientId": None,
            "recurringGroceryId": None,
            "ingredientId": None,
            "purchaseAmount": None,
        }
        item.update(fields)
        self.groceries[item["id"]] = item
        return item

    def count(self, method: str, path: str) -> int:
        return sum(1 for m, p in self.requests if m == method and p == path)

    @staticmethod
    def _resp(
        method: str, url: URL, data: Any, status: int = HTTPStatus.OK
    ) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse(method, url, status=status, json=data)

    async def handle(
        self, method: str, url: URL, data: Any
    ) -> AiohttpClientMockResponse:
        method = method.upper()
        path = url.path.removeprefix("/api/v1")
        self.requests.append((method, re.sub(r"/[0-9a-f-]{36}", "/{id}", path)))
        if self.down:
            from aiohttp import ClientConnectionError

            return AiohttpClientMockResponse(
                method, url, exc=ClientConnectionError("down")
            )
        if path != "/health" and not self.auth_ok:
            return self._resp(
                method, url, {"code": "UNAUTHORIZED"}, HTTPStatus.UNAUTHORIZED
            )
        if self.fail_status:
            return self._resp(method, url, {"error": "x"}, self.fail_status)

        if method == "GET" and path == "/health":
            if not self.healthy:
                return self._resp(
                    method,
                    url,
                    {"status": "error"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            return self._resp(method, url, {"status": "ok"})
        if method == "GET" and path == "/groceries":
            return self._resp(method, url, list(self.groceries.values()))
        if method == "GET" and path == "/stores":
            return self._resp(method, url, self.stores)
        if method == "POST" and path == "/groceries":
            assert set(data) >= {"name", "amount", "unit"}
            item = self.add(
                data["name"],
                amount=data["amount"],
                unit=data["unit"],
                isDone=data.get("isDone", False),
                storeId=data.get("storeId"),
            )
            return self._resp(
                method, url, item if self.create_returns_object else {"ok": True}
            )

        if match := re.fullmatch(r"/groceries/([^/]+)(?:/(done|undone))?", path):
            grocery_id, action = match.groups()
            item = self.groceries.get(grocery_id)
            if item is None:
                return self._resp(method, url, {"error": "nf"}, HTTPStatus.NOT_FOUND)
            if self.concurrent_changes or grocery_id in self.always_stale:
                self.concurrent_changes = max(self.concurrent_changes - 1, 0)
                item["version"] += 1
            if method == "PATCH" and action:
                if data["version"] != item["version"]:
                    return self._resp(method, url, {"grocery": item, "stale": True})
                item["isDone"] = action == "done"
                item["version"] += 1
                return self._resp(method, url, {"grocery": item, "stale": False})
            if method == "DELETE" and not action:
                if int(url.query["version"]) != item["version"]:
                    return self._resp(method, url, {"success": False, "stale": True})
                del self.groceries[grocery_id]
                return self._resp(method, url, {"success": True, "stale": False})

        return self._resp(method, url, {"error": "route"}, HTTPStatus.NOT_FOUND)


@pytest.fixture
def fake() -> FakeNorish:
    return FakeNorish()


@pytest.fixture
def mock_norish(aioclient_mock: AiohttpClientMocker, fake: FakeNorish) -> FakeNorish:
    pattern = re.compile(rf"^{re.escape(BASE_URL)}/api/v1/")
    for method in ("get", "post", "patch", "delete"):
        aioclient_mock.request(method, pattern, side_effect=fake.handle)
    return fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="norish.test",
        unique_id=BASE_URL,
        data={CONF_URL: BASE_URL, CONF_API_KEY: API_KEY},
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_norish: FakeNorish
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
