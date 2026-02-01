"""
Azure OpenAI Integration for RET App
"""
import logging
from typing import List, Optional

try:
    from openai import AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    AzureOpenAI = None
    OPENAI_AVAILABLE = False

from api.core.config import settings

logger = logging.getLogger(__name__)


class AzureOpenAIClient:
    """Wrapper for Azure OpenAI API with graceful degradation"""
    
    def __init__(self):
        self.client = None
        self.available = False
        
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI package not installed. AI features will be limited.")
            return
        
        # Check configuration
        if not all([
            settings.AZURE_OPENAI_API_KEY, 
            settings.AZURE_OPENAI_ENDPOINT, 
            settings.AZURE_OPENAI_API_VERSION
        ]):
            logger.warning(
                "Azure OpenAI configuration incomplete. "
                "Set AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_VERSION."
            )
            return
        
        try:
            self.client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT)
            )
            self.available = True
            logger.info("Azure OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {e}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts"""
        if not self.client or not self.available:
            raise RuntimeError("Azure OpenAI client not available")
        
        if not settings.AZURE_OPENAI_EMBED_MODEL:
            raise ValueError("AZURE_OPENAI_EMBED_MODEL not configured")
        
        try:
            # Process in batches to avoid token limits
            batch_size = 16
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                resp = self.client.embeddings.create(
                    model=settings.AZURE_OPENAI_EMBED_MODEL,
                    input=batch,
                )
                all_embeddings.extend([d.embedding for d in resp.data])
            
            return all_embeddings
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def chat(self, system: str, user: str) -> Optional[str]:
        """Get chat completion response"""
        if not self.client or not self.available:
            raise RuntimeError("Azure OpenAI client not available")
        
        deployment = settings.AZURE_OPENAI_CHAT_DEPLOYMENT or settings.AZURE_OPENAI_CHAT_MODEL
        if not deployment:
            raise ValueError("AZURE_OPENAI_CHAT_MODEL/CHAT_DEPLOYMENT not configured")
        
        try:
            resp = self.client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=settings.RET_AI_TEMPERATURE or 0.7,
                max_tokens=4000,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if Azure OpenAI is available"""
        return self.available and self.client is not None
