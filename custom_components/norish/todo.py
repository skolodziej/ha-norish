"""Todo platform for Norish: the grocery list."""

from __future__ import annotations

from typing import override

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Grocery, Store, format_amount
from .const import CONF_SHOW_STORE, DEFAULT_SHOW_STORE, DESCRIPTION_SEPARATOR, DOMAIN
from .coordinator import NorishConfigEntry, NorishDataUpdateCoordinator
from .entity import NorishEntity

# Writes are serialized in the coordinator.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NorishConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Norish grocery list."""
    async_add_entities([NorishGroceryListEntity(entry.runtime_data)])


def describe_grocery(
    grocery: Grocery, stores: dict[str, Store], show_store: bool
) -> str | None:
    """Build a readable description like ``200 g · Rewe``."""
    quantity = " ".join(
        part for part in (format_amount(grocery.amount), grocery.unit) if part
    )
    parts = [quantity] if quantity else []
    store = stores.get(grocery.store_id) if grocery.store_id else None
    if show_store and store and store.name:
        parts.append(store.name)
    return DESCRIPTION_SEPARATOR.join(parts) or None


class NorishGroceryListEntity(NorishEntity, TodoListEntity):
    """The Norish grocery list as a todo list."""

    _attr_translation_key = "groceries"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: NorishDataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_groceries"

    @property
    def _show_store(self) -> bool:
        return bool(
            self.coordinator.config_entry.options.get(
                CONF_SHOW_STORE, DEFAULT_SHOW_STORE
            )
        )

    def _to_item(self, grocery: Grocery) -> TodoItem:
        return TodoItem(
            uid=grocery.id,
            summary=grocery.name,
            status=(
                TodoItemStatus.COMPLETED
                if grocery.is_done
                else TodoItemStatus.NEEDS_ACTION
            ),
            description=describe_grocery(
                grocery, self.coordinator.data.stores, self._show_store
            ),
        )

    @property
    @override
    def todo_items(self) -> list[TodoItem]:
        """Return the groceries as todo items, ordered by sortOrder."""
        return [self._to_item(g) for g in self.coordinator.data.groceries]

    @override
    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a grocery."""
        name = (item.summary or "").strip()
        if not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="empty_name"
            )
        await self.coordinator.async_create_grocery(name)

    @override
    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a grocery. Only the done state can be changed."""
        assert item.uid
        grocery = self.coordinator.data.get(item.uid)
        if grocery is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="item_not_found",
                translation_placeholders={"uid": item.uid},
            )
        current = self._to_item(grocery)
        if item.summary is not None and item.summary != current.summary:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="rename_not_supported"
            )
        if (item.description or None) != current.description:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="description_not_supported"
            )
        if item.status is None or item.status == current.status:
            return
        await self.coordinator.async_set_done(
            grocery.id, item.status == TodoItemStatus.COMPLETED
        )

    @override
    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more groceries."""
        await self.coordinator.async_delete_groceries(uids)
