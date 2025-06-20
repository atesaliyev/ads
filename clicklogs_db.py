from datetime import datetime
from typing import Optional
from contextlib import contextmanager

import sqlite3

from logger import logger

# Import Supabase client
try:
    from supabase_client import SupabaseClient
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    SupabaseClient = None


DBCursor = sqlite3.Connection.cursor


class ClickLogsDB:
    """SQLite database to keep daily click logs for links

    Raises RuntimeError if database connection is not established.
    """

    def __init__(self) -> None:
        self._create_db_table()
        
        # Initialize Supabase client if available
        if SUPABASE_AVAILABLE:
            self.supabase_client = SupabaseClient()
        else:
            self.supabase_client = None

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
        """Save click_date, site_url, click_time, query, and category to database

        Raises RuntimeError if an error occurs during the save operation.

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

        # replace spaces with %20 in urls
        site_url = site_url.replace(" ", "%20")

        try:
            with self._clicklogs_db() as clicklogs_db_cursor:
                # date will be in DD-MM-YYYY format.
                click_date = datetime.now().strftime("%d-%m-%Y")

                clicklogs_db_cursor.execute(
                    "INSERT INTO clicklogs (click_date, click_time, site_url, query, category) VALUES (?, ?, ?, ?, ?)",
                    (click_date, click_time, site_url, query, category),
                )
                log_details = f"{click_date} {click_time}, {site_url}, {query}, {category}"
                logger.debug(f"Click log ({log_details}) was added to database.")

        except sqlite3.Error as exp:
            raise RuntimeError(exp) from exp

        # Also save to Supabase if available and configured
        if self.supabase_client:
            try:
                self.supabase_client.save_click(
                    site_url,
                    category,
                    query,
                    click_time,
                    browser_id,
                    proxy_used,
                    user_agent,
                )
            except Exception as exp:
                logger.warning(f"Failed to save to Supabase: {exp}")

    def query_clicks(self, click_date: str) -> Optional[list[tuple[str, str, str]]]:
        """Query given date in database and return results grouped by the site_url

        :type click_date: str
        :param click_date: Date to query clicks
        :rtype: list
        :returns: List of (site_url, clicks, category, click_time, query) tuples for the given date
        """

        logger.debug(f"Querying click results for {click_date}...")

        try:
            with self._clicklogs_db() as clicklogs_db_cursor:
                query = """
                    SELECT site_url, COUNT(*) as clicks, category, click_time, query
                    FROM clicklogs
                    WHERE click_date = ?
                    GROUP BY site_url, query, category;
                """
                clicklogs_db_cursor.execute(query, (click_date,))

                results = clicklogs_db_cursor.fetchall()

                if not results:
                    logger.debug(f"Couldn't found any click data for {click_date} in database!")
                    return None
                else:
                    return results

        except sqlite3.Error as exp:
            raise RuntimeError(exp) from exp

    def query_clicks_from_supabase(self, click_date: str) -> Optional[list[tuple[str, str, str]]]:
        """Query given date from Supabase and return results grouped by the site_url

        :type click_date: str
        :param click_date: Date to query clicks
        :rtype: list
        :returns: List of (site_url, clicks, category, click_time, query) tuples for the given date
        """

        if not self.supabase_client:
            logger.debug("Supabase client not available")
            return None

        return self.supabase_client.query_clicks(click_date)

    def _create_db_table(self) -> None:
        """Create table to store click_date, click_time, site_url, query, and category"""

        with self._clicklogs_db() as clicklogs_db_cursor:
            clicklogs_db_cursor.execute(
                """CREATE TABLE IF NOT EXISTS clicklogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    click_date TEXT NOT NULL,
                    click_time TEXT NOT NULL,
                    site_url TEXT NOT NULL,
                    query TEXT NOT NULL,
                    category TEXT NOT NULL
                );"""
            )

    @contextmanager
    def _clicklogs_db(self) -> DBCursor:
        """Context manager that returns clicklogs db cursor

        :rtype: sqlite3.Connection.cursor
        :returns: Database connection cursor
        """

        try:
            clicklogs_db = sqlite3.connect("clicklogs.db")
            yield clicklogs_db.cursor()

        except sqlite3.Error as exp:
            logger.error(exp)
            raise RuntimeError("Failed to connect to clicklogs database!") from exp

        finally:
            clicklogs_db.commit()
            clicklogs_db.close()
