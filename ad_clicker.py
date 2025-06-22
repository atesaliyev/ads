import random
import shutil
import string
import traceback
from argparse import ArgumentParser
from datetime import datetime
from itertools import chain, filterfalse, zip_longest
from pathlib import Path
from time import sleep

import hooks
from clicklogs_db import ClickLogsDB
from config_reader import config
from logger import logger, update_log_formats
from proxy import get_proxies
from search_controller import SearchController, update_click_stats
from utils import (
    get_domains,
    get_queries,
    get_random_user_agent_string,
    take_screenshot,
    generate_click_report,
    get_random_sleep,
    add_cookies,
)
from webdriver import create_webdriver


if config.behavior.telegram_enabled:
    from telegram_notifier import notify_matching_ads, start_bot


__author__ = "Coşkun Deniz <coskun.denize@gmail.com>"


def get_arg_parser() -> ArgumentParser:
    """Get argument parser

    :rtype: ArgumentParser
    :returns: ArgumentParser object
    """

    arg_parser = ArgumentParser(add_help=False, usage="See README.md file")
    arg_parser.add_argument("-q", "--query", help="Search query")
    arg_parser.add_argument(
        "-p",
        "--proxy",
        help="""Use the given proxy in "ip:port" or "username:password@host:port" format""",
    )
    arg_parser.add_argument("--id", help="Browser id for multiprocess run")
    arg_parser.add_argument(
        "--enable_telegram", action="store_true", help="Enable telegram notifications"
    )
    arg_parser.add_argument(
        "--report_clicks", action="store_true", help="Get click report for the given date"
    )
    arg_parser.add_argument("--date", help="Give a specific report date in DD-MM-YYYY format")
    arg_parser.add_argument("--excel", action="store_true", help="Write results to an Excel file")
    arg_parser.add_argument(
        "--check_nowsecure", action="store_true", help="Check nowsecure.nl for undetection"
    )
    arg_parser.add_argument("-d", "--device_id", help="Android device ID for assigning to browser")
    arg_parser.add_argument(
        "--supabase", action="store_true", help="Get click report from Supabase instead of SQLite"
    )

    return arg_parser


def main():
    """Entry point for the tool"""

    arg_parser = get_arg_parser()
    args = arg_parser.parse_args()

    if args.report_clicks:
        report_date = datetime.now().strftime("%d-%m-%Y") if not args.date else args.date

        clicklogs_db_client = ClickLogsDB()
        
        # Choose data source based on argument
        if args.supabase:
            click_results = clicklogs_db_client.query_clicks_from_supabase(click_date=report_date)
            data_source = "Supabase"
        else:
            click_results = clicklogs_db_client.query_clicks(click_date=report_date)
            data_source = "SQLite"

        border = (
            "+" + "-" * 70 + "+" + "-" * 27 + "+" + "-" * 9 + "+" + "-" * 12 + "+" + "-" * 12 + "+"
        )

        if click_results:
            print(f"Click Report from {data_source} for {report_date}")
            print(border)
            print(
                f"| {'URL':68s} | {'Query':25s} | {'Clicks':7s} | {'Time':10s} | {'Category':10s} |"
            )
            print(border)

            for result in click_results:
                url, clicks, category, click_time, search_query = result

                if len(url) > 68:
                    url = url[:65] + "..."

                print(
                    f"| {url:68s} | {search_query:25s} | {str(clicks):7s} | {click_time:10s} | {category:10s} |"
                )

                print(border)

            # write results to Excel with name click_report_dd-mm-yyyy.xlsx
            if args.excel:
                generate_click_report(click_results, report_date)

        else:
            logger.info(f"No click result was found for {report_date} in {data_source}!")

        return

    if args.enable_telegram:
        if config.behavior.telegram_enabled:
            start_bot()
            return
        else:
            logger.info("Please set the telegram_enabled option to true in config and try again.")
            return

    if args.id:
        update_log_formats(args.id)

    if args.query:
        query = args.query
    else:
        if not config.behavior.query:
            logger.error("Fill the query parameter!")
            raise SystemExit()

        query = config.behavior.query

    if args.proxy:
        proxy = args.proxy
    elif config.paths.proxy_file:
        proxies = get_proxies()
        logger.debug(f"Proxies: {proxies}")
        proxy = random.choice(proxies)
    elif config.webdriver.proxy:
        proxy = config.webdriver.proxy
    else:
        proxy = None

    domains = get_domains()

    user_agent = get_random_user_agent_string()

    plugin_folder_name = "".join(random.choices(string.ascii_lowercase, k=5))

    driver, country_code = create_webdriver(proxy, user_agent, plugin_folder_name)

    if config.behavior.custom_cookies:
        # Navigate to the domain before setting cookies
        logger.info("Navigating to google.com.tr to set cookies for the correct domain.")
        driver.get("https://www.google.com.tr/")
        add_cookies(driver)

    # Verify public IP to ensure proxy is working
    try:
        logger.info("Verifying proxy connection by checking public IP...")
        driver.get("https://api.ipify.org")
        sleep(get_random_sleep(2, 3) * config.behavior.wait_factor)
        ip_address = driver.find_element(by=By.TAG_NAME, value="body").text
        logger.info(f"Proxy connection successful. Current public IP: {ip_address}")
    except Exception as e:
        logger.error(f"Could not verify proxy IP. The browser might be using the server's IP. Error: {e}")
        # Depending on strictness, you might want to stop the script here
        # raise SystemExit("Failed to verify proxy connection.")

    if args.check_nowsecure:
        driver.get("https://nowsecure.nl/")
        sleep(7 * config.behavior.wait_factor)

        driver.quit()

        raise SystemExit()

    if config.behavior.hooks_enabled:
        hooks.before_search_hook(driver)

    search_controller = None

    try:
        search_controller = SearchController(
            driver,
            query,
            country_code,
            proxy=proxy,
            user_agent=user_agent,
        )

        if args.id:
            search_controller.set_browser_id(args.id)

        if args.device_id:
            search_controller.assign_android_device(args.device_id)

        ads, non_ad_links, shopping_ads = search_controller.search_for_ads(non_ad_domains=domains)

        if config.behavior.hooks_enabled:
            hooks.after_search_hook(driver)

        if not (ads or shopping_ads):
            logger.info("No ads found in the search results!")

            if config.behavior.telegram_enabled:
                notify_matching_ads(query, links=None, stats=search_controller.stats)
        else:
            logger.debug(f"Selected click order: {config.behavior.click_order}")

            if config.behavior.click_order == 1:
                all_links = non_ad_links + ads

            elif config.behavior.click_order == 2:
                all_links = ads + non_ad_links

            elif config.behavior.click_order == 3:
                if non_ad_links:
                    all_links = [non_ad_links[0]] + [ads[0]] + non_ad_links[1:] + ads[1:]
                else:
                    logger.debug("Couldn't found non-ads! Continue with ads only.")
                    all_links = ads

            elif config.behavior.click_order == 4:
                all_links = list(
                    filterfalse(
                        lambda x: not x, chain.from_iterable(zip_longest(non_ad_links, ads))
                    )
                )

            else:
                all_links = ads + non_ad_links
                random.shuffle(all_links)

            logger.info(f"Found {len(ads) + len(shopping_ads)} ads")

            # click on ads
            if ads:
                logger.info(f"Found {len(ads)} ads to potentially click.")
                hooks.before_ad_click_hook(driver)
                
                ads_clicked_count = 0
                # We iterate by index to avoid stale element issues
                for i in range(len(ads)):
                    # Stop if we've reached the max number of clicks for this query
                    if ads_clicked_count >= config.behavior.max_ad_clicks_per_query:
                        logger.info("Reached max ad clicks for this query.")
                        break
                    
                    # Re-find the ads on each iteration to ensure they are not stale
                    current_ads = search_controller._get_ad_links()
                    if i >= len(current_ads):
                        break # Break if the ad list has shrunk
                    
                    ad_element, ad_link, ad_title = current_ads[i]

                    probability = random.random()
                    if probability > config.behavior.ad_click_probability:
                        logger.info(f"Skipping click to [{ad_title}] due to probability.")
                        continue

                    logger.info(f"Attempting to click ad: [{ad_title}]({ad_link})...")

                    try:
                        # Store current URL before clicking
                        current_url = driver.current_url
                        
                        driver.execute_script("arguments[0].click();", ad_element)
                        sleep(3)  # Wait a bit longer for any redirect
                        
                        # Check if new window opened
                        if len(driver.window_handles) > 1:
                            driver.switch_to.window(driver.window_handles[-1])
                            
                            update_click_stats(search_controller, ad_link, "Ad")
                            logger.info(f"Successfully clicked and logged ad: {ad_title}")
                            ads_clicked_count += 1
                            
                            wait_time = get_random_sleep(
                                config.behavior.ad_page_min_wait, config.behavior.ad_page_max_wait
                            )
                            logger.info(f"Waiting on ad page for {int(wait_time)} seconds...")
                            sleep(wait_time)

                            # Safely close the ad tab and switch back
                            try:
                                driver.close()
                                if len(driver.window_handles) > 0:
                                    driver.switch_to.window(driver.window_handles[0])
                            except Exception as e:
                                logger.warning(f"Error switching back to main window: {e}")
                                break
                        else:
                            # Check if URL changed (same-page redirect)
                            new_url = driver.current_url
                            if new_url != current_url:
                                update_click_stats(search_controller, ad_link, "Ad")
                                logger.info(f"Successfully clicked and logged ad (same page): {ad_title}")
                                ads_clicked_count += 1
                                
                                wait_time = get_random_sleep(
                                    config.behavior.ad_page_min_wait, config.behavior.ad_page_max_wait
                                )
                                logger.info(f"Waiting on ad page for {int(wait_time)} seconds...")
                                sleep(wait_time)
                                
                                # Go back to search results
                                driver.back()
                                sleep(2)
                            else:
                                logger.warning("No new window opened and no URL change detected after clicking ad")

                    except Exception as e:
                        logger.error(f"Failed to click on [{ad_title}]! Reason: {e}")
                        # Try to switch back to main window if possible
                        try:
                            if len(driver.window_handles) > 1:
                                driver.switch_to.window(driver.window_handles[0])
                        except Exception as switch_error:
                            logger.warning(f"Could not switch back to main window: {switch_error}")
                            break

                    sleep(get_random_sleep(2, 4) * config.behavior.wait_factor)
            else:
                logger.info("No ads found in the search results!")

            # click on non-ad links
            if non_ad_links:
                logger.info(f"Found {len(non_ad_links)} non-ad links")
                
                for link in non_ad_links:
                    logger.info(f"Clicking to non-ad link [{link}]...")
                    try:
                        # Use JavaScript click for reliability
                        driver.execute_script("arguments[0].click();", link)
                        
                        # After click, switch to the new tab
                        sleep(2) # Give a moment for the new tab to open
                        driver.switch_to.window(driver.window_handles[-1])
                        
                        # Log the click to the database
                        search_controller._update_click_stats("Non-ad", link.get_attribute("href"))

                        # Wait on the page
                        wait_time = get_random_sleep(
                            config.behavior.nonad_page_min_wait, config.behavior.nonad_page_max_wait
                        )
                        logger.info(f"Waiting on page for {int(wait_time)} seconds...")
                        sleep(wait_time)
                        
                        # Close the tab and switch back
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

                    except Exception as e:
                        logger.error(f"Failed to click on non-ad link! Reason: {e}")
                        if len(driver.window_handles) > 1:
                            driver.switch_to.window(driver.window_handles[0])

                    sleep(get_random_sleep(2, 4) * config.behavior.wait_factor)

            if config.behavior.hooks_enabled:
                hooks.after_clicks_hook(driver)

            if config.behavior.telegram_enabled:
                notify_matching_ads(query, links=ads + shopping_ads, stats=search_controller.stats)

            logger.info(search_controller.stats)

    except Exception as exp:
        logger.error("Exception occurred. See the details in the log file.")
        logger.error(f"Error: {exp}")
        
        # Try to take screenshot only if driver is still valid
        try:
            if driver and hasattr(driver, 'current_url'):
                take_screenshot(driver)
        except Exception as screenshot_error:
            logger.warning(f"Could not take screenshot: {screenshot_error}")

        message = str(exp).split("\n")[0]
        logger.debug(f"Exception: {message}")
        details = traceback.format_tb(exp.__traceback__)
        logger.debug(f"Exception details: \n{''.join(details)}")

        logger.debug(f"Exception cause: {exp.__cause__}") if exp.__cause__ else None

        if config.behavior.hooks_enabled:
            hooks.exception_hook(driver)

    finally:
        if search_controller:
            if config.behavior.hooks_enabled:
                hooks.before_browser_close_hook(driver)

            search_controller.end_search()

            if config.behavior.hooks_enabled:
                hooks.after_browser_close_hook(driver)

        if proxy and config.webdriver.auth:
            plugin_folder = Path.cwd() / "proxy_auth_plugin" / plugin_folder_name
            logger.debug(f"Removing '{plugin_folder}' folder...")
            shutil.rmtree(plugin_folder, ignore_errors=True)


if __name__ == "__main__":
    main()
