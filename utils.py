import sys
import json
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from enum import Enum
from itertools import cycle
from pathlib import Path
from time import sleep
from typing import Optional

try:
    import requests
    import openpyxl
    import undetected_chromedriver
    from openpyxl.styles import Alignment, Font

except ImportError:
    packages_path = Path.cwd() / "env" / "Lib" / "site-packages"
    sys.path.insert(0, f"{packages_path}")

    import requests
    import openpyxl
    import undetected_chromedriver
    from openpyxl.styles import Alignment, Font

from config_reader import config
from geolocation_db import GeolocationDB
from logger import logger
from proxy import get_proxies


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    BOTH = "BOTH"


def get_random_user_agent_string() -> str:
    """Get random user agent

    :rtype: str
    :returns: User agent string
    """

    # The user_agents file path is now hardcoded as it's a core part of the project.
    user_agents = _get_user_agents(Path("user_agents.txt"))

    user_agent_string = random.choice(user_agents)

    logger.debug(f"user_agent: {user_agent_string}")

    return user_agent_string


def _get_user_agents(user_agent_file: Path) -> list[str]:
    """Get user agents from file

    :type user_agent_file: Path
    :param user_agent_file: File containing user agents
    :rtype: list
    :returns: List of user agents
    """

    filepath = Path(user_agent_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find user agents file: {filepath}")

    with open(filepath, encoding="utf-8") as useragentfile:
        user_agents = [
            user_agent.strip().replace("'", "").replace('"', "")
            for user_agent in useragentfile.read().splitlines()
        ]

    return user_agents


def get_location(geolocation_db_client: GeolocationDB, proxy: str) -> tuple[float, float, str, str]:
    """Get latitude, longitude, country code, and timezone of ip address

    :type geolocation_db_client: GeolocationDB
    :param geolocation_db_client: GeolocationDB instance
    :type proxy: str
    :param proxy: Proxy to get geolocation
    :rtype: tuple
    :returns: (latitude, longitude, country_code, timezone) tuple for the given proxy IP
    """

    proxies_header = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    ip_address = ""

    if config.webdriver.auth:
        for repeat in range(2):
            try:
                response = requests.get("https://api.ipify.org", proxies=proxies_header, timeout=5)
                ip_address = response.text

                if not ip_address:
                    raise Exception("Failed with https://api.ipify.org")

                break

            except Exception as exp:
                logger.debug(exp)

                try:
                    logger.debug("Trying with ipv4.webshare.io...")
                    response = requests.get(
                        "https://ipv4.webshare.io/", proxies=proxies_header, timeout=5
                    )
                    ip_address = response.text

                    if not ip_address:
                        raise Exception("Failed with https://ipv4.webshare.io")

                    break

                except Exception as exp:
                    logger.debug(exp)

                    try:
                        logger.debug("Trying with ipconfig.io...")
                        response = requests.get(
                            "https://ipconfig.io/json", proxies=proxies_header, timeout=5
                        )
                        ip_address = response.json().get("ip")

                        if not ip_address:
                            raise Exception("Failed with https://ipconfig.io/json")

                        break

                    except Exception as exp:
                        logger.debug(exp)

                        if repeat == 1:
                            break

                        request_retry_timeout = 60 * config.behavior.wait_factor
                        logger.info(f"Request will be resend after {request_retry_timeout} seconds")

                        sleep(request_retry_timeout)

            sleep(get_random_sleep(0.5, 1) * config.behavior.wait_factor)
    else:
        ip_address = proxy.split(":")[0]

    if not ip_address:
        logger.info(f"Couldn't verify IP address for {proxy}!")
        logger.debug("Geolocation won't be set")
        return (None, None, None, None)

    logger.info(f"Connecting with IP: {ip_address}")

    db_result = geolocation_db_client.query_geolocation(ip_address)

    latitude = None
    longitude = None
    country_code = None
    timezone = None

    if db_result:
        latitude, longitude, country_code = db_result
        logger.debug(f"Cached latitude and longitude for {ip_address}: ({latitude}, {longitude})")
        logger.debug(f"Cached country code for {ip_address}: {country_code}")

        if not country_code:
            try:
                response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=5)
                country_code = response.json().get("country_code")
                timezone = response.json().get("timezone")
                logger.debug(f"Country code for {ip_address}: {country_code}")

            except Exception:
                try:
                    response = requests.get(
                        "https://ifconfig.co/json", proxies=proxies_header, timeout=5
                    )
                    country_code = response.json().get("country_iso")
                    timezone = response.json().get("time_zone")
                except Exception:
                    logger.debug(f"Couldn't find country code for {ip_address}!")

        return (float(latitude), float(longitude), country_code, timezone)

    else:
        retry_count = 0
        max_retry_count = 5
        sleep_seconds = 5 * config.behavior.wait_factor

        while retry_count < max_retry_count:
            try:
                response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=5)
                latitude, longitude, country_code, timezone = (
                    response.json().get("latitude"),
                    response.json().get("longitude"),
                    response.json().get("country_code"),
                    response.json().get("timezone"),
                )

                if not (latitude and longitude and country_code):
                    raise Exception("Failed with https://ipapi.co")

                break
            except Exception as exp:
                logger.debug(exp)
                logger.debug("Continue with ifconfig.co")

                try:
                    response = requests.get(
                        "https://ifconfig.co/json", proxies=proxies_header, timeout=5
                    )
                    latitude, longitude, country_code, timezone = (
                        response.json().get("latitude"),
                        response.json().get("longitude"),
                        response.json().get("country_iso"),
                        response.json().get("time_zone"),
                    )

                    if not (latitude and longitude and country_code):
                        raise Exception("Failed with https://ifconfig.co/json")

                    break
                except Exception as exp:
                    logger.debug(exp)
                    logger.debug("Continue with ipconfig.io")

                    try:
                        response = requests.get(
                            "https://ipconfig.io/json", proxies=proxies_header, timeout=5
                        )
                        latitude, longitude, country_code, timezone = (
                            response.json().get("latitude"),
                            response.json().get("longitude"),
                            response.json().get("country_iso"),
                            response.json().get("time_zone"),
                        )

                        if not (latitude and longitude and country_code):
                            raise Exception("Failed with https://ipconfig.io/json")

                        break
                    except Exception as exp:
                        logger.debug(exp)
                        logger.error(
                            f"Couldn't find latitude and longitude for {ip_address}! "
                            f"Retrying after {sleep_seconds} seconds..."
                        )

                        retry_count += 1
                        sleep(sleep_seconds)
                        sleep_seconds *= 2

            sleep(0.5 * config.behavior.wait_factor)

        if latitude and longitude and country_code:
            logger.debug(f"Latitude and longitude for {ip_address}: ({latitude}, {longitude})")
            logger.debug(f"Country code for {ip_address}: {country_code}")

            geolocation_db_client.save_geolocation(ip_address, latitude, longitude, country_code)

            return (latitude, longitude, country_code, timezone)
        else:
            logger.error(f"Couldn't find latitude, longitude, and country_code for {ip_address}!")
            return (None, None, None, None)


def get_queries() -> list[str]:
    """Get queries from file

    :rtype: list
    :returns: List of queries
    """

    filepath = Path(config.paths.query_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find query file: {filepath}")

    with open(filepath, encoding="utf-8") as queryfile:
        queries = [
            query.strip().replace("'", "").replace('"', "")
            for query in queryfile.read().splitlines()
        ]

    return queries


def get_domains() -> list[str]:
    """Get domains from file

    :rtype: list
    :returns: List of domains
    """

    filepath = Path(config.paths.domains_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find domains file: {filepath}")

    with open(filepath, encoding="utf-8") as domainfile:
        domains = [
            domain.strip().replace("'", "").replace('"', "")
            for domain in domainfile.read().splitlines()
        ]

    logger.debug(f"Domains: {domains}")

    return domains


def add_cookies(driver: undetected_chromedriver.Chrome) -> None:
    """Add cookies from a JSON-formatted cookies.txt file.

    This function is designed to handle the standard format exported by
    browser extensions like 'Get cookies.txt LOCALLY'. This format is
    a JSON array of cookie objects.

    :type driver: undetected_chromedriver.Chrome
    :param driver: Selenium Chrome webdriver instance
    """
    filepath = Path.cwd() / "cookies.txt"
    if not filepath.exists():
        raise SystemExit("Missing cookies.txt file!")

    logger.info(f"Adding cookies from {filepath}")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            cookies_list = json.load(f)

        if not isinstance(cookies_list, list):
            logger.error(f"Invalid cookies format in {filepath}. Expected a JSON array.")
            return

        for cookie in cookies_list:
            # Selenium's add_cookie method can be picky. We need to ensure
            # all required fields are present and correctly typed.
            # We also remove fields that are not recognized by all WebDriver versions.

            # USER'S SUGGESTION: Force cookie domain to .google.com.tr
            # This is the best way to solve the 'domain mismatch' error.
            original_domain = cookie.get("domain", "")
            if "google.com" in original_domain:
                cookie["domain"] = ".google.com.tr"
                # If a cookie was host-only (e.g., for www.google.com),
                # it must be changed to not be host-only for the new parent domain.
                if "hostOnly" in cookie:
                    cookie["hostOnly"] = False
            
            # The 'expiry' key is used by some WebDriver versions instead of 'expirationDate'.
            if 'expirationDate' in cookie:
                cookie['expiry'] = int(cookie['expirationDate'])
                del cookie['expirationDate']
            elif 'expires' in cookie:
                # Convert from seconds since epoch to integer expiry timestamp
                cookie['expiry'] = int(cookie['expires'])
                del cookie['expires']

            # These keys are often in exported cookies but not used by add_cookie.
            # Removing them prevents potential errors.
            for key in ('storeId', 'id', 'sameSite', 'priority', 'sameParty', 'size', 'sourcePort', 'sourceScheme', 'partitionKey', 'hostOnly'):
                if key in cookie:
                    del cookie[key]
            
            # Some fields must be present.
            if 'domain' not in cookie or 'name' not in cookie or 'value' not in cookie:
                logger.warning(f"Skipping malformed cookie: {cookie}")
                continue

            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Could not add cookie: {cookie['name']}. Reason: {e}")

    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {filepath}. Please ensure it is a valid JSON file.")
        # Optional: Add fallback for simple name=value format if needed, but for now, we enforce JSON.
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing cookies: {e}")


def solve_recaptcha(
    apikey: str,
    sitekey: str,
    current_url: str,
    data_s: str,
    cookies: Optional[str] = None,
) -> Optional[str]:
    """Solve the recaptcha using the 2captcha service

    :type apikey: str
    :param apikey: API key for the 2captcha service
    :type sitekey: str
    :param sitekey: data-sitekey attribute value of the recaptcha element
    :type current_url: str
    :param current_url: Url that is showing the captcha
    :type data_s: str
    :param data_s: data-s attribute of the captcha element
    :type cookies: str
    :param cookies: Cookies to send 2captcha service
    :rtype: str
    :returns: Response code obtained from the service or None
    """

    logger.info("Trying to solve captcha...")

    api_url = "http://2captcha.com/in.php"
    params = {
        "key": apikey,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": current_url,
        "data-s": data_s,
    }

    if cookies:
        params["cookies"] = cookies

    max_retry_count = 10
    request_retry_count = 0

    while request_retry_count < max_retry_count:
        response = requests.get(api_url, params=params)

        logger.debug(f"Response: {response.text}")

        error_to_exit, error_to_continue, error_to_break = _check_error(response.text)

        if error_to_exit:
            raise SystemExit()

        elif error_to_break:
            request_id = response.text.split("|")[1]
            logger.debug(f"request_id: {request_id}")
            break

        elif error_to_continue:
            request_retry_count += 1
            continue

    initial_captcha_response_wait = 15
    sleep(initial_captcha_response_wait * config.behavior.wait_factor)

    # check if the CAPTCHA has been solved
    response_api_url = "http://2captcha.com/res.php"
    params = {"key": apikey, "action": "get", "id": request_id}

    response_retry_count = 0
    captcha_response = None

    while response_retry_count < max_retry_count:
        response = requests.get(response_api_url, params=params)

        logger.debug(f"Response: {response.text}")

        error_to_exit, error_to_continue, error_to_break = _check_error(
            response.text, request_type="res_php"
        )

        if error_to_exit:
            raise SystemExit()

        elif error_to_continue:
            response_retry_count += 1
            continue

        elif error_to_break:
            if "CAPCHA_NOT_READY" not in response.text:
                captcha_response = response.text.split("|")[1]
                return captcha_response

    if not captcha_response:
        logger.error("Failed to solve captcha!")

    return captcha_response


def take_screenshot(driver: undetected_chromedriver.Chrome) -> None:
    """Save screenshot during exception

    :type driver: undetected_chromedriver.Chrome
    :param driver: Selenium Chrome webdriver instance
    """

    now = datetime.now().strftime("%d-%m-%Y_%H:%M:%S")
    filename = f"exception_ss_{now}.png"

    if driver:
        driver.save_screenshot(filename)
        sleep(get_random_sleep(1, 1.5) * config.behavior.wait_factor)
        logger.info(f"Saved screenshot during exception as {filename}")


def generate_click_report(click_results: list[tuple[str, str, str]], report_date: str) -> None:
    """Update results file with new rows

    :type click_results: list
    :param click_results: List of (site_url, clicks, category, click_time, query) tuples
    :type report_date: str
    :param report_date: Date to query clicks
    """

    click_report_file = Path(f"click_report_{report_date}.xlsx")

    workbook = openpyxl.Workbook()
    sheet = workbook.active

    sheet.row_dimensions[1].height = 20

    # add header
    sheet["A1"] = "URL"
    sheet["B1"] = "Query"
    sheet["C1"] = "Clicks"
    sheet["D1"] = "Time"
    sheet["E1"] = "Category"

    bold_font = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center")

    for cell in ("A1", "B1", "C1", "D1", "E1"):
        sheet[cell].font = bold_font
        sheet[cell].alignment = center_align

    # adjust column widths
    sheet.column_dimensions["A"].width = 80
    sheet.column_dimensions["B"].width = 25
    sheet.column_dimensions["C"].width = 15
    sheet.column_dimensions["D"].width = 20
    sheet.column_dimensions["E"].width = 15

    for result in click_results:
        url, click_count, category, click_time, query = result
        sheet.append((url, query, click_count, f"{report_date} {click_time}", category))

    for column_letter in ("B", "C", "D", "E"):
        sheet.column_dimensions[column_letter].alignment = center_align

    workbook.save(click_report_file)

    logger.info(f"Results were written to {click_report_file}")


def get_random_sleep(start: int, end: int) -> float:
    """Generate a random number from the given range

    :type start: int
    :pram start: Start value
    :type end: int
    :pram end: End value
    :rtype: float
    :returns: Randomly selected number rounded to 2 decimals
    """

    return round(random.uniform(start, end), 2)


def _check_error(response_text: str, request_type: str = "in_php") -> tuple[bool, bool, bool]:
    """Check errors returned from requests to in.php or res.php endpoints

    :type response_text: str
    :param response_text: Response returned from the request
    :request_type: str
    :param request_type: Request type to differentiate error groups
    :rtype: tuple
    :returns: Flags for exit, continue, and break
    """

    logger.debug("Checking error code...")

    error_to_exit, error_to_continue, error_to_break = False, False, False
    error_wait = 5 * config.behavior.wait_factor

    if request_type == "in_php":
        if "ERROR_WRONG_USER_KEY" in response_text or "ERROR_KEY_DOES_NOT_EXIST" in response_text:
            logger.error("Invalid API key. Please check your 2captcha API key.")
            error_to_exit = True

        elif "ERROR_ZERO_BALANCE" in response_text:
            logger.error("You don't have funds on your account. Please load your account.")
            error_to_exit = True

        elif "ERROR_NO_SLOT_AVAILABLE" in response_text:
            logger.error(
                "The queue of your captchas that are not distributed to workers is too long."
            )
            logger.info(f"Waiting {error_wait} seconds before sending new request...")
            sleep(error_wait)

            error_to_continue = True

        elif "IP_BANNED" in response_text:
            logger.error(
                "Your IP address is banned due to many frequent attempts to access the server"
            )
            error_to_exit = True

        elif "ERROR_GOOGLEKEY" in response_text:
            logger.error("Blank or malformed sitekey.")
            error_to_exit = True

        else:
            logger.debug(response_text)
            error_to_break = True

    elif request_type == "res_php":
        if "ERROR_WRONG_USER_KEY" in response_text or "ERROR_KEY_DOES_NOT_EXIST" in response_text:
            logger.error("Invalid API key. Please check your 2captcha API key.")
            error_to_exit = True

        elif "ERROR_CAPTCHA_UNSOLVABLE" in response_text:
            logger.error("Unable to solve the captcha.")
            error_to_exit = True

        elif "CAPCHA_NOT_READY" in response_text:
            logger.info(f"Waiting {error_wait} seconds before checking response again...")
            sleep(error_wait)

            error_to_continue = True

        else:
            logger.debug(response_text)
            error_to_break = True

    else:
        logger.error(f"Wrong request type: {request_type}")

    return (error_to_exit, error_to_continue, error_to_break)


def get_locale_language(country_code: str) -> str:
    """Get locale language for the given country code

    :type country_code: str
    :param country_code: Country code for proxy IP
    :rtype: str
    :returns: Locale language for the given country code
    """

    logger.debug(f"Getting locale language for {country_code}...")

    with open("country_to_locale.json", "r") as locales_file:
        locales = json.load(locales_file)

    locale_language = locales.get(country_code, ["en"])

    logger.debug(f"Locale language code for {country_code}: {locale_language[0]}")

    return locale_language


def resolve_redirect(url: str) -> str:
    """Resolve any redirects and return the final destination URL

    :type url: str
    :param url: Input url to resolve
    :rtype: str
    :returns: Final destination URL
    """

    try:
        response = requests.get(url, allow_redirects=True)
        return response.url

    except requests.RequestException as exp:
        logger.error(f"Error resolving URL redirection: {exp}")
        return url


def _make_boost_request(url: str, proxy: str, user_agent: str) -> None:
    """Make a single GET request for the given url through a random proxy and user agent

    :type url: str
    :param url: Input URL to send request to
    :type proxy: str
    :param proxy: Proxy to use for the request
    :type user_agent: str
    :param user_agent: User agent to use for the request
    """

    headers = {"User-Agent": user_agent}
    proxy_config = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    try:
        response = requests.get(url, headers=headers, proxies=proxy_config, timeout=5)
        logger.debug(
            f"Boosted [{url}] via [{proxy.split('@')[1] if '@' in proxy else proxy}] "
            f"UA={headers['User-Agent']}, Response code: {response.status_code}"
        )

    except Exception as exp:
        logger.debug(f"Boost request failed for [{url}] via [{proxy}]: {exp}")


def boost_requests(url: str) -> None:
    """Send multiple requests to the given URL

    :type url: str
    :param url: Input URL to send requests to
    """

    logger.debug(f"Sending 10 requests to [{url}]...")

    proxies = get_proxies()
    user_agents = _get_user_agents(Path("user_agents.txt"))

    random.shuffle(proxies)
    random.shuffle(user_agents)

    proxy = cycle(proxies)
    user_agent = cycle(user_agents)

    with ThreadPoolExecutor(max_workers=10) as executor:
        for _ in range(10):
            executor.submit(_make_boost_request, url, next(proxy), next(user_agent))
