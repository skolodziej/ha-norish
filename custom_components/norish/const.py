"""Constants for the Norish integration."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "norish"
LOGGER = logging.getLogger(__package__)

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SHOW_STORE: Final = "show_store"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 15
DEFAULT_SHOW_STORE: Final = True

STORES_REFRESH_INTERVAL: Final = timedelta(minutes=15)
STORES_MISSING_RETRY_INTERVAL: Final = timedelta(minutes=1)

AUTH_FAILURE_THRESHOLD: Final = 3

DESCRIPTION_SEPARATOR: Final = " · "
