"""
ChromaDB Vector Store Backend

Implements the VectorStoreBackend interface using ChromaDB.
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from api.services.ai.backends import VectorStoreBackend, Document, QueryResult
from api.core.config import settings

try:
    from loguru import logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    logger = logging.getLogger(__name__)

# Try to import ChromaDB
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None


class ChromaVectorStore(VectorStoreBackend):
    """
    ChromaDB vector store backend.
    
    Provides session-isolated vector storage with persistent or in-memory modes.
    """
    
    def __init__(
        self,
        collection_name: str,
        persist_directory: Optional[Path] = None,
        distance_metric: str = "cosine",
    ):
        """
        Initialize ChromaDB vector store.
        
        Args:
            collection_name: Name of the collection
            persist_directory: Path for persistent storage (None for in-memory)
            distance_metric: Distance function ('cosine', 'l2', 'ip')
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.distance_metric = distance_metric
        
        self._client = None
        self._collection = None
        
        if CHROMA_AVAILABLE:
            self._init_client()
    
    def _init_client(self) -> None:
        """Initialize the ChromaDB client and collection."""
        try:
            if self.persist_directory:
                # Persistent storage
                self.persist_directory.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self.persist_directory),
                    settings=ChromaSettings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ),
                )
            else:
                # In-memory storage
                self._client = chromadb.Client()
            
            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": self.distance_metric},
            )
            
        except Exception as e:
            log_msg = f"Failed to initialize ChromaDB: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            self._client = None
            self._collection = None
    
    def is_available(self) -> bool:
        """Check if ChromaDB is available."""
        return CHROMA_AVAILABLE and self._collection is not None
    
    def upsert(self, documents: List[Document]) -> int:
        """Insert or update documents in the collection."""
        if not self._collection:
            raise RuntimeError("ChromaDB collection not available")
        
        if not documents:
            return 0
        
        # Prepare data for upsert
        ids = [doc.id for doc in documents]
        embeddings = [doc.embedding for doc in documents if doc.embedding]
        metadatas = [doc.metadata for doc in documents]
        contents = [doc.content for doc in documents]
        
        try:
            if embeddings and len(embeddings) == len(documents):
                self._collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=contents,
                )
            else:
                # Upsert without embeddings (ChromaDB will generate)
                self._collection.upsert(
                    ids=ids,
                    metadatas=metadatas,
                    documents=contents,
                )
            
            return len(documents)
            
        except Exception as e:
            log_msg = f"ChromaDB upsert failed: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            raise
    
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """Query the collection for similar documents."""
        if not self._collection:
            raise RuntimeError("ChromaDB collection not available")
        
        try:
            # Build query parameters
            query_params = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            
            # Add filters if provided
            if filters:
                query_params["where"] = self._build_where_clause(filters)
            
            results = self._collection.query(**query_params)
            
            # Parse results
            documents = []
            scores = []
            
            if results and results.get("ids") and results["ids"][0]:
                ids = results["ids"][0]
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                
                for i, doc_id in enumerate(ids):
                    content = docs[i] if i < len(docs) else ""
                    metadata = metas[i] if i < len(metas) else {}
                    distance = distances[i] if i < len(distances) else 0.0
                    
                    # Convert distance to similarity score (for cosine: 1 - distance)
                    score = 1.0 - distance if self.distance_metric == "cosine" else -distance
                    
                    documents.append(Document(
                        id=doc_id,
                        content=content,
                        metadata=metadata,
                    ))
                    scores.append(score)
            
            return QueryResult(
                documents=documents,
                scores=scores,
                total_count=self.count(),
            )
            
        except Exception as e:
            log_msg = f"ChromaDB query failed: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            return QueryResult(documents=[], scores=[], total_count=0)
    
    def _build_where_clause(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build ChromaDB where clause from filters."""
        # Handle simple equality filters
        if all(not isinstance(v, dict) for v in filters.values()):
            if len(filters) == 1:
                key, value = next(iter(filters.items()))
                return {key: {"$eq": value}}
            else:
                # Multiple conditions require $and
                return {
                    "$and": [
                        {k: {"$eq": v}} for k, v in filters.items()
                    ]
                }
        
        # Already in ChromaDB format
        return filters
    
    def delete(self, ids: List[str]) -> int:
        """Delete documents by ID."""
        if not self._collection:
            raise RuntimeError("ChromaDB collection not available")
        
        if not ids:
            return 0
        
        try:
            self._collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            log_msg = f"ChromaDB delete failed: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            return 0
    
    def delete_by_filter(self, filters: Dict[str, Any]) -> int:
        """Delete documents matching a filter."""
        if not self._collection:
            raise RuntimeError("ChromaDB collection not available")
        
        try:
            where_clause = self._build_where_clause(filters)
            
            # ChromaDB requires IDs or where clause
            # First query to get matching IDs
            results = self._collection.get(
                where=where_clause,
                include=["metadatas"],
            )
            
            if results and results.get("ids"):
                self._collection.delete(ids=results["ids"])
                return len(results["ids"])
            
            return 0
            
        except Exception as e:
            log_msg = f"ChromaDB delete by filter failed: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
            return 0
    
    def clear(self) -> None:
        """Clear all documents from the collection."""
        if not self._client:
            return
        
        try:
            # Delete and recreate collection
            self._client.delete_collection(self.collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": self.distance_metric},
            )
        except Exception as e:
            log_msg = f"ChromaDB clear failed: {e}"
            if HAS_LOGURU:
                logger.error(log_msg)
            else:
                logger.error(log_msg)
    
    def count(self) -> int:
        """Return the number of documents in the collection."""
        if not self._collection:
            return 0
        
        try:
            return self._collection.count()
        except Exception:
            return 0
    
    def close(self) -> None:
        """Close the client connection."""
        # ChromaDB doesn't require explicit closure for most operations
        # but we reset references to allow garbage collection
        self._collection = None
        self._client = None


def get_session_vector_store(
    session_id: str,
    user_id: str,
) -> ChromaVectorStore:
    """
    Get a session-isolated vector store.
    
    Creates a ChromaDB collection specific to the session.
    """
    from api.services.storage_service import get_session_dir
    
    # Collection name unique to session
    collection_name = f"session_{session_id}"
    
    # Persist directory in session folder
    session_dir = get_session_dir(session_id)
    persist_dir = session_dir / "ai_index" / "chroma"
    
    return ChromaVectorStore(
        collection_name=collection_name,
        persist_directory=persist_dir,
    )
