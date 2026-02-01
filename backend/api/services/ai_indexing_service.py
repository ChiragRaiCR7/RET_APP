"""
AI Indexing Service
Handles indexing of XML groups into Chroma vector DB for RAG
Session-specific indexing - cleared on logout
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import tempfile

logger = logging.getLogger(__name__)

# Try to import chroma
chromadb = None
Settings = None
CHROMA_AVAILABLE = False

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("Chroma not available - AI indexing disabled")

# Try to import embeddings
SentenceTransformer = None
EMBEDDINGS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers not available")


@dataclass
class IndexStats:
    """Index statistics"""
    groups_indexed: int
    total_documents: int
    total_tokens: int


class SessionIndexer:
    """Per-session indexer for Chroma DB"""
    
    def __init__(self, session_id: str, runtime_root: Path):
        self.session_id = session_id
        self.runtime_root = runtime_root
        self.session_dir = runtime_root / "sessions" / session_id
        self.index_dir = self.session_dir / "ai_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.index_dir / "index_metadata.json"
        
        self.client = None
        self.collection = None
        self.model = None
        self.indexed_groups: Set[str] = set()
        
        self._load_metadata()
        self._init_chroma()
        self._init_embeddings()
    
    def _load_metadata(self):
        """Load indexed groups from metadata"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file) as f:
                    data = json.load(f)
                    self.indexed_groups = set(data.get("indexed_groups", []))
            except Exception as e:
                logger.error(f"Failed to load index metadata: {e}")
    
    def _save_metadata(self):
        """Save indexed groups to metadata"""
        try:
            metadata = {
                "indexed_groups": list(self.indexed_groups),
                "session_id": self.session_id
            }
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f)
        except Exception as e:
            logger.error(f"Failed to save index metadata: {e}")
    
    def _init_chroma(self):
        """Initialize Chroma client for this session"""
        if not CHROMA_AVAILABLE:
            logger.warning("Chroma not available")
            return
        
        if not chromadb:
            logger.warning("chromadb module not loaded")
            return
        
        try:
            # Use session-specific persistent storage
            chroma_path = str(self.index_dir / "chroma")
            
            # Create settings object properly
            try:
                if Settings:
                    settings = Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=chroma_path,
                        anonymized_telemetry=False,
                    )
                    self.client = chromadb.Client(settings)
                else:
                    # Fallback for different chromadb versions
                    self.client = chromadb.PersistentClient(path=chroma_path)
            except (TypeError, AttributeError):
                # Fallback for different chromadb versions
                try:
                    self.client = chromadb.PersistentClient(path=chroma_path)
                except:
                    self.client = chromadb.Client()
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name=f"session_{self.session_id}",
                metadata={"description": f"Session {self.session_id} AI index"}
            )
            
            logger.info(f"Initialized Chroma collection for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma: {e}")
            self.client = None
            self.collection = None
    
    def _init_embeddings(self):
        """Initialize embedding model"""
        if not EMBEDDINGS_AVAILABLE:
            logger.warning("Embeddings not available")
            return
        
        try:
            if not SentenceTransformer:
                logger.warning("SentenceTransformer not available")
                return
            
            # Use a small, efficient model
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Initialized embeddings model")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            self.model = None
    
    def index_groups(
        self,
        groups_data: Dict[str, List[Dict]],
        session_root: Path,
    ) -> IndexStats:
        """
        Index XML groups from scan results
        
        Args:
            groups_data: Dict of group_name -> list of file info dicts
            session_root: Root directory containing extracted XMLs
        
        Returns:
            IndexStats with results
        """
        if not self.collection or not self.model:
            raise RuntimeError("Chroma or embeddings not initialized")
        
        doc_count = 0
        token_count = 0
        groups_indexed = 0
        
        from api.services.xml_processing_service import iter_xml_record_chunks
        
        for group_name, files in groups_data.items():
            if group_name in self.indexed_groups:
                logger.info(f"Group {group_name} already indexed, skipping")
                continue
            
            group_doc_count = 0
            
            for file_info in files:
                file_path = session_root / file_info.get("path", "")
                
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    continue
                
                # Stream records from this file
                try:
                    for record_idx, record_tag, record_text in iter_xml_record_chunks(
                        str(file_path),
                        auto_detect=True,
                        max_records=1000,
                    ):
                        # Generate embedding
                        try:
                            embedding = self.model.encode(record_text).tolist()
                        except Exception as e:
                            logger.warning(f"Failed to embed record: {e}")
                            continue
                        
                        # Store in Chroma
                        doc_id = f"{group_name}_{file_info.get('filename')}_{record_idx}"
                        
                        self.collection.add(
                            ids=[doc_id],
                            embeddings=[embedding],
                            documents=[record_text],
                            metadatas=[{
                                "group": group_name,
                                "file": file_info.get("filename"),
                                "record_idx": record_idx,
                                "record_tag": record_tag,
                            }]
                        )
                        
                        group_doc_count += 1
                        doc_count += 1
                        token_count += len(record_text.split())
                
                except Exception as e:
                    logger.error(f"Failed to index file {file_path}: {e}")
                    continue
            
            if group_doc_count > 0:
                self.indexed_groups.add(group_name)
                groups_indexed += 1
                logger.info(f"Indexed group {group_name} with {group_doc_count} documents")
        
        # Persist changes (for older chromadb versions)
        if self.client:
            try:
                if hasattr(self.client, 'persist'):
                    self.client.persist()
            except Exception as e:
                logger.warning(f"Failed to persist Chroma: {e}")
        
        # Save metadata
        self._save_metadata()
        
        return IndexStats(
            groups_indexed=groups_indexed,
            total_documents=doc_count,
            total_tokens=token_count
        )
    
    def query(self, query_text: str, n_results: int = 5) -> List[Dict]:
        """
        Query indexed documents
        
        Returns:
            List of matching documents with metadata
        """
        if not self.collection or not self.model:
            return []
        
        try:
            query_embedding = self.model.encode(query_text).tolist()
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted = []
            if results:
                documents = results.get("documents", [])
                metadatas_list = results.get("metadatas", [])
                distances_list = results.get("distances", [])
                
                if documents and isinstance(documents, list) and len(documents) > 0:
                    docs = documents[0] if isinstance(documents[0], list) else []
                    metas = metadatas_list[0] if metadatas_list and isinstance(metadatas_list[0], list) else []
                    dists = distances_list[0] if distances_list and isinstance(distances_list[0], list) else []
                    
                    for i, doc in enumerate(docs):
                        formatted.append({
                            "document": doc,
                            "metadata": metas[i] if i < len(metas) else {},
                            "distance": dists[i] if i < len(dists) else 0.0,
                        })
            
            return formatted
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []
    
    def get_indexed_groups(self) -> List[str]:
        """Get list of indexed groups"""
        return sorted(list(self.indexed_groups))
    
    def clear(self):
        """Clear all indexed data for this session"""
        try:
            # Delete collection
            if self.client and self.collection:
                self.client.delete_collection(name=f"session_{self.session_id}")
            
            # Delete index directory
            import shutil
            if self.index_dir.exists():
                shutil.rmtree(self.index_dir)
            
            self.indexed_groups.clear()
            self.collection = None
            
            # Reinitialize
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._init_chroma()
            
            logger.info(f"Cleared index for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")


# Global session indexers cache
_SESSION_INDEXERS: Dict[str, SessionIndexer] = {}


def get_session_indexer(session_id: str, runtime_root: Path) -> SessionIndexer:
    """Get or create indexer for session"""
    if session_id not in _SESSION_INDEXERS:
        _SESSION_INDEXERS[session_id] = SessionIndexer(session_id, runtime_root)
    return _SESSION_INDEXERS[session_id]


def clear_session_indexer(session_id: str):
    """Clear and remove session indexer"""
    if session_id in _SESSION_INDEXERS:
        try:
            _SESSION_INDEXERS[session_id].clear()
        except Exception as e:
            logger.error(f"Error clearing session indexer: {e}")
        finally:
            del _SESSION_INDEXERS[session_id]
