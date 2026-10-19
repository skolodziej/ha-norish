"""Data update coordinator for Norish."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Grocery,
    NorishAuthError,
    NorishClient,
    NorishConnectionError,
    NorishError,
    NorishNotFoundError,
    Store,
    WriteResult,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_SCAN_INTERVAL,
    STORES_MISSING_RETRY_INTERVAL,
    STORES_REFRESH_INTERVAL,
)

type NorishConfigEntry = ConfigEntry[NorishDataUpdateCoordinator]


@dataclass(slots=True)
class NorishData:
    """Snapshot of the shopping list."""

    groceries: list[Grocery] = field(default_factory=list)
    stores: dict[str, Store] = field(default_factory=dict)

    def get(self, grocery_id: str) -> Grocery | None:
        """Return the grocery with the given id."""
        return next((g for g in self.groceries if g.id == grocery_id), None)


def sort_groceries(groceries: list[Grocery]) -> list[Grocery]:
    """Sort groceries by sortOrder; items without sortOrder go last."""
    return sorted(
        groceries,
        key=lambda g: (g.sort_order is None, g.sort_order or 0),
    )


def _write_error(err: NorishError) -> HomeAssistantError:
    """Map an API error during a write to a translated HA error."""
    if isinstance(err, NorishConnectionError):
        key = "cannot_connect"
    elif isinstance(err, NorishAuthError):
        key = "invalid_auth"
    else:
        key = "unexpected_response"
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


class NorishDataUpdateCoordinator(DataUpdateCoordinator[NorishData]):
    """Polls groceries regularly and stores less often."""

    config_entry: NorishConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: NorishConfigEntry, client: NorishClient
    ) -> None:
        """Initialize the coordinator."""
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            MIN_SCAN_INTERVAL,
        )
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        # Serializes polling and writes, so a poll that started before a write
        # can never overwrite the state the write produced.
        self._lock = asyncio.Lock()
        self._stores: dict[str, Store] = {}
        self._stores_fetched: datetime | None = None

    async def _async_update_data(self) -> NorishData:
        """Fetch groceries (and stores, when due)."""
        async with self._lock:
            try:
                return await self._async_fetch()
            except NorishAuthError as err:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="invalid_auth"
                ) from err
            except NorishConnectionError as err:
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="cannot_connect"
                ) from err
            except NorishError as err:
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="unexpected_response"
                ) from err

    async def _async_fetch(self) -> NorishData:
        """Fetch the current state. Caller must hold the lock."""
        groceries = sort_groceries(await self.client.async_get_groceries())
        await self._async_refresh_stores_if_needed(groceries)
        return NorishData(groceries=groceries, stores=dict(self._stores))

    async def _async_refresh_stores_if_needed(self, groceries: list[Grocery]) -> None:
        """Refresh the store cache when it is old or a store is unknown."""
        now = dt_util.utcnow()
        last = self._stores_fetched
        unknown = any(g.store_id and g.store_id not in self._stores for g in groceries)
        if not (
            last is None
            or now - last >= STORES_REFRESH_INTERVAL
            or (unknown and now - last >= STORES_MISSING_RETRY_INTERVAL)
        ):
            return
        try:
            stores = await self.client.async_get_stores()
        except NorishAuthError:
            raise
        except NorishError as err:
            # Store names are cosmetic; keep the cache instead of failing.
            LOGGER.debug("Could not refresh Norish stores: %s", err)
            if last is None:
                self._stores_fetched = now - STORES_REFRESH_INTERVAL
            return
        self._stores = {store.id: store for store in stores}
        self._stores_fetched = now

    # ---- write operations -------------------------------------------------

    async def _async_reload(self) -> NorishData:
        """Reload and publish the current state. Caller must hold the lock."""
        data = await self._async_fetch()
        self.async_set_updated_data(data)
        return data

    def _publish(self, groceries: list[Grocery]) -> None:
        """Publish a locally modified grocery list."""
        self.async_set_updated_data(
            NorishData(groceries=sort_groceries(groceries), stores=dict(self._stores))
        )

    async def _async_guarded[T](self, func: Callable[[], Awaitable[T]]) -> T:
        """Run a write under the lock and map API errors."""
        async with self._lock:
            try:
                return await func()
            except NorishAuthError as err:
                self.config_entry.async_start_reauth(self.hass)
                raise _write_error(err) from err
            except NorishError as err:
                raise _write_error(err) from err

    async def async_create_grocery(self, name: str) -> Grocery | None:
        """Create a grocery and make it visible immediately."""

        async def _create() -> Grocery | None:
            created = await self.client.async_create_grocery(name)
            if created is None:
                data = await self._async_reload()
                return next(
                    (g for g in reversed(data.groceries) if g.name == name), None
                )
            groceries = [g for g in self.data.groceries if g.id != created.id]
            self._publish([*groceries, created])
            return created

        return await self._async_guarded(_create)

    async def async_set_done(self, grocery_id: str, done: bool) -> None:
        """Change the done state, retrying once on a stale version."""

        async def _set_done() -> None:
            grocery = await self._async_current(grocery_id)
            if grocery is None:
                raise _not_found(grocery_id)
            if grocery.is_done == done:
                return
            try:
                result = await self._async_write_retry(
                    grocery,
                    lambda g: self.client.async_set_done(g.id, g.version, done),
                    already_done=lambda g: g.is_done == done,
                )
            except NorishNotFoundError as err:
                await self._async_reload()
                raise _not_found(grocery_id) from err
            if result is None:
                return
            if result.grocery is not None:
                self._publish(
                    [
                        result.grocery if g.id == grocery_id else g
                        for g in self.data.groceries
                    ]
                )
            else:
                await self._async_reload()

        await self._async_guarded(_set_done)

    async def async_delete_groceries(self, grocery_ids: list[str]) -> None:
        """Delete groceries, retrying each once on a stale version."""

        async def _delete() -> None:
            deleted: set[str] = set()
            try:
                for grocery_id in grocery_ids:
                    grocery = await self._async_current(grocery_id)
                    if grocery is None:
                        # Already gone, nothing to do.
                        deleted.add(grocery_id)
                        continue
                    with contextlib.suppress(NorishNotFoundError):
                        await self._async_write_retry(
                            grocery,
                            lambda g: self.client.async_delete_grocery(g.id, g.version),
                        )
                    deleted.add(grocery_id)
            finally:
                if deleted:
                    self._publish(
                        [g for g in self.data.groceries if g.id not in deleted]
                    )

        await self._async_guarded(_delete)

    async def _async_current(self, grocery_id: str) -> Grocery | None:
        """Return the grocery from the cache, reloading once if unknown."""
        if (grocery := self.data.get(grocery_id)) is not None:
            return grocery
        return (await self._async_reload()).get(grocery_id)

    async def _async_write_retry(
        self,
        grocery: Grocery,
        write: Callable[[Grocery], Awaitable[WriteResult]],
        already_done: Callable[[Grocery], bool] | None = None,
    ) -> WriteResult | None:
        """Run a versioned write; on stale reload and retry exactly once.

        Returns None if, after reloading, the change is no longer necessary.
        """
        result = await write(grocery)
        if not result.stale:
            return result
        LOGGER.debug("Stale version for grocery %s, reloading", grocery.id)
        current = (await self._async_reload()).get(grocery.id)
        if current is None:
            raise NorishNotFoundError(grocery.id)
        if already_done is not None and already_done(current):
            return None
        result = await write(current)
        if result.stale:
            await self._async_reload()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="stale_version",
                translation_placeholders={"name": current.name},
            )
        return result


def _not_found(grocery_id: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="item_not_found",
        translation_placeholders={"uid": grocery_id},
    )
