import json
import multiprocessing
from dataclasses import dataclass
from typing import Optional

from logger import logger


@dataclass
class GeneralParams:
    query_file: str
    domains: str
    domain_mapping: str
    multi_browser_in_use: bool
    run_on_startup: bool


@dataclass
class WebdriverParams:
    browser: str
    incognito: bool
    auth: bool
    proxy_file: Optional[str]
    country_domain: bool
    language_from_proxy: bool
    use_seleniumbase: bool
    window_size: Optional[str]
    shift_windows: bool
    check_shopping_ads: bool
    ss_on_exception: bool


@dataclass
class BehaviorParams:
    ad_click_probability: float
    max_ad_clicks_per_query: int
    max_non_ad_clicks_per_query: int
    max_shopping_ad_clicks_per_query: int
    max_total_clicks_per_query: int
    wait_factor: float
    ad_page_min_wait: int
    ad_page_max_wait: int
    nonad_page_min_wait: int
    nonad_page_max_wait: int
    random_mouse: bool
    custom_cookies: bool
    delete_cookies: bool
    hooks_enabled: bool
    twocaptcha_apikey: str
    telegram_enabled: bool
    max_scroll_limit: int
    excludes: Optional[str]
    check_shopping_ads: bool
    click_order: int


class ConfigReader:
    """Config reader for the bot"""

    def __init__(self, config_file: str = "config.json") -> None:
        self.config_file = config_file
        self._config = self._load_config()

        # Dynamically load configuration sections as attributes
        for section, values in self._config.items():
            setattr(self, section, self._Section(values))

    def _load_config(self) -> dict:
        """Load configuration from json file"""
        try:
            with open(self.config_file, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            logger.error(f"Configuration file '{self.config_file}' not found.")
            raise SystemExit()
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from '{self.config_file}'.")
            raise SystemExit()

    class _Section:
        """Represents a section of the configuration"""
        def __init__(self, data: dict):
            for key, value in data.items():
                setattr(self, key, value)
        
        def __getattr__(self, name):
            # If an attribute is not found, return None instead of raising an error
            return None

    def __getattr__(self, name):
        # If a section is not found, return an empty Section object
        # which will return None for any attribute access.
        return self._Section({})

# Create a single, globally accessible instance of the config reader.
# This can be imported by other modules.
config = ConfigReader()
