from openai import AzureOpenAI
from api.core.config import settings

class AzureOpenAIClient:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(
            model=settings.AZURE_OPENAI_EMBED_MODEL,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    def chat(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content
