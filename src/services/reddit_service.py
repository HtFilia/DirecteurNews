import aiohttp
from typing import Dict, List, Any, Set
from datetime import datetime
import json
import os
import random
from utils.logger import setup_logger
from croniter import croniter
import html
from urllib.parse import urlencode

class RedditService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.shown_posts_file = "shown_reddit_posts.json"
        self.logger = setup_logger('RedditService')
        self.shown_posts: Set[str] = self._load_shown_posts()
        
        # API configuration
        self.user_agent_version = random.randint(0, 4)  # Initialize random version
        
        # Serious loop configuration
        self.serious_cron_schedule = self.config['reddit']['serious'].get('schedule', '0 */4 * * *')
        self.serious_cron_iter = croniter(self.serious_cron_schedule, datetime.now())
        self.next_serious_check = datetime.now()  # Immediate first run
        self.serious_subreddits = self.config['reddit']['serious'].get('subreddits', [])
        
        # Fun loop configuration
        self.fun_cron_schedule = self.config['reddit']['fun'].get('schedule', '0 * * * *')
        self.fun_cron_iter = croniter(self.fun_cron_schedule, datetime.now())
        self.next_fun_check = datetime.now()  # Immediate first run
        self.fun_subreddits = self.config['reddit']['fun'].get('subreddits', [])
        
        self.is_first_run = True
        self.logger.info("RedditService initialized with serious and fun loops")

    def _load_shown_posts(self) -> Set[str]:
        try:
            if os.path.exists(self.shown_posts_file):
                with open(self.shown_posts_file, 'r') as f:
                    data = json.load(f)
                    # Check if we need to reset for a new day or if it's a new bot session
                    last_reset_date = datetime.fromisoformat(data.get('last_reset_date', '2000-01-01')).date()
                    if last_reset_date < datetime.now().date() or self.is_first_run:
                        self.logger.info("Resetting shown Reddit posts for new day or bot restart")
                        return set()
                    posts = set(data.get('posts', []))
                    self.logger.info(f"Loaded {len(posts)} shown Reddit posts from file")
                    return posts
            self.logger.info("No shown Reddit posts file found, starting with empty set")
            return set()
        except Exception as e:
            self.logger.error(f"Error loading shown Reddit posts: {e}")
            return set()

    def _save_shown_posts(self):
        try:
            data = {
                'last_reset_date': datetime.now().isoformat(),
                'posts': list(self.shown_posts)
            }
            with open(self.shown_posts_file, 'w') as f:
                json.dump(data, f)
            self.logger.debug(f"Saved {len(self.shown_posts)} shown Reddit posts to file")
        except Exception as e:
            self.logger.error(f"Error saving shown Reddit posts: {e}")

    def _get_user_agent(self) -> str:
        """Generate a Firefox-like user agent string with random version."""
        # 1 in 2000 chance to update the version
        if random.randint(1, 2000) == 1:
            self.user_agent_version = random.randint(0, 4)
        
        version = 130 + self.user_agent_version
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}.0) Gecko/20100101 Firefox/{version}.0"

    async def _fetch_subreddit_posts(self, subreddit: str, sort: str = "hot", top_period: str = "day", limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit using direct API calls."""
        headers = {
            'User-Agent': self._get_user_agent()
        }
        
        # Build the query parameters
        params = {}
        if sort == "top":
            params['t'] = top_period
        
        # Construct the URL
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        if params:
            url += f"?{urlencode(params)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    self.logger.error(f"Error fetching posts from r/{subreddit}: HTTP {response.status}")
                    return []
                
                data = await response.json()
                posts = []
                
                for child in data['data']['children']:
                    post = child['data']
                    
                    # Skip stickied and pinned posts
                    if post.get('stickied') or post.get('pinned'):
                        continue
                    
                    # Skip if we've already shown this post
                    if post['id'] in self.shown_posts:
                        continue
                    
                    # Handle crossposts
                    target_url = post['url']
                    target_domain = post['domain']
                    if post.get('crosspost_parent_list'):
                        parent = post['crosspost_parent_list'][0]
                        target_url = f"https://www.reddit.com{parent['permalink']}"
                        target_domain = f"r/{parent['subreddit']}"
                    
                    # Create post object
                    post_data = {
                        'id': post['id'],
                        'title': html.unescape(post['title']),
                        'link': f"https://www.reddit.com{post['permalink']}",
                        'content': post.get('selftext', ''),
                        'image_url': post['url'] if post['url'].endswith(('.jpg', '.jpeg', '.png', '.gif')) else None,
                        'source': f"r/{subreddit}",
                        'score': post['ups'],
                        'comments': post['num_comments'],
                        'target_url': target_url,
                        'target_domain': target_domain,
                        'is_crosspost': bool(post.get('crosspost_parent_list')),
                        'flair': post.get('link_flair_text'),
                        'created': datetime.fromtimestamp(post['created'])
                    }
                    
                    # Add thumbnail if available
                    if post.get('thumbnail') and post['thumbnail'] not in ['self', 'default', 'nsfw']:
                        post_data['thumbnail_url'] = html.unescape(post['thumbnail'])
                    
                    posts.append(post_data)
                
                return posts[:limit]

    async def check_subreddits(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Check subreddits and return both serious and fun posts.
        Returns: (serious_posts, fun_posts)
        """
        try:
            current_time = datetime.now()
            serious_posts = []
            fun_posts = []

            # Check serious subreddits
            if not self.is_first_run and current_time < self.next_serious_check:
                self.logger.debug(f"Not time for serious Reddit check yet. Next check at {self.next_serious_check}")
            else:
                if self.is_first_run:
                    self.is_first_run = False
                self.next_serious_check = self.serious_cron_iter.get_next(datetime)
                self.logger.debug(f"Next serious Reddit check scheduled for {self.next_serious_check}")
                serious_posts = await self._check_serious_subreddits()

            # Check fun subreddits
            if not self.is_first_run and current_time < self.next_fun_check:
                self.logger.debug(f"Not time for fun Reddit check yet. Next check at {self.next_fun_check}")
            else:
                self.next_fun_check = self.fun_cron_iter.get_next(datetime)
                self.logger.debug(f"Next fun Reddit check scheduled for {self.next_fun_check}")
                fun_posts = await self._check_fun_subreddits()

            return serious_posts, fun_posts
        except Exception as e:
            self.logger.error(f"Error in check_subreddits: {e}")
            return [], []

    async def _check_serious_subreddits(self) -> List[Dict[str, Any]]:
        """Check serious subreddits for new posts, returning only the top post from each subreddit."""
        new_posts = []
        
        for subreddit in self.serious_subreddits:
            try:
                self.logger.debug(f"Checking serious subreddit: {subreddit['name']}")
                # Only fetch the top post
                posts = await self._fetch_subreddit_posts(subreddit['name'], sort="hot", limit=1)
                
                if posts and posts[0]['link'] not in self.shown_posts:
                    post = posts[0]
                    post['source'] = subreddit['name']
                    post['icon'] = subreddit['icon']
                    new_posts.append(post)
                    self.shown_posts.add(post['link'])
                    self.logger.debug(f"Found new top post from r/{subreddit['name']}")
                else:
                    self.logger.debug(f"No new top post from r/{subreddit['name']}")
                    
            except Exception as e:
                self.logger.error(f"Error checking subreddit r/{subreddit['name']}: {e}")
        
        # Save shown posts to file
        self._save_shown_posts()
        
        return new_posts

    async def _check_fun_subreddits(self) -> List[Dict[str, Any]]:
        """Check fun subreddits for new posts, returning only the top post from each subreddit."""
        new_posts = []
        
        for subreddit in self.fun_subreddits:
            try:
                self.logger.debug(f"Checking fun subreddit: {subreddit['name']}")
                # Only fetch the top post
                posts = await self._fetch_subreddit_posts(subreddit['name'], sort="hot", limit=1)
                
                if posts and posts[0]['link'] not in self.shown_posts:
                    post = posts[0]
                    post['source'] = subreddit['name']
                    post['icon'] = subreddit['icon']
                    new_posts.append(post)
                    self.shown_posts.add(post['link'])
                    self.logger.debug(f"Found new top post from r/{subreddit['name']}")
                else:
                    self.logger.debug(f"No new top post from r/{subreddit['name']}")
                    
            except Exception as e:
                self.logger.error(f"Error checking subreddit r/{subreddit['name']}: {e}")
        
        # Save shown posts to file
        self._save_shown_posts()
        
        return new_posts 