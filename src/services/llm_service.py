from openai import OpenAI
from typing import Dict, List, Any, Optional
import json
from utils.logger import setup_logger

class LLMService:
    def __init__(self, config: Dict[str, Any]):
        self.logger = setup_logger('LLMService')
        self.config = config['llm']
        self.client = OpenAI(
            api_key=self.config['api_key'],
            base_url="https://api.deepseek.com"
        )
        self.logger.info("LLMService initialized")

    def select_best_article(self, articles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not articles:
            self.logger.warning("No articles provided for selection")
            return None

        self.logger.info(f"Selecting best article from {len(articles)} articles")
        prompt = self._create_selection_prompt(articles)
        
        try:
            self.logger.debug("Sending request to LLM")
            response = self.client.chat.completions.create(
                model=self.config['model'],
                messages=[
                    {"role": "system", "content": "You are an expert at selecting the most relevant and high-quality news articles based on user preferences."},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )
            
            return self._parse_selection_response(response, articles)
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            return None

    def _create_selection_prompt(self, articles: List[Dict[str, Any]]) -> str:
        self.logger.debug("Creating selection prompt")
        return f"""Select the best article from the following list based on the specified topics and preferences.
The best article should be the most relevant to the topics and have the highest quality content.

Articles: {json.dumps(articles, indent=2)}
Topics: {json.dumps(self.config['key_topics'], indent=2)}

Respond in JSON format with the following structure:
{{
    "selected_article_index": 0,
    "reason": "Brief explanation of why this article was selected",
    "relevance_score": 0.0-1.0,
    "matching_topics": ["topic1", "topic2"]
}}"""

    def _parse_selection_response(self, response: Any, articles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            content = response.choices[0].message.content
            self.logger.debug(f"Received LLM response: {content}")
            
            # Remove markdown code block formatting if present
            if content.startswith('```json'):
                content = content[7:]  # Remove ```json
            if content.endswith('```'):
                content = content[:-3]  # Remove ```
            content = content.strip()
            
            selection = json.loads(content)
            selected_index = selection.get('selected_article_index')
            if selected_index is not None and 0 <= selected_index < len(articles):
                self.logger.debug(f"Selected article index: {selected_index}")
                return articles[selected_index]
            self.logger.warning("Invalid article index in LLM response")
            return None
        except (KeyError, json.JSONDecodeError, IndexError) as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            return None
