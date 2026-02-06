"""
Lite AI Strategy - Lightweight AI service using direct Azure OpenAI and Chroma.

This is the simplest AI implementation, suitable for basic RAG use cases.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.services.ai.base import (
    BaseAIService,
    ChatResponse,
    Citation,
    IndexingStats,
)
from api.integrations.azure_openai import AzureOpenAIClient
from api.core.config import settings

logger = logging.getLogger(__name__)

# Try to import chromadb
chromadb = None
CHROMA_AVAILABLE = False

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    logger.warning("ChromaDB not available for LiteAIStrategy")


class LiteAIStrategy(BaseAIService):
    """
    Lightweight AI service without heavy dependencies.
    Uses Azure OpenAI directly with Chroma for RAG.
    """
    
    CHUNK_SIZE_ROWS = 20
    DEFAULT_TOP_K = 5
    
    def __init__(self, session_id: str, persist_dir: Optional[str] = None):
        super().__init__(session_id, persist_dir)
        self.openai: Optional[AzureOpenAIClient] = None
        self.chroma = None
        self.collection = None
    
    def initialize(self) -> bool:
        """Initialize OpenAI client and Chroma"""
        try:
            # Initialize OpenAI client
            self.openai = AzureOpenAIClient()
            if not self.openai.is_available():
                logger.warning("Azure OpenAI not available - AI features limited")
                self.openai = None
        except Exception as e:
            logger.warning(f"Could not initialize OpenAI client: {e}")
            self.openai = None
        
        # Initialize Chroma if available
        if CHROMA_AVAILABLE and chromadb and self.persist_dir:
            self._init_chroma()
        
        self._initialized = True
        return self.is_available()
    
    def is_available(self) -> bool:
        """Check if service is available"""
        return self.openai is not None and CHROMA_AVAILABLE
    
    def _init_chroma(self) -> None:
        """Initialize Chroma vector store"""
        if not chromadb:
            return
        
        try:
            chroma_path = str(self.persist_dir / "chroma_db")
            
            # Use PersistentClient for modern chromadb (>= 0.4.0)
            try:
                self.chroma = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=chromadb.Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ) if hasattr(chromadb, 'Settings') else None
                )
            except (TypeError, AttributeError):
                # Fallback for older versions
                try:
                    self.chroma = chromadb.Client(chromadb.Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=chroma_path,
                        anonymized_telemetry=False,
                    ))
                except Exception:
                    self.chroma = chromadb.Client()
            
            # Sanitize collection name
            safe_name = f"session_{self.session_id}".replace("-", "_")[:63]
            
            self.collection = self.chroma.get_or_create_collection(
                name=safe_name,
                metadata={"session_id": self.session_id}
            )
            logger.info(f"Initialized Chroma for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma: {e}")
            self.chroma = None
            self.collection = None
    
    def index_documents(
        self,
        files: List[Path],
        groups: Optional[Dict[str, List[Path]]] = None,
    ) -> IndexingStats:
        """Index CSV/text files into vector store"""
        stats = IndexingStats()
        
        if not CHROMA_AVAILABLE:
            stats.errors.append("ChromaDB not available")
            return stats
        
        if self.collection is None:
            self._init_chroma()
        
        if self.collection is None:
            stats.errors.append("ChromaDB collection could not be initialized")
            return stats
        
        if not self.openai:
            stats.errors.append("Azure OpenAI not configured")
            return stats
        
        try:
            documents = []
            metadatas = []
            ids = []
            total_size = 0
            
            for file_path in files:
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}")
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
                    
                    # Split into chunks
                    lines = content.split('\n')
                    for i in range(0, len(lines), self.CHUNK_SIZE_ROWS):
                        chunk = '\n'.join(lines[i:i+self.CHUNK_SIZE_ROWS])
                        if chunk.strip():
                            doc_id = f"{self.session_id}-{file_path.stem}-{i//self.CHUNK_SIZE_ROWS}"
                            documents.append(chunk)
                            metadatas.append({
                                "source": file_path.name,
                                "session_id": self.session_id,
                                "group": group,
                                "chunk_index": i // self.CHUNK_SIZE_ROWS,
                            })
                            ids.append(doc_id)
                    
                    stats.documents_indexed += 1
                    
                except Exception as e:
                    logger.error(f"Failed to read file {file_path}: {e}")
                    stats.errors.append(f"Failed to read {file_path.name}: {str(e)}")
            
            if not documents:
                stats.errors.append("No documents to index")
                return stats
            
            # Get embeddings
            logger.info(f"Getting embeddings for {len(documents)} chunks...")
            embeddings = self.openai.embed_texts(documents)
            
            # Add to Chroma
            self._add_to_chroma(documents, embeddings, metadatas, ids)
            
            stats.chunks_created = len(documents)
            stats.total_size_mb = total_size / (1024 * 1024)
            stats.groups_processed = len(set(m["group"] for m in metadatas))
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            stats.errors.append(str(e))
        
        return stats
    
    def _add_to_chroma(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        ids: List[str],
    ) -> None:
        """Add documents to Chroma with proper error handling"""
        try:
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
        except (TypeError, ValueError):
            try:
                import numpy as np
                self.collection.add(
                    documents=documents,
                    embeddings=np.array(embeddings, dtype=np.float32),
                    metadatas=metadatas,
                    ids=ids,
                )
            except (TypeError, ImportError):
                # Fallback: let Chroma generate embeddings
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )
    
    def chat(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> ChatResponse:
        """Chat with the AI using indexed documents"""
        if not self.openai:
            return ChatResponse(
                answer="Azure OpenAI is not available.",
                metadata={"error": "openai_unavailable"}
            )
        
        if not self.collection:
            return ChatResponse(
                answer="No documents have been indexed yet.",
                metadata={"error": "no_documents"}
            )
        
        try:
            # Get query embedding
            q_embed = self.openai.embed_texts([query])[0]
            
            # Query Chroma
            results = self.collection.query(
                query_embeddings=[q_embed],
                n_results=self.DEFAULT_TOP_K,
            )
            
            if not results or not results.get("documents") or not results["documents"][0]:
                return ChatResponse(
                    answer="No relevant documents found.",
                    metadata={"error": "no_results"}
                )
            
            # Build context
            contexts = results["documents"][0]
            context_text = "\n\n".join(contexts)
            
            # Build conversation with history
            system_prompt = (
                "You are a RETv4 assistant. Answer strictly using the provided context. "
                "Cite facts from the context. If information is not in the context, say so."
            )
            
            user_message = f"Context:\n{context_text}\n\nQuestion: {query}"
            
            # Get answer from OpenAI
            answer = self.openai.chat(system_prompt, user_message)
            
            # Build citations
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            citations = [
                Citation(
                    content=ctx[:200] + "..." if len(ctx) > 200 else ctx,
                    source=meta.get("source", "unknown"),
                    score=1.0 - dist if dist else 0.0,
                    metadata=meta,
                )
                for ctx, meta, dist in zip(contexts, metadatas, distances)
            ]
            
            return ChatResponse(
                answer=answer,
                citations=citations,
                metadata={"query": query, "context_chunks": len(contexts)},
            )
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return ChatResponse(
                answer=f"An error occurred: {str(e)}",
                metadata={"error": str(e)},
            )
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        self.collection = None
        self.chroma = None
        self._initialized = False
