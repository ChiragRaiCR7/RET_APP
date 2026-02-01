"""
ChromaDB Client for vector storage
Provides a clean interface for vector operations in RET App
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMA_AVAILABLE = False

logger = logging.getLogger(__name__)


class ChromaClient:
    """Wrapper class for ChromaDB operations"""
    
    def __init__(self, persist_dir: Optional[str] = None):
        """Initialize ChromaDB client with optional persistence"""
        self.client = None
        self.persist_dir = persist_dir
        
        if not CHROMA_AVAILABLE:
            logger.warning("ChromaDB not available. Install with: pip install chromadb")
            return
        
        try:
            if persist_dir:
                path = Path(persist_dir)
                path.mkdir(parents=True, exist_ok=True)
                self.client = chromadb.PersistentClient(path=str(path))
            else:
                self.client = chromadb.Client()
            logger.info("ChromaDB client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.client = None
    
    def get_or_create(self, name: str, metadata: Optional[Dict] = None) -> Optional[Any]:
        """Get or create a collection by name"""
        if not self.client:
            logger.warning("ChromaDB client not available")
            return None
        
        try:
            collection_metadata = metadata or {"hnsw:space": "cosine"}
            return self.client.get_or_create_collection(
                name=name,
                metadata=collection_metadata
            )
        except Exception as e:
            logger.error(f"Failed to get/create collection '{name}': {e}")
            return None
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection by name"""
        if not self.client:
            return False
        
        try:
            self.client.delete_collection(name)
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection '{name}': {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """List all collection names"""
        if not self.client:
            return []
        
        try:
            collections = self.client.list_collections()
            return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []


def get_client(session_dir: Path) -> Optional[Any]:
    """Get a ChromaDB client for a session directory"""
    if not CHROMA_AVAILABLE:
        return None
    
    try:
        path = session_dir / "chroma"
        path.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(path))
    except Exception as e:
        logger.error(f"Failed to create session Chroma client: {e}")
        return None


def get_collection(client: Any, user_id: str, session_id: str) -> Optional[Any]:
    """Get or create a collection for a user session"""
    if not client:
        return None
    
    try:
        name = f"ret_{user_id}_{session_id}"
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        logger.error(f"Failed to get/create collection: {e}")
        return None


def upsert(
    collection: Any,
    *,
    doc_id: str,
    embedding: List[float],
    document: str,
    metadata: Dict
) -> bool:
    """Upsert a document into the collection"""
    if not collection:
        return False
    
    try:
        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )
        return True
    except Exception as e:
        logger.error(f"Failed to upsert document '{doc_id}': {e}")
        return False


def query(
    collection: Any,
    query_embedding: List[float],
    *,
    top_k: int = 5,
    where: Optional[dict] = None
) -> List[Dict]:
    """Query the collection for similar documents"""
    if not collection:
        return []
    
    try:
        res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        
        out = []
        documents = res.get("documents", [[]])[0]
        metadatas = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]
        
        for doc, meta, dist in zip(documents, metadatas, distances):
            out.append({
                "document": doc,
                "metadata": meta,
                "distance": dist
            })
        
        return out
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return []


def bulk_add(
    collection: Any,
    *,
    ids: List[str],
    embeddings: List[List[float]],
    documents: List[str],
    metadatas: List[Dict]
) -> bool:
    """Add multiple documents to the collection"""
    if not collection:
        return False
    
    try:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return True
    except (TypeError, ValueError):
        # Try with numpy arrays for some chromadb versions
        try:
            import numpy as np
            collection.add(
                ids=ids,
                embeddings=np.array(embeddings, dtype=np.float32),
                documents=documents,
                metadatas=metadatas,
            )
            return True
        except Exception as e:
            logger.error(f"Bulk add failed with numpy: {e}")
            return False
    except Exception as e:
        logger.error(f"Bulk add failed: {e}")
        return False