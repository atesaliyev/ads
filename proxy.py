from pathlib import Path
from logger import logger

logger.info("PROXY.PY VERSION 3.0 RUNNING - DYNAMIC AUTH SCRIPT")

try:
    from selenium.webdriver import ChromeOptions
except ImportError:
    import sys
    packages_path = Path.cwd() / "env" / "Lib" / "site-packages"
    sys.path.insert(0, f"{packages_path}")
    from selenium.webdriver import ChromeOptions

from config_reader import config
from logger import logger
import requests

# ==================== PROXY BİLGİLERİ ====================
HC_HOST = "core-residential.evomi.com"
HC_PORT = 1000
HC_USER = "dersdelisi2"
HC_PASS = "cyOv4WS8RuTxg6rpn93U_country-TR"

def get_proxies() -> list[str]:
    """Get proxies from file, ignoring comments and empty lines."""
    filepath = Path(config.paths.proxy_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find proxy file: {filepath}")

    proxies = []
    with open(filepath, encoding="utf-8") as proxyfile:
        for line in proxyfile:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line.replace("'", "").replace('"', ""))

    if not proxies:
        raise SystemExit(f"No valid proxies found in {filepath}. Please add at least one proxy.")

    return proxies

def install_plugin(
    chrome_options: ChromeOptions,
    proxy_host: str,
    proxy_port: int,
    username: str,
    password: str,
    plugin_folder_name: str,
) -> None:
    """Install plugin on the fly for proxy authentication"""

    logger.info("<<<<< STATIC PROXY MODE ENGAGED: Bypassing all dynamic configs. >>>>>")

    manifest_json = """
{
    "version": "1.0.0",
    "manifest_version": 3,
    "name": "Chrome Proxy Authentication",
    "background": {
        "service_worker": "background.js"
    },
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "webRequest",
        "webRequestAuthProvider"
    ],
    "host_permissions": [
        "<all_urls>"
    ],
    "minimum_chrome_version": "108"
}
"""

    background_js_template = """
var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: {
            scheme: "%s",
            host: "%s",
            port: %s
        },
        bypassList: ["localhost"]
    }
};
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
"""

    auth_script = """
function callbackFn(details) {
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    { urls: ["<all_urls>"] },
    ['blocking']
);
""" % (HC_USER, HC_PASS)

    background_js = (background_js_template % (config.webdriver.proxy_scheme, HC_HOST, HC_PORT)) + auth_script

    header_script = """
chrome.webRequest.onBeforeSendHeaders.addListener(
    function(details) {
        details.requestHeaders.push({
            name: 'Accept-Language',
            value: 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        });
        return { requestHeaders: details.requestHeaders };
    },
    { urls: ["<all_urls>"] },
    ['blocking', 'requestHeaders']
);
"""
    background_js += header_script

    plugins_folder = Path.cwd() / "proxy_auth_plugin"
    plugins_folder.mkdir(exist_ok=True)

    plugin_folder = plugins_folder / plugin_folder_name
    logger.debug(f"Creating '{plugin_folder}' folder...")
    plugin_folder.mkdir(exist_ok=True)

    with open(plugin_folder / "manifest.json", "w") as manifest_file:
        manifest_file.write(manifest_json)

    with open(plugin_folder / "background.js", "w") as background_js_file:
        background_js_file.write(background_js)

    chrome_options.add_argument(f"--load-extension={plugin_folder}")

# ==================== IP TEST KISMI ====================
def test_proxy_connection():
    proxy_url = f"http://{HC_USER}:{HC_PASS}@{HC_HOST}:{HC_PORT}"
    proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }

    try:
        logger.info("Testing proxy connection...")
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        r.raise_for_status()
        print(f"✅ Proxy aktif. Görünen IP: {r.text}")
    except Exception as e:
        print("❌ Proxy bağlantısı başarısız:", str(e))

# ==================== ÇALIŞTIR ====================
if __name__ == "__main__":
    test_proxy_connection()
