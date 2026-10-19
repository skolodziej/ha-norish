"""Tests for the Norish config flow."""

from http import HTTPStatus
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.norish.const import CONF_SCAN_INTERVAL, CONF_SHOW_STORE, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import API_KEY, BASE_URL, FakeNorish


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_user_flow_success(hass: HomeAssistant, mock_norish: FakeNorish) -> None:
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: f"{BASE_URL}/api/v1/", CONF_API_KEY: f" {API_KEY} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "norish.test"
    assert result["data"] == {CONF_URL: BASE_URL, CONF_API_KEY: API_KEY}
    assert result["result"].unique_id == BASE_URL
    assert mock_norish.count("GET", "/groceries") >= 1


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        ("down", "cannot_connect"),
        ("unauthorized", "invalid_auth"),
        ("forbidden", "invalid_auth"),
        ("server_error", "unexpected_response"),
    ],
)
async def test_user_flow_errors_and_recovery(
    hass: HomeAssistant, mock_norish: FakeNorish, setup: str, error: str
) -> None:
    if setup == "down":
        mock_norish.down = True
    elif setup == "unauthorized":
        mock_norish.auth_ok = False
    elif setup == "forbidden":
        mock_norish.fail_status = HTTPStatus.FORBIDDEN
    else:
        mock_norish.fail_status = HTTPStatus.INTERNAL_SERVER_ERROR

    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: BASE_URL, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_norish.down = False
    mock_norish.auth_ok = True
    mock_norish.fail_status = None
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: BASE_URL, CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unknown_error(
    hass: HomeAssistant, mock_norish: FakeNorish
) -> None:
    flow_id = await _start(hass)
    with patch(
        "custom_components.norish.config_flow.NorishClient.async_get_groceries",
        side_effect=RuntimeError,
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_URL: BASE_URL, CONF_API_KEY: API_KEY}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_invalid_url(hass: HomeAssistant) -> None:
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: "ftp://x", CONF_API_KEY: API_KEY}
    )
    assert result["errors"] == {CONF_URL: "invalid_url"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_norish: FakeNorish, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_URL: "norish.test/api/v1/", CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_norish: FakeNorish
) -> None:
    result = await init_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_norish.auth_ok = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_norish.auth_ok = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert init_integration.data[CONF_API_KEY] == "new-key"
    assert init_integration.data[CONF_URL] == BASE_URL


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30.0, CONF_SHOW_STORE: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert init_integration.options == {CONF_SCAN_INTERVAL: 30, CONF_SHOW_STORE: False}
    assert init_integration.runtime_data.update_interval.total_seconds() == 30


async def test_options_flow_minimum(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    from homeassistant.data_entry_flow import InvalidData

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 5, CONF_SHOW_STORE: True}
        )
