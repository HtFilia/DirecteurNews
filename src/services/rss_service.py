import feedparser
from typing import Dict, List, Any, Set, Tuple
import asyncio
from datetime import datetime
import html
import json
import os
import random
from utils.logger import setup_logger
from bs4 import BeautifulSoup
from croniter import croniter

class RSSService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.shown_articles_file = "shown_articles.json"
        self.logger = setup_logger('RSSService')
        self.shown_articles: Set[str] = self._load_shown_articles()
        
        # Serious loop configuration
        self.serious_cron_schedule = self.config['rss']['serious'].get('schedule', '0 8-23/4 * * *')
        self.serious_cron_iter = croniter(self.serious_cron_schedule, datetime.now())
        self.next_serious_check = datetime.now()  # Immediate first run
        self.serious_feeds = self.config['rss']['serious'].get('feeds', [])
        
        # Fun loop configuration
        self.fun_cron_schedule = self.config['rss']['fun'].get('schedule', '0 8-23 * * *')
        self.fun_cron_iter = croniter(self.fun_cron_schedule, datetime.now())
        self.next_fun_check = datetime.now()  # Immediate first run
        self.fun_feeds = self.config['rss']['fun'].get('feeds', [])
        
        self.is_first_run = True
        self.logger.info("RSSService initialized with serious and fun loops")

    def _load_shown_articles(self) -> Set[str]:
        try:
            if os.path.exists(self.shown_articles_file):
                with open(self.shown_articles_file, 'r') as f:
                    data = json.load(f)
                    # Check if we need to reset for a new day or if it's a new bot session
                    last_reset_date = datetime.fromisoformat(data.get('last_reset_date', '2000-01-01')).date()
                    if last_reset_date < datetime.now().date() or self.is_first_run:
                        self.logger.info("Resetting shown articles for new day or bot restart")
                        return set()
                    articles = set(data.get('articles', []))
                    self.logger.info(f"Loaded {len(articles)} shown articles from file")
                    return articles
            self.logger.info("No shown articles file found, starting with empty set")
            return set()
        except Exception as e:
            self.logger.error(f"Error loading shown articles: {e}")
            return set()

    def _save_shown_articles(self):
        try:
            data = {
                'last_reset_date': datetime.now().isoformat(),
                'articles': list(self.shown_articles)
            }
            with open(self.shown_articles_file, 'w') as f:
                json.dump(data, f)
            self.logger.debug(f"Saved {len(self.shown_articles)} shown articles to file")
        except Exception as e:
            self.logger.error(f"Error saving shown articles: {e}")

    def _is_today(self, date_str: str) -> bool:
        try:
            # Try to parse the date string
            if not date_str:
                return False
                
            # Handle different date formats
            for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z', '%Y-%m-%dT%H:%M:%S%z']:
                try:
                    article_date = datetime.strptime(date_str, fmt)
                    return article_date.date() == datetime.now().date()
                except ValueError:
                    continue
            
            # If we couldn't parse the date, assume it's not today
            return False
        except Exception as e:
            self.logger.error(f"Error parsing date {date_str}: {e}")
            return False

    async def check_feeds(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Check feeds and return both serious and fun articles.
        Returns: (serious_articles, fun_articles)
        """
        try:
            current_time = datetime.now()
            serious_articles = []
            fun_articles = []

            # Check serious feeds
            if not self.is_first_run and current_time < self.next_serious_check:
                self.logger.debug(f"Not time for serious check yet. Next check at {self.next_serious_check}")
            else:
                if self.is_first_run:
                    self.is_first_run = False
                self.next_serious_check = self.serious_cron_iter.get_next(datetime)
                self.logger.debug(f"Next serious check scheduled for {self.next_serious_check}")
                serious_articles = await self._check_serious_feeds()

            # Check fun feeds
            if not self.is_first_run and current_time < self.next_fun_check:
                self.logger.debug(f"Not time for fun check yet. Next check at {self.next_fun_check}")
            else:
                self.next_fun_check = self.fun_cron_iter.get_next(datetime)
                self.logger.debug(f"Next fun check scheduled for {self.next_fun_check}")
                fun_articles = await self._check_fun_feeds()

            return serious_articles, fun_articles
        except Exception as e:
            self.logger.error(f"Error in check_feeds: {e}")
            return [], []

    async def _check_serious_feeds(self) -> List[Dict[str, Any]]:
        new_articles = []
        seen_links = set()  # Track unique article links
        
        for feed in self.serious_feeds:
            if feed and feed.get('url', None):
                self.logger.debug(f"Checking serious feed: {feed['url']}")
                articles = await self._parse_feed(feed['url'], feed.get('name', feed['url']))
                # Filter out already shown articles, today's articles, and duplicates
                articles = [
                    article for article in articles 
                    if (article['link'] not in self.shown_articles 
                        and article['link'] not in seen_links
                        and self._is_today(article['published']))
                ]
                # Add new unique articles
                for article in articles:
                    seen_links.add(article['link'])
                self.logger.debug(f"Found {len(articles)} new serious articles from {feed['url']}")
                new_articles.extend(articles)

        # Get the 3 most recent articles from all feeds
        new_articles.sort(key=lambda x: x.get('published', ''), reverse=True)
        recent_articles = new_articles[:3]

        # Mark these articles as shown
        for article in recent_articles:
            self.shown_articles.add(article['link'])
        self._save_shown_articles()

        return recent_articles

    async def _check_fun_feeds(self) -> List[Dict[str, Any]]:
        new_articles = []
        seen_links = set()  # Track unique article links
        
        for feed in self.fun_feeds:
            if feed and feed.get('url', None):
                self.logger.debug(f"Checking fun feed: {feed['url']}")
                articles = await self._parse_feed(feed['url'], feed.get('name', feed['url']))
                # Filter out already shown articles and duplicates
                articles = [
                    article for article in articles 
                    if (article['link'] not in self.shown_articles 
                        and article['link'] not in seen_links)
                ]
                # Add new unique articles
                for article in articles:
                    seen_links.add(article['link'])
                self.logger.debug(f"Found {len(articles)} new fun articles from {feed['url']}")
                new_articles.extend(articles)

        # Select one random article
        if new_articles:
            random_article = random.choice(new_articles)
            self.shown_articles.add(random_article['link'])
            self._save_shown_articles()
            return [random_article]
        return []

    async def _parse_feed(self, feed_url: str, feed_name: str) -> List[Dict[str, Any]]:
        try:
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)
            
            articles = []
            for entry in feed.entries:
                # Get image URL if available
                image_url = None
                if hasattr(entry, 'media_content'):
                    for media in entry.media_content:
                        if 'url' in media:
                            image_url = media['url']
                            break
                elif hasattr(entry, 'links'):
                    for link in entry.links:
                        if link.get('type', '').startswith('image/'):
                            image_url = link.get('href')
                            break
                    
                # Decode HTML entities and clean HTML tags from title and content
                title = html.unescape(entry.title)
                content = html.unescape(entry.summary if hasattr(entry, 'summary') else '')
                
                # Clean HTML tags from content
                soup = BeautifulSoup(content, 'html.parser')
                content = soup.get_text(separator=' ', strip=True)
                
                articles.append({
                    'title': title,
                    'link': entry.link,
                    'published': entry.published,
                    'content': content,
                    'image_url': image_url,
                    'source': feed_name,
                })
            
            self.logger.debug(f"Parsed {len(articles)} articles from {feed_url}")
            return articles
        except Exception as e:
            self.logger.error(f"Error parsing feed {feed_url}: {e}")
            return [] 

    def _get_category_color(self, article: Dict[str, Any]) -> int:
        """
        Determine the color code based on the article's category or source.
        Returns a Discord color code (integer).
        """
        # Map of categories to Discord color codes
        category_colors = {
            'technology': 0x3498db,  # Blue
            'finance': 0x2ecc71,     # Green
            'politics': 0xe74c3c,    # Red
            'sports': 0xf39c12,      # Orange
            'entertainment': 0x9b59b6, # Purple
            'science': 0x1abc9c,     # Turquoise
            'health': 0xe67e22,      # Carrot
            'world': 0x34495e,       # Dark Blue
            'business': 0x27ae60,    # Dark Green
            'default': 0x95a5a6      # Gray
        }

        # Try to determine category from source URL
        source = article['source'].lower()
        if 'tech' in source or 'technology' in source:
            return category_colors['technology']
        elif 'finance' in source or 'economy' in source or 'market' in source:
            return category_colors['finance']
        elif 'politics' in source or 'government' in source:
            return category_colors['politics']
        elif 'sports' in source:
            return category_colors['sports']
        elif 'entertainment' in source or 'arts' in source or 'culture' in source:
            return category_colors['entertainment']
        elif 'science' in source:
            return category_colors['science']
        elif 'health' in source or 'medical' in source:
            return category_colors['health']
        elif 'world' in source or 'international' in source:
            return category_colors['world']
        elif 'business' in source:
            return category_colors['business']
        
        # If no category matches, use the default color
        return category_colors['default'] 