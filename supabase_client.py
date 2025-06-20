import os
from datetime import datetime
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from logger import logger

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class SupabaseClient:
    """Supabase client for sending click data to database"""

    def __init__(self) -> None:
        # Use IP address directly to bypass DNS issues, but with HTTP to avoid SSL
        self.supabase_url = os.getenv("SUPABASE_URL", "").replace("https://", "http://").replace("gjhrgslbhajjpfudcegf.supabase.co", "104.18.38.10")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.enabled = bool(self.supabase_url and self.supabase_key)
        
        # Create session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def save_click(
        self,
        site_url: str,
        category: str,
        query: str,
        click_time: str,
        browser_id: Optional[str] = None,
        proxy_used: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Save click data to Supabase

        :type site_url: str
        :param site_url: Link clicked
        :type category: str
        :param category: Link category as Ad, Non-ad, or Shopping
        :type query: str
        :param query: Search query used
        :type click_time: str
        :param click_time: Time of the click in hh:mm:ss format
        :type browser_id: Optional[str]
        :param browser_id: ID of the browser instance
        :type proxy_used: Optional[str]
        :param proxy_used: Proxy used for the click
        :type user_agent: Optional[str]
        :param user_agent: User agent used for the click
        """

        if not self.enabled:
            logger.debug("Supabase is not configured, skipping...")
            return

        # replace spaces with %20 in urls
        site_url = site_url.replace(" ", "%20")

        try:
            # date will be in DD-MM-YYYY format.
            click_date = datetime.now().strftime("%d-%m-%Y")

            data = {
                "click_date": click_date,
                "click_time": click_time,
                "site_url": site_url,
                "query": query,
                "category": category,
                "browser_id": browser_id,
                "proxy_used": proxy_used,
                "user_agent": user_agent,
                "created_at": datetime.now().isoformat()
            }

            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }

            # Try with longer timeout and better error handling
            response = self.session.post(
                f"{self.supabase_url}/rest/v1/ads_clicker_log",
                json=data,
                headers=headers,
                timeout=30
            )

            if response.status_code == 201:
                log_details = f"{click_date} {click_time}, {site_url}, {query}, {category}"
                logger.debug(f"Click log ({log_details}) was sent to Supabase.")
            else:
                logger.warning(f"Failed to send to Supabase: {response.status_code} - {response.text}")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Supabase: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error to Supabase: {e}")
        except Exception as exp:
            logger.error(f"Error sending to Supabase: {exp}")

    def query_clicks(self, click_date: str) -> Optional[list[tuple[str, str, str]]]:
        """Query given date from Supabase and return results grouped by the site_url

        :type click_date: str
        :param click_date: Date to query clicks
        :rtype: list
        :returns: List of (site_url, clicks, category, click_time, query) tuples for the given date
        """

        if not self.enabled:
            logger.debug("Supabase is not configured, skipping...")
            return None

        logger.debug(f"Querying click results for {click_date} from Supabase...")

        try:
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json"
            }

            # Supabase query to group by site_url, query, category
            query_params = {
                "select": "site_url,category,click_time,query",
                "click_date": f"eq.{click_date}"
            }

            response = requests.get(
                f"{self.supabase_url}/rest/v1/ads_clicker_log",
                headers=headers,
                params=query_params,
                timeout=10
            )

            if response.status_code == 200:
                results = response.json()
                
                if not results:
                    logger.debug(f"Couldn't found any click data for {click_date} in Supabase!")
                    return None
                
                # Group by site_url, query, category and count
                grouped_results = {}
                for row in results:
                    key = (row['site_url'], row['query'], row['category'])
                    if key not in grouped_results:
                        grouped_results[key] = {
                            'count': 0,
                            'click_time': row['click_time']
                        }
                    grouped_results[key]['count'] += 1
                
                # Convert to expected format
                formatted_results = []
                for (site_url, query, category), data in grouped_results.items():
                    formatted_results.append((
                        site_url,
                        str(data['count']),
                        category,
                        data['click_time'],
                        query
                    ))
                
                return formatted_results
            else:
                logger.warning(f"Failed to query Supabase: {response.status_code} - {response.text}")
                return None

        except Exception as exp:
            logger.error(f"Error querying Supabase: {exp}")
            return None 