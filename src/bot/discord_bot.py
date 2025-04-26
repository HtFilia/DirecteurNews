import discord
import yaml
import asyncio
from typing import Dict, Any, List
from services.rss_service import RSSService
from services.reddit_service import RedditService
from services.llm_service import LLMService
from datetime import datetime
from utils.logger import setup_logger

class NewsSharerBot:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.logger = setup_logger('NewsSharerBot')
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.config = self.load_config(config_path)
        self.rss_service = RSSService(self.config)
        self.reddit_service = RedditService(self.config)
        self.llm_service = LLMService(self.config)
        self.setup_events()
        self.logger.info("NewsSharerBot initialized")

    def load_config(self, config_path: str) -> Dict[str, Any]:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.logger.info("Configuration loaded successfully")
                return config
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            raise

    def setup_events(self):
        @self.client.event
        async def on_ready():
            self.logger.info(f'Logged in as {self.client.user}')
            # Start the feed checking loop
            self.client.loop.create_task(self.check_feeds())

    async def check_feeds(self):
        self.logger.info("Starting feed checking loop")
        error_count = 0
        max_backoff = 3600  # Maximum backoff time in seconds (1 hour)
        base_wait = 60  # Base wait time in seconds
        
        while True:
            try:
                # Get both serious and fun articles from RSS
                serious_articles, fun_articles = [], []
                # serious_articles, fun_articles = await self.rss_service.check_feeds()
                
                # Get both serious and fun posts from Reddit
                serious_posts, fun_posts = await self.reddit_service.check_subreddits()
                
                # Process serious RSS articles
                if serious_articles:
                    # Use LLM to select the best article
                    best_article = self.llm_service.select_best_article(serious_articles)
                    
                    if best_article:
                        self.logger.info(f"Selected serious RSS article: {best_article['title']}")
                        await self.send_article(best_article, self.config['discord']['channel_ids']["serious_rss"])

                # Process fun RSS articles
                if fun_articles:
                    # For fun articles, we just take the first one (it's already randomly selected)
                    fun_article = fun_articles[0]
                    self.logger.info(f"Selected fun RSS article: {fun_article['title']}")
                    await self.send_article(fun_article, self.config['discord']['channel_ids']["fun_rss"])

                # Process serious Reddit posts
                if serious_posts:
                    # Get configuration limits
                    total_limit = self.config['reddit']['serious'].get('total_limit', 10)
                    per_subreddit_limit = self.config['reddit']['serious'].get('per_subreddit_limit', 3)
                    
                    # Group and limit posts
                    all_posts = []
                    posts_by_subreddit = {}
                    
                    # First, group posts by subreddit and apply per-subreddit limit
                    for post in serious_posts:
                        subreddit = post['source']
                        if subreddit not in posts_by_subreddit:
                            posts_by_subreddit[subreddit] = []
                        if len(posts_by_subreddit[subreddit]) < per_subreddit_limit:
                            posts_by_subreddit[subreddit].append(post)
                    
                    # Then, collect all posts and sort by score
                    for posts in posts_by_subreddit.values():
                        all_posts.extend(posts)
                    
                    # Sort all posts by score and apply total limit
                    all_posts.sort(key=lambda x: x['score'], reverse=True)
                    top_posts = all_posts[:total_limit]
                    
                    # Send all posts in a single message
                    await self.send_reddit_posts(top_posts, self.config['discord']['channel_ids']["serious_reddit"], True)

                # Process fun Reddit posts
                if fun_posts:
                    # Get configuration limits
                    total_limit = self.config['reddit']['fun'].get('total_limit', 5)
                    per_subreddit_limit = self.config['reddit']['fun'].get('per_subreddit_limit', 2)
                    
                    # Group and limit posts
                    all_posts = []
                    posts_by_subreddit = {}
                    
                    # First, group posts by subreddit and apply per-subreddit limit
                    for post in fun_posts:
                        subreddit = post['source']
                        if subreddit not in posts_by_subreddit:
                            posts_by_subreddit[subreddit] = []
                        if len(posts_by_subreddit[subreddit]) < per_subreddit_limit:
                            posts_by_subreddit[subreddit].append(post)
                    
                    # Then, collect all posts and sort by score
                    for posts in posts_by_subreddit.values():
                        all_posts.extend(posts)
                    
                    # Sort all posts by score and apply total limit
                    all_posts.sort(key=lambda x: x['score'], reverse=True)
                    top_posts = all_posts[:total_limit]
                    
                    # Send all posts in a single message
                    await self.send_reddit_posts(top_posts, self.config['discord']['channel_ids']["fun_reddit"], False)
                
                # Reset error count on successful run
                error_count = 0
                
                # Wait for the next check interval
                await asyncio.sleep(4 * 60 * 60)  # Check every 4 hours
                
            except Exception as e:
                self.logger.error(f"Error in feed checking loop: {e}")
                
                # Calculate backoff time with exponential growth
                backoff_time = min(base_wait * (2 ** error_count), max_backoff)
                error_count += 1
                
                self.logger.warning(f"Backing off for {backoff_time} seconds (attempt {error_count})")
                await asyncio.sleep(backoff_time)

    async def send_reddit_posts(self, posts: List[Dict[str, Any]], channel_id: int, is_serious: bool = False):
        """Send Reddit posts to the specified channel, one message per post."""
        if not posts:
            return

        channel = self.client.get_channel(channel_id)
        if not channel:
            self.logger.error(f"Could not find channel {channel_id} to send message")
            return

        for post in posts:
            # Create embed for this post
            embed = discord.Embed(
                title=post['title'],
                url=post['link'],
                color=0xFF4500,  # Reddit orange
                timestamp=datetime.now()
            )
            
            # Add subreddit information
            embed.set_author(name=f"r/{post['source']}")
            
            # Add content if available
            if post['content']:
                content_preview = post['content'][:200] + "..." if len(post['content']) > 200 else post['content']
                embed.description = content_preview
            
            # Add engagement metrics
            embed.add_field(
                name="Engagement",
                value=f"⬆️ {post['score']} | 💬 {post['comments']}",
                inline=True
            )
            
            # Add crosspost information if available
            if post['is_crosspost']:
                embed.add_field(
                    name="Crosspost",
                    value=f"[Original Post]({post['target_url']})",
                    inline=True
                )
            
            # Add flair if available
            if post['flair']:
                embed.add_field(
                    name="Flair",
                    value=post['flair'],
                    inline=True
                )
            
            # Add thumbnail if available
            if post.get('thumbnail_url'):
                embed.set_thumbnail(url=post['thumbnail_url'])
            
            # Send the embed
            await channel.send(embed=embed)
            # Add a small delay between messages to avoid rate limiting
            await asyncio.sleep(1)

    async def send_article(self, article: Dict[str, Any], channel_id: int):
        try:
            # Get the color based on the article's category
            color = self.rss_service._get_category_color(article)
            
            # Create an embed for the article
            embed = discord.Embed(
                title=article['title'],
                url=article['link'],
                description=article['content'][:200] + '...' if len(article['content']) > 200 else article['content'],
                color=color,
                timestamp=datetime.now()
            )
            
            # Add image if available
            if article.get('image_url'):
                embed.set_image(url=article['image_url'])
            
            # Add source information
            embed.set_footer(text=f"Source: {article['source']}")
            
            # Add Reddit-specific fields if present
            if 'score' in article and 'comments' in article:
                embed.add_field(name="Reddit Stats", value=f"⬆️ {article['score']} | 💬 {article['comments']}", inline=True)
            
            # Send the embed to the channel
            channel = self.client.get_channel(channel_id)
            if channel:
                self.logger.info(f"Sending article to channel {channel.name}")
                await channel.send(embed=embed)
            else:
                self.logger.error(f"Could not find channel {channel_id} to send message")
        except Exception as e:
            self.logger.error(f"Error sending article: {e}")

    def run(self):
        self.logger.info("Starting bot")
        self.client.run(self.config['discord']['token']) 