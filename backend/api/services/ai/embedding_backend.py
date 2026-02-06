"""
Azure OpenAI Embedding Backend

Implements the EmbeddingBackend interface using Azure OpenAI.
"""
import time
import logging
from typing import List, Optional

from api.services.ai.backends import EmbeddingBackend, EmbeddingResult
from api.core.config import settings

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)

# Try to import OpenAI
try:
    from openai import AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AzureOpenAI = None


class AzureEmbeddingBackend(EmbeddingBackend):
    """
    Azure OpenAI embedding backend.
    
    Uses Azure OpenAI API to generate embeddings with automatic batching and retries.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_version: Optional[str] = None,
        batch_size: int = 16,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        """
        Initialize Azure embedding backend.
        
        Args:
            api_key: Azure OpenAI API key (defaults to settings)
            endpoint: Azure OpenAI endpoint (defaults to settings)
            model: Embedding model/deployment name (defaults to settings)
            api_version: API version (defaults to settings)
            batch_size: Number of texts to embed per API call
            max_retries: Maximum retry attempts
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.api_key = api_key or settings.AZURE_OPENAI_API_KEY
        self.endpoint = endpoint or str(settings.AZURE_OPENAI_ENDPOINT or "")
        self.model = model or settings.AZURE_OPENAI_EMBED_MODEL
        self.api_version = api_version or settings.AZURE_OPENAI_API_VERSION
        self.batch_size = batch_size or getattr(settings, "EMBED_BATCH_SIZE", 16)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._client: Optional[AzureOpenAI] = None
        self._dimension: int = 1536  # Default for text-embedding-3-small
        
        # Try to initialize client
        if self.is_available():
            self._init_client()
    
    def _init_client(self) -> None:
        """Initialize the Azure OpenAI client."""
        if not OPENAI_AVAILABLE:
            return
        
        try:
            self._client = AzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.endpoint,
                api_version=self.api_version,
            )
        except Exception as e:
            log_msg = f"Failed to initialize Azure OpenAI client: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            self._client = None
    
    @property
    def dimension(self) -> int:
        """Return embedding dimension (1536 for text-embedding-3-small)."""
        return self._dimension
    
    def is_available(self) -> bool:
        """Check if the backend is available and configured."""
        if not OPENAI_AVAILABLE:
            return False
        
        return bool(self.api_key and self.endpoint and self.model)
    
    def embed(self, texts: List[str]) -> EmbeddingResult:
        """
        Generate embeddings for a list of texts.
        
        Uses batching to handle large inputs efficiently.
        """
        if not self.is_available():
            raise RuntimeError("Azure embedding backend not available")
        
        if not self._client:
            self._init_client()
            if not self._client:
                raise RuntimeError("Failed to initialize Azure OpenAI client")
        
        all_embeddings = []
        total_tokens = 0
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_result = self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_result.embeddings)
            total_tokens += batch_result.token_count
        
        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self.model or "",
            token_count=total_tokens,
        )
    
    def _embed_batch_with_retry(self, texts: List[str]) -> EmbeddingResult:
        """Embed a batch of texts with retry logic."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self._client.embeddings.create(
                    input=texts,
                    model=self.model,
                )
                
                embeddings = [item.embedding for item in response.data]
                token_count = response.usage.total_tokens if response.usage else 0
                
                return EmbeddingResult(
                    embeddings=embeddings,
                    model=self.model or "",
                    token_count=token_count,
                )
                
            except Exception as e:
                last_error = e
                log_msg = f"Embedding batch failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                if HAS_LOGURU:
                    logger.warning(log_msg)
                else:
                    logger.warning(log_msg)
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
        
        raise RuntimeError(f"Embedding failed after {self.max_retries} attempts: {last_error}")
    
    def embed_single(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        result = self.embed([text])
        return result.embeddings[0] if result.embeddings else []


class LocalEmbeddingBackend(EmbeddingBackend):
    """
    Local embedding backend using sentence-transformers.
    
    Useful for development/testing without Azure credentials.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize local embedding backend.
        
        Args:
            model_name: Hugging Face model name
        """
        self.model_name = model_name
        self._model = None
        self._dimension = 384  # Default for all-MiniLM-L6-v2
        
        self._try_init()
    
    def _try_init(self) -> None:
        """Try to initialize the model."""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
        except ImportError:
            self._model = None
        except Exception as e:
            log_msg = f"Failed to load sentence transformer: {e}"
            if HAS_LOGURU:
                logger.warning(log_msg)
            else:
                logger.warning(log_msg)
            self._model = None
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def is_available(self) -> bool:
        return self._model is not None
    
    def embed(self, texts: List[str]) -> EmbeddingResult:
        if not self._model:
            raise RuntimeError("Local embedding model not available")
        
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        
        return EmbeddingResult(
            embeddings=[emb.tolist() for emb in embeddings],
            model=self.model_name,
            token_count=0,  # Not tracked for local models
        )
    
    def embed_single(self, text: str) -> List[float]:
        result = self.embed([text])
        return result.embeddings[0] if result.embeddings else []


def get_embedding_backend() -> EmbeddingBackend:
    """
    Get the configured embedding backend.
    
    Returns Azure backend if configured, otherwise tries local backend.
    """
    # Try Azure first
    azure_backend = AzureEmbeddingBackend()
    if azure_backend.is_available():
        return azure_backend
    
    # Fall back to local
    local_backend = LocalEmbeddingBackend()
    if local_backend.is_available():
        log_msg = "Azure embeddings not available, using local sentence-transformers"
        if HAS_LOGURU:
            logger.warning(log_msg)
        else:
            logger.warning(log_msg)
        return local_backend
    
    raise RuntimeError(
        "No embedding backend available. "
        "Configure Azure OpenAI or install sentence-transformers."
    )
