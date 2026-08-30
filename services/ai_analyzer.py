import json
import logging
import re
import httpx
from openai import AsyncOpenAI
from config import config

logger = logging.getLogger("AIAnalyzer")

class AIAnalyzer:
    def __init__(self):
        http_client = httpx.AsyncClient(proxy=config.HTTP_PROXY) if config.HTTP_PROXY else None
        self.client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            http_client=http_client,
        )

    async def extract_highlights_and_meta(self, transcript: list[dict], mode: str = "short") -> dict:
        if not transcript:
            return {"movie_title": "Неизвестно", "tiktok_caption": "", "highlights": []}

        formatted_lines = [
            f"[{b['start']}s - {b['end']}s] {b['text']}"
            for b in transcript
            if b.get("text")
        ]
        full_text = "\n".join(formatted_lines)

        if mode == "long":
            duration_rule = "Each clip MUST be between 2 and 5 minutes long (120 to 300 seconds)."
            clips_count = 3
        else:
            duration_rule = "Each clip MUST be between 30 and 60 seconds long."
            clips_count = config.MAX_CLIPS

        prompt = f"""
You are an expert viral video producer and TikTok SMM manager.
Analyze this transcript from a movie/series/show and:
1. Identify the name of the movie/cartoon/series.
2. Generate an engaging TikTok caption with the format:
"Название фильма/сериала: [НАЗВАНИЕ] 🍿

[2-3 предложения интригующего описания момента]

#фильмы #кино #нарезки #shorts #fyp #рек #[хештег_названия]"
3. Select {clips_count} continuous viral highlight clips.
Rule for duration: {duration_rule}

Return ONLY a JSON object matching this schema:
{{
  "movie_title": "Title here",
  "tiktok_caption": "Caption here",
  "highlights": [
    {{
      "start": 12.5,
      "end": 55.0,
      "title": "Brief title of the moment"
    }}
  ]
}}

Transcript:
{full_text}
"""
        try:
            response = await self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional video editor. Output only valid JSON without markdown formatting."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            raw_content = response.choices[0].message.content.strip()
            logger.info(f"Ответ от LLM:\n{raw_content}")

            json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if json_match:
                parsed_data = json.loads(json_match.group(0))
            else:
                parsed_data = json.loads(raw_content)

            highlights = []
            for item in parsed_data.get("highlights", []):
                if "start" in item and "end" in item:
                    item["start"] = float(item["start"])
                    item["end"] = float(item["end"])
                    if item["end"] > item["start"]:
                        highlights.append(item)

            return {
                "movie_title": parsed_data.get("movie_title", "Неизвестно"),
                "tiktok_caption": parsed_data.get("tiktok_caption", ""),
                "highlights": highlights,
            }

        except Exception as e:
            logger.error(f"Ошибка при анализе LLM: {str(e)}", exc_info=True)
            return {"movie_title": "Неизвестно", "tiktok_caption": "", "highlights": []}