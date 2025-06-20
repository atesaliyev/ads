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


class ConfigReader:
    """Config file reader"""

    def __init__(self) -> None:
        self.general = None
        self.webdriver = None
        self.behavior = None

    def read_parameters(self) -> None:
        """Read parameters from the config.json file"""

        with open("config.json", encoding="utf-8") as config_file:
            try:
                config = json.loads(config_file.read())
            except Exception:
                logger.error("Failed to read config file. Check format and try again.")
                raise SystemExit()

        self.general = GeneralParams(
            query_file=config["general"]["query_file"],
            domains=config["general"]["domains"],
            domain_mapping=config["general"]["domain_mapping"],
            multi_browser_in_use=config["general"]["multi_browser_in_use"],
            run_on_startup=config["general"]["run_on_startup"],
        )

        self.webdriver = WebdriverParams(
            browser=config["webdriver"]["browser"],
            incognito=config["webdriver"]["incognito"],
            auth=config["webdriver"]["auth"],
            proxy_file=config["webdriver"]["proxy_file"],
            country_domain=config["webdriver"]["country_domain"],
            language_from_proxy=config["webdriver"]["language_from_proxy"],
            use_seleniumbase=config["webdriver"]["use_seleniumbase"],
            window_size=config["webdriver"]["window_size"],
            shift_windows=config["webdriver"]["shift_windows"],
            check_shopping_ads=config["webdriver"]["check_shopping_ads"],
            ss_on_exception=config["webdriver"]["ss_on_exception"],
        )

        self.behavior = BehaviorParams(
            ad_click_probability=config["behavior"]["ad_click_probability"],
            max_ad_clicks_per_query=config["behavior"]["max_ad_clicks_per_query"],
            max_non_ad_clicks_per_query=config["behavior"]["max_non_ad_clicks_per_query"],
            max_shopping_ad_clicks_per_query=config["behavior"]["max_shopping_ad_clicks_per_query"],
            max_total_clicks_per_query=config["behavior"]["max_total_clicks_per_query"],
            wait_factor=config["behavior"]["wait_factor"],
            ad_page_min_wait=config["behavior"]["ad_page_min_wait"],
            ad_page_max_wait=config["behavior"]["ad_page_max_wait"],
            nonad_page_min_wait=config["behavior"]["nonad_page_min_wait"],
            nonad_page_max_wait=config["behavior"]["nonad_page_max_wait"],
            random_mouse=config["behavior"]["random_mouse"],
            custom_cookies=config["behavior"]["custom_cookies"],
            delete_cookies=config["behavior"]["delete_cookies"],
            hooks_enabled=config["behavior"]["hooks_enabled"],
            twocaptcha_apikey=config["behavior"]["twocaptcha_apikey"],
            telegram_enabled=config["behavior"]["telegram_enabled"],
            max_scroll_limit=config["behavior"]["max_scroll_limit"],
        )


config = ConfigReader()
config.read_parameters()
