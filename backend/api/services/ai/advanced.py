"""
Advanced AI Strategy - Full-featured RAG with hybrid retrieval.

This strategy provides the most sophisticated AI capabilities including:
- Hybrid retrieval (semantic + lexical)
- Dynamic context building
- Citation enforcement
- Conversation memory
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

from api.services.ai.base import (
    BaseAIService,
    ChatResponse,
    Citation,
    IndexingStats,
)
from api.core.config import settings

logger = logging.getLogger(__name__)

# Configuration constants
CHUNK_TARGET_CHARS = 10_000
CHUNK_MAX_CHARS = 14_000
CELL_MAX_CHARS = 250
EMBED_BATCH_SIZE = 16
RETRIEVAL_TOP_K = 16
MAX_CONTEXT_CHARS = 40_000
AI_TEMPERATURE = 0.65
AI_MAX_TOKENS = 4000
HYBRID_ALPHA = 0.70  # Weight for semantic similarity
HYBRID_BETA = 0.30   # Weight for lexical similarity
LEX_TOP_N_TOKENS = 80

# Try to import dependencies
chromadb = None
AzureOpenAI = None
RecursiveCharacterTextSplitter = None
Document = None

try:
    import chromadb
except ImportError:
    pass

try:
    from openai import AzureOpenAI
except ImportError:
    pass

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        pass

try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        pass

ADVANCED_AVAILABLE = chromadb is not None and AzureOpenAI is not None


def extract_query_tokens(query: str) -> List[str]:
    """Extract searchable tokens from query"""
    pattern = re.compile(r"[A-Za-z0-9_./\-]{2,64}")
    tokens = pattern.findall((query or "").lower())
    
    seen = set()
    result = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
            if len(result) >= LEX_TOP_N_TOKENS:
                break
    return result


def compute_lexical_score(query_tokens: List[str], document: str) -> float:
    """Compute lexical matching score (0.0-1.0)"""
    if not query_tokens:
        return 0.0
    
    body = (document or "").lower()
    hits = sum(1 for t in query_tokens if t in body)
    return float(hits / len(query_tokens))


def vector_similarity_from_distance(distance: Optional[float]) -> float:
    """Convert distance metric to similarity (0.0-1.0)"""
    if distance is None:
        return 0.0
    return float(max(0.0, min(1.0, 1.0 - float(distance))))


class AdvancedAIStrategy(BaseAIService):
    """
    Advanced AI service with hybrid retrieval and sophisticated RAG.
    """
    
    def __init__(self, session_id: str, persist_dir: Optional[str] = None):
        super().__init__(session_id, persist_dir)
        self.openai_client = None
        self.chroma_client = None
        self.collection = None
        self.conversation_history: List[Dict[str, str]] = []
    
    def initialize(self) -> bool:
        """Initialize advanced AI components"""
        if not ADVANCED_AVAILABLE:
            logger.warning("Advanced AI dependencies not available")
            self._initialized = False
            return False
        
        try:
            # Initialize OpenAI client
            if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
                self.openai_client = AzureOpenAI(
                    api_key=settings.AZURE_OPENAI_API_KEY,
                    api_version=settings.AZURE_OPENAI_API_VERSION or "2024-02-15-preview",
                    azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT),
                )
            
            # Initialize Chroma
            self._init_chroma()
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Advanced AI service: {e}")
            self._initialized = False
            return False
    
    def _init_chroma(self) -> None:
        """Initialize Chroma client and collection"""
        if not chromadb or not self.persist_dir:
            return
        
        try:
            chroma_path = str(self.persist_dir / "chroma_db")
            
            try:
                self.chroma_client = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=chromadb.Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ) if hasattr(chromadb, 'Settings') else None
                )
            except (TypeError, AttributeError):
                self.chroma_client = chromadb.Client()
            
            safe_name = f"adv_{self.session_id}".replace("-", "_")[:63]
            self.collection = self.chroma_client.get_or_create_collection(
                name=safe_name,
                metadata={"session_id": self.session_id, "strategy": "advanced"}
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize Chroma: {e}")
    
    def is_available(self) -> bool:
        """Check if service is available"""
        return (
            ADVANCED_AVAILABLE
            and self.openai_client is not None
            and self.collection is not None
        )
    
    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings with batching"""
        if not self.openai_client or not settings.AZURE_OPENAI_EMBED_MODEL:
            return []
        
        all_embeddings = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            try:
                response = self.openai_client.embeddings.create(
                    input=batch,
                    model=settings.AZURE_OPENAI_EMBED_MODEL,
                )
                all_embeddings.extend([item.embedding for item in response.data])
            except Exception as e:
                logger.error(f"Embedding batch failed: {e}")
                all_embeddings.extend([[0.0] * 1536 for _ in batch])
        
        return all_embeddings
    
    def _chat_completion(self, system: str, user: str) -> str:
        """Get chat completion from OpenAI"""
        if not self.openai_client or not settings.AZURE_OPENAI_CHAT_MODEL:
            return "OpenAI not configured"
        
        try:
            response = self.openai_client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            return f"Error: {str(e)}"
    
    def index_documents(
        self,
        files: List[Path],
        groups: Optional[Dict[str, List[Path]]] = None,
    ) -> IndexingStats:
        """Index documents with advanced chunking"""
        stats = IndexingStats()
        
        if not self.is_available():
            stats.errors.append("Service not available")
            return stats
        
        try:
            documents = []
            metadatas = []
            ids = []
            total_size = 0
            groups_seen = set()
            
            for file_path in files:
                if not file_path.exists():
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    total_size += len(content.encode('utf-8'))
                    
                    # Determine group
                    group = "default"
                    if groups:
                        for g, gfiles in groups.items():
                            if file_path in gfiles:
                                group = g
                                break
                    groups_seen.add(group)
                    
                    # Advanced chunking
                    chunks = self._smart_chunk(content, file_path.name)
                    
                    for i, chunk in enumerate(chunks):
                        doc_id = f"{self.session_id}-{file_path.stem}-{i}"
                        documents.append(chunk)
                        metadatas.append({
                            "source": file_path.name,
                            "group": group,
                            "session_id": self.session_id,
                            "chunk_index": i,
                        })
                        ids.append(doc_id)
                    
                    stats.documents_indexed += 1
                    
                except Exception as e:
                    stats.errors.append(f"Failed to process {file_path.name}: {str(e)}")
            
            if not documents:
                stats.errors.append("No documents to index")
                return stats
            
            # Get embeddings
            embeddings = self._get_embeddings(documents)
            
            # Add to collection
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            
            stats.chunks_created = len(documents)
            stats.total_size_mb = total_size / (1024 * 1024)
            stats.groups_processed = len(groups_seen)
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            stats.errors.append(str(e))
        
        return stats
    
    def _smart_chunk(self, content: str, filename: str) -> List[str]:
        """Smart chunking based on content type"""
        chunks = []
        
        # For CSV-like content, chunk by rows
        if filename.endswith('.csv') or '\t' in content[:1000]:
            lines = content.split('\n')
            current_chunk = []
            current_size = 0
            
            for line in lines:
                line_size = len(line)
                if current_size + line_size > CHUNK_TARGET_CHARS and current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(line)
                current_size += line_size
            
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
        else:
            # For other content, use character-based chunking
            for i in range(0, len(content), CHUNK_TARGET_CHARS):
                chunk = content[i:i + CHUNK_MAX_CHARS]
                if chunk.strip():
                    chunks.append(chunk)
        
        return chunks or [content[:CHUNK_MAX_CHARS]]
    
    def chat(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> ChatResponse:
        """Chat with hybrid retrieval"""
        if not self.is_available():
            return ChatResponse(
                answer="Advanced AI service is not available.",
                metadata={"error": "service_unavailable"}
            )
        
        try:
            # Extract query tokens for lexical matching
            query_tokens = extract_query_tokens(query)
            
            # Get query embedding
            query_embedding = self._get_embeddings([query])[0]
            
            # Retrieve from Chroma
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=RETRIEVAL_TOP_K,
            )
            
            if not results or not results.get("documents") or not results["documents"][0]:
                return ChatResponse(
                    answer="No relevant documents found.",
                    metadata={"error": "no_results"}
                )
            
            # Hybrid reranking
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            scored_results = []
            for doc, meta, dist in zip(docs, metadatas, distances):
                semantic_score = vector_similarity_from_distance(dist)
                lexical_score = compute_lexical_score(query_tokens, doc)
                hybrid_score = (HYBRID_ALPHA * semantic_score) + (HYBRID_BETA * lexical_score)
                scored_results.append((doc, meta, hybrid_score))
            
            # Sort by hybrid score
            scored_results.sort(key=lambda x: x[2], reverse=True)
            
            # Build context
            context_parts = []
            total_chars = 0
            for doc, meta, score in scored_results:
                if total_chars + len(doc) > MAX_CONTEXT_CHARS:
                    break
                context_parts.append(f"[{meta.get('source', 'unknown')}]\n{doc}")
                total_chars += len(doc)
            
            context_text = "\n\n---\n\n".join(context_parts)
            
            # Build system prompt
            system_prompt = (
                "You are an Enterprise Data Analyst assistant for RETv4. "
                "Answer using ONLY the provided context. "
                "Always cite your sources using [filename] notation. "
                "If information is not in the context, clearly state that. "
                "Be concise and accurate."
            )
            
            # Build conversation
            user_message = f"Context:\n{context_text}\n\n---\n\nQuestion: {query}"
            
            # Get answer
            answer = self._chat_completion(system_prompt, user_message)
            
            # Build citations
            citations = [
                Citation(
                    content=doc[:200] + "..." if len(doc) > 200 else doc,
                    source=meta.get("source", "unknown"),
                    score=score,
                    metadata=meta,
                )
                for doc, meta, score in scored_results[:5]
            ]
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": query})
            self.conversation_history.append({"role": "assistant", "content": answer})
            
            return ChatResponse(
                answer=answer,
                citations=citations,
                metadata={
                    "query": query,
                    "context_chunks": len(context_parts),
                    "retrieval_method": "hybrid",
                },
            )
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return ChatResponse(
                answer=f"An error occurred: {str(e)}",
                metadata={"error": str(e)},
            )
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history"""
        return self.conversation_history.copy()
    
    def clear_conversation_history(self) -> None:
        """Clear conversation history"""
        self.conversation_history.clear()
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        self.conversation_history.clear()
        self.collection = None
        self.chroma_client = None
        self.openai_client = None
        self._initialized = False
