import os
import random
import shutil
import sys
from pathlib import Path
from time import sleep
from typing import Optional, Union

try:
    import pyautogui
    import requests
    import seleniumbase
    import undetected_chromedriver

except ImportError:
    packages_path = Path.cwd() / "env" / "Lib" / "site-packages"
    sys.path.insert(0, f"{packages_path}")

    import pyautogui
    import requests
    import seleniumbase
    import undetected_chromedriver

from config_reader import config
from geolocation_db import GeolocationDB
from logger import logger
from proxy import install_plugin
from utils import get_location, get_locale_language, get_random_sleep


IS_POSIX = sys.platform.startswith(("cygwin", "linux"))


class CustomChrome(undetected_chromedriver.Chrome):
    """Modified Chrome implementation"""

    def quit(self):

        try:
            # logger.debug("Terminating the browser")
            os.kill(self.browser_pid, 15)
            if IS_POSIX:
                os.waitpid(self.browser_pid, 0)
            else:
                sleep(0.05 * config.behavior.wait_factor)
        except (AttributeError, ChildProcessError, RuntimeError, OSError):
            pass
        except TimeoutError as e:
            logger.debug(e, exc_info=True)
        except Exception:
            pass

        if hasattr(self, "service") and getattr(self.service, "process", None):
            # logger.debug("Stopping webdriver service")
            self.service.stop()

        try:
            if self.reactor:
                # logger.debug("Shutting down Reactor")
                self.reactor.event.set()
        except Exception:
            pass

        if (
            hasattr(self, "keep_user_data_dir")
            and hasattr(self, "user_data_dir")
            and not self.keep_user_data_dir
        ):
            for _ in range(5):
                try:
                    shutil.rmtree(self.user_data_dir, ignore_errors=False)
                except FileNotFoundError:
                    pass
                except (RuntimeError, OSError, PermissionError) as e:
                    logger.debug(
                        "When removing the temp profile, a %s occured: %s\nretrying..."
                        % (e.__class__.__name__, e)
                    )
                else:
                    # logger.debug("successfully removed %s" % self.user_data_dir)
                    break

                sleep(0.1 * config.behavior.wait_factor)

        # dereference patcher, so patcher can start cleaning up as well.
        # this must come last, otherwise it will throw 'in use' errors
        self.patcher = None

    def __del__(self):
        try:
            self.service.process.kill()
        except Exception:  # noqa
            pass

        try:
            self.quit()
        except OSError:
            pass

    @classmethod
    def _ensure_close(cls, self):
        # needs to be a classmethod so finalize can find the reference
        if (
            hasattr(self, "service")
            and hasattr(self.service, "process")
            and hasattr(self.service.process, "kill")
        ):
            self.service.process.kill()

            if IS_POSIX:
                try:
                    # prevent zombie processes
                    os.waitpid(self.service.process.pid, 0)
                except ChildProcessError:
                    pass
                except Exception:
                    pass
            else:
                sleep(0.05 * config.behavior.wait_factor)


def create_webdriver(
    proxy: str, user_agent: Optional[str] = None, plugin_folder_name: Optional[str] = None
) -> tuple[undetected_chromedriver.Chrome, Optional[str]]:
    """Create Selenium Chrome webdriver instance

    :type proxy: str
    :param proxy: Proxy to use in ip:port or user:pass@host:port format
    :type user_agent: str
    :param user_agent: User agent string
    :type plugin_folder_name: str
    :param plugin_folder_name: Plugin folder name for proxy
    :rtype: tuple
    :returns: (undetected_chromedriver.Chrome, country_code) pair
    """

    if config.webdriver.use_seleniumbase:
        logger.debug("Using SeleniumBase...")
        return create_seleniumbase_driver(proxy, user_agent)

    geolocation_db_client = GeolocationDB()

    chrome_options = undetected_chromedriver.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-service-autorun")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--deny-permission-prompts")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--disable-breakpad")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-browser-side-navigation")
    chrome_options.add_argument("--disable-save-password-bubble")
    chrome_options.add_argument("--disable-single-click-autofill")
    chrome_options.add_argument("--disable-prompt-on-repost")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-hang-monitor")
    chrome_options.add_argument("--dns-prefetch-disable")
    chrome_options.add_argument(f"--user-agent={user_agent}")

    if IS_POSIX:
        chrome_options.add_argument("--disable-setuid-sandbox")

    # Start the browser maximized to avoid issues with new Chrome versions
    chrome_options.add_argument("--start-maximized")

    optimization_features = [
        "OptimizationGuideModelDownloading",
        "OptimizationHintsFetching",
        "OptimizationTargetPrediction",
        "OptimizationHints",
        "Translate",
        "DownloadBubble",
        "DownloadBubbleV2",
    ]
    chrome_options.add_argument(f"--disable-features={','.join(optimization_features)}")

    if config.webdriver.incognito:
        chrome_options.add_argument("--incognito")

    country_code = None

    # Create a dictionary to hold all preferences
    prefs = {
        # WebRTC settings to prevent IP leak
        "webrtc.ip_handling_policy": "disable_non_proxied_udp",
        "webrtc.multiple_routes_enabled": False,
        "webrtc.nonproxied_udp_enabled": False,
    }

    multi_browser_flag_file = Path(".MULTI_BROWSERS_IN_USE")
    multi_procs_enabled = multi_browser_flag_file.exists()
    driver_exe_path = None

    if multi_procs_enabled:
        driver_exe_path = _get_driver_exe_path()

    if proxy:
        logger.info(f"Using proxy: {proxy}")

        # Force DNS to go through proxy as well, to prevent DNS leaks
        prefs["net.proxy.proxy_dns"] = True

        if config.webdriver.auth:
            if "@" not in proxy or proxy.count(":") != 2:
                raise ValueError(
                    "Invalid proxy format! Should be in 'username:password@host:port' format"
                )

            username, password = proxy.split("@")[0].split(":")
            host, port = proxy.split("@")[1].split(":")

            install_plugin(chrome_options, host, int(port), username, password, plugin_folder_name)
            sleep(2 * config.behavior.wait_factor)

        else:
            chrome_options.add_argument(f"--proxy-server={proxy}")

        # get location of the proxy IP
        lat, long, country_code, timezone = get_location(geolocation_db_client, proxy)

        # ================== NUCLEAR OPTION: HARDCODE TURKISH SETTINGS ==================
        # Forcing all settings to Turkish to isolate the problem.
        logger.debug("NUCLEAR OPTION ENGAGED: Forcing all settings to TR.")
        
        country_code = "TR"
        timezone = "Europe/Istanbul"
        
        # Friend's suggestions
        prefs["intl.accept_languages"] = "tr,tr-TR"
        chrome_options.add_argument("--lang=tr-TR")
        # ==============================================================================

        # Add all collected preferences at once
        chrome_options.add_experimental_option("prefs", prefs)

        driver = CustomChrome(
            driver_executable_path=(
                driver_exe_path if multi_procs_enabled and Path(driver_exe_path).exists() else None
            ),
            options=chrome_options,
            user_multi_procs=multi_procs_enabled,
            use_subprocess=False,
            headless=False,
        )

        # Friend's JS override suggestion
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            "source": """
                Object.defineProperty(navigator, 'language', {get: () => 'tr-TR'});
                Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr']});
            """
        })

        # Set timezone if available
        if timezone:
            logger.debug(f"Overriding timezone to {timezone}...")
            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": timezone})

        accuracy = 95

        # Set geolocation and timezone of the browser according to IP address
        if lat and long:
            driver.execute_cdp_cmd(
                "Emulation.setGeolocationOverride",
                {"latitude": lat, "longitude": long, "accuracy": accuracy},
            )

            # If timezone was not found (and not TR), try to look it up
            if not timezone:
                try:
                    response = requests.get(f"http://timezonefinder.michelfe.it/api/0_{long}_{lat}")
                    if response.status_code == 200:
                        timezone = response.json().get("timezone_id")
                except Exception as e:
                    logger.warning(f"Timezone API lookup failed: {e}")

        # If we have a timezone, apply it
        if timezone:
            try:
                logger.debug(f"Applying timezone override: {timezone}")
                driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": timezone})
            except Exception as e:
                logger.warning(f"Could not set timezone: {e}")

        # Force locale to match the proxy country to prevent location leakage
        if country_code == "TR":
            try:
                locale_override = "tr-TR"
                logger.debug(f"Applying locale override with: {locale_override}")
                driver.execute_cdp_cmd("Emulation.setLocaleOverride", {"locale": locale_override})
            except Exception as e:
                logger.warning(f"Could not set locale override: {e}")

    else:
        driver = CustomChrome(
            options=chrome_options,
            user_multi_procs=multi_procs_enabled,
            use_subprocess=False,
            headless=False,
        )

    # driver.maximize_window() is commented out to prevent errors
    sleep(1 * config.behavior.wait_factor)
    _shift_window_position(driver)

    return driver, country_code

def create_seleniumbase_driver(
    proxy: str, user_agent: Optional[str] = None
) -> tuple[seleniumbase.Driver, Optional[str]]:
    """Create SeleniumBase Chrome webdriver instance

    :type proxy: str
    :param proxy: Proxy to use in ip:port or user:pass@host:port format
    :type user_agent: str
    :param user_agent: User agent string
    :rtype: tuple
    :returns: (Driver, country_code) pair
    """

    geolocation_db_client = GeolocationDB()

    country_code = None

    if proxy:
        logger.info(f"Using proxy: {proxy}")

        if config.webdriver.auth:
            if "@" not in proxy or proxy.count(":") != 2:
                raise ValueError(
                    "Invalid proxy format! Should be in 'username:password@host:port' format"
                )

        # get location of the proxy IP
        lat, long, country_code, timezone = get_location(geolocation_db_client, proxy)

        if config.webdriver.language_from_proxy:
            lang = get_locale_language(country_code)

    driver = seleniumbase.get_driver(
        browser_name="chrome",
        undetectable=True,
        headless2=False,
        do_not_track=True,
        user_agent=user_agent,
        proxy_string=proxy or None,
        incognito=config.webdriver.incognito,
        locale_code=str(lang) if config.webdriver.language_from_proxy else None,
    )

    # set geolocation and timezone if available
    if proxy and lat and long:
        accuracy = 95
        driver.execute_cdp_cmd(
            "Emulation.setGeolocationOverride",
            {"latitude": lat, "longitude": long, "accuracy": accuracy},
        )

        if not timezone:
            response = requests.get(f"http://timezonefinder.michelfe.it/api/0_{long}_{lat}")
            if response.status_code == 200:
                timezone = response.json()["timezone_id"]

        if timezone:
            try:
                driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": timezone})
            except Exception as e:
                logger.warning(f"Could not set timezone: {e}")

        logger.debug(
            f"Timezone of {proxy.split('@')[1] if config.webdriver.auth else proxy}: {timezone}"
        )

    sleep(1 * config.behavior.wait_factor)

    _shift_window_position(driver)

    return driver, country_code


def _shift_window_position(
    driver: Union[undetected_chromedriver.Chrome, seleniumbase.Driver],
    width: int = None,
    height: int = None,
) -> None:
    """Shift the browser window position randomly

    :type driver: Union[undetected_chromedriver.Chrome, seleniumbase.Driver]
    :param driver: WebDriver instance
    :type width: int
    :param width: Predefined window width
    :type height: int
    :param height: Predefined window height
    """

    # get screen size
    screen_width, screen_height = pyautogui.size()

    window_position = driver.get_window_position()
    x, y = window_position["x"], window_position["y"]

    random_x_offset = random.choice(range(150, 300))
    random_y_offset = random.choice(range(75, 150))

    if width and height:
        new_width = int(width) - random_x_offset
        new_height = int(height) - random_y_offset
    else:
        new_width = int(screen_width * 2 / 3) - random_x_offset
        new_height = int(screen_height * 2 / 3) - random_y_offset

    # set the window size and position
    driver.set_window_size(new_width, new_height)

    new_x = min(x + random_x_offset, screen_width - new_width)
    new_y = min(y + random_y_offset, screen_height - new_height)

    logger.debug(f"Setting window position as ({new_x},{new_y})...")

    driver.set_window_position(new_x, new_y)
    sleep(get_random_sleep(0.1, 0.5) * config.behavior.wait_factor)


def _get_driver_exe_path() -> str:
    """Get the path for the chromedriver executable to avoid downloading and patching each time

    :rtype: str
    :returns: Absoulute path of the chromedriver executable
    """

    platform = sys.platform
    prefix = "undetected"
    exe_name = "chromedriver%s"

    if platform.endswith("win32"):
        exe_name %= ".exe"
    if platform.endswith(("linux", "linux2")):
        exe_name %= ""
    if platform.endswith("darwin"):
        exe_name %= ""

    if platform.endswith("win32"):
        dirpath = "~/appdata/roaming/undetected_chromedriver"
    elif "LAMBDA_TASK_ROOT" in os.environ:
        dirpath = "/tmp/undetected_chromedriver"
    elif platform.startswith(("linux", "linux2")):
        dirpath = "~/.local/share/undetected_chromedriver"
    elif platform.endswith("darwin"):
        dirpath = "~/Library/Application Support/undetected_chromedriver"
    else:
        dirpath = "~/.undetected_chromedriver"

    driver_exe_folder = os.path.abspath(os.path.expanduser(dirpath))
    driver_exe_path = os.path.join(driver_exe_folder, "_".join([prefix, exe_name]))

    return driver_exe_path


def _execute_stealth_js_code(driver: Union[undetected_chromedriver.Chrome, seleniumbase.Driver]):
    """Execute the stealth JS code to prevent detection

    Signature changes can be tested by loading the following addresses
    - https://browserleaks.com/canvas
    - https://browserleaks.com/webrtc
    - https://browserleaks.com/webgl

    :type driver: Union[undetected_chromedriver.Chrome, seleniumbase.Driver]
    :param driver: WebDriver instance
    """

    stealth_js = r"""
    (() => {
    // 1) Random vendor/platform/WebGL info
    const vendors = ["Intel Inc.","NVIDIA Corporation","AMD","Google Inc."];
    const renderers = ["ANGLE (Intel® Iris™ Graphics)","ANGLE (NVIDIA GeForce)","WebKit WebGL"];
    const vendor = vendors[Math.floor(Math.random()*vendors.length)];
    const renderer = renderers[Math.floor(Math.random()*renderers.length)];
    Object.defineProperty(navigator, "vendor", { get: ()=>vendor });
    Object.defineProperty(navigator, "platform", { get: ()=>["Win32","Linux x86_64","MacIntel"][Math.floor(Math.random()*3)] });

    // 2) Canvas 2D noise
    const rawToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
        const ctx = this.getContext("2d");
        const image = ctx.getImageData(0,0,this.width,this.height);
        for(let i=0;i<image.data.length;i+=4){
        const noise = (Math.random()-0.5)*2; // -1..+1
        image.data[i]   = image.data[i]+noise;    // R
        image.data[i+1] = image.data[i+1]+noise;  // G
        image.data[i+2] = image.data[i+2]+noise;  // B
        }
        ctx.putImageData(image,0,0);
        return rawToDataURL.apply(this,[type,...args]);
    };

    // 3) Canvas toBlob noise
    const rawToBlob = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toBlob = function(cb, type, quality) {
        const ctx = this.getContext("2d");
        const image = ctx.getImageData(0,0,this.width,this.height);
        for(let i=0;i<image.data.length;i+=4){
        const noise = (Math.random()-0.5)*2;
        image.data[i]   += noise;
        image.data[i+1] += noise;
        image.data[i+2] += noise;
        }
        ctx.putImageData(image,0,0);
        return rawToBlob.call(this,cb,type,quality);
    };

    // 4) WebGL patch: vendor/renderer
    const getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if(param === 37445) return vendor;    // UNMASKED_VENDOR_WEBGL
        if(param === 37446) return renderer;  // UNMASKED_RENDERER_WEBGL
        return getParam.call(this,param);
    };

    // 5) WebRTC IP leak prevention
    const OrigRTCPeer = window.RTCPeerConnection;
    window.RTCPeerConnection = function(cfg, opts) {
        const pc = new OrigRTCPeer(cfg, opts);
        const origCreateOffer = pc.createOffer;
        pc.createOffer = function() {
        return origCreateOffer.apply(this).then(o => {
            o.sdp = o.sdp.replace(/^a=candidate:.+$/gm,"");
            return o;
        });
        };
        return pc;
    };
    window.RTCPeerConnection.prototype = OrigRTCPeer.prototype;
    })();
    """

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})
