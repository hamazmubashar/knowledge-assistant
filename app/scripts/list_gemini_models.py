from google import genai

from app.core.config import settings

client = genai.Client(api_key=settings.gemini_api_key)
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    if "generateContent" in actions:
        print(m.name)