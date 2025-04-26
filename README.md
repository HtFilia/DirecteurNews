# News Sharer Discord Bot

A Discord bot that shares news articles from RSS feeds, web scraping, and Reddit posts based on topic relevance.

## Features

- RSS feed monitoring
- Web page scraping
- Reddit post monitoring
- Topic-based filtering using LLM
- Discord integration

## Setup

1. Create and activate virtual environment:

```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On Unix or MacOS
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure the bot:

   - Copy `config/config.yaml` and update with your credentials
   - Add your Discord bot token
   - Configure RSS feeds, Reddit credentials, and topics
   - Add your LLM API key

4. Run the bot:

```bash
python src/main.py
```

## Configuration

Edit `config/config.yaml` to customize:

- Discord channel and token
- RSS feeds to monitor
- Reddit subreddits and settings
- Topics and keywords
- LLM settings

## Requirements

- Python 3.12+
- Discord bot token
- Reddit API credentials
- LLM API key (Deepseek)

## License

MIT
