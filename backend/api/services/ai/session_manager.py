"""
AI Service Manager
Manages Advanced RAG engine instances and auto-indexing per session.

Updated to use AdvancedRAGEngine with LangGraph for complete RAG workflow.
Session-specific vector stores are cleared on logout.
"""

import logging
from typing import Dict, Optional, Any, List
from pathlib import Path
import threading
from datetime import datetime
import json
import shutil

from api.core.config import settings

# Import both RAG engines for fallback support
try:
    from api.services.ai.advanced_rag_engine import (
        AdvancedRAGEngine,
        RAGResponse,
        create_advanced_rag_engine,
    )
    ADVANCED_RAG_AVAILABLE = True
except ImportError:
    ADVANCED_RAG_AVAILABLE = False

try:
    from api.services.ai.rag_engine import RAGEngine
    BASIC_RAG_AVAILABLE = True
except ImportError:
    BASIC_RAG_AVAILABLE = False

from api.services.ai.auto_indexer import AutoIndexer, IndexingProgress

logger = logging.getLogger(__name__)


class SessionAIManager:
    """
    Manages AI resources for a single session.
    Uses AdvancedRAGEngine for complete RAG workflow with:
    - Query transformation
    - Query routing 
    - Fusion retrieval (vector + lexical + summary)
    - Reranking
    - Citation-aware generation
    
    Session-specific vector stores are automatically cleared on logout.
    """
    
    def __init__(
        self,
        session_id: str,
        user_id: str,
        runtime_root: Path,
        use_advanced_rag: bool = True,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.runtime_root = Path(runtime_root)
        self.use_advanced_rag = use_advanced_rag and ADVANCED_RAG_AVAILABLE
        
        self.session_dir = self.runtime_root / "sessions" / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # AI metadata file
        self.metadata_path = self.session_dir / "ai_metadata.json"
        
        # Lazy initialization
        self._rag_engine = None  # Can be AdvancedRAGEngine or RAGEngine
        self._auto_indexer: Optional[AutoIndexer] = None
        self._lock = threading.Lock()
        
        # Chat history
        self._chat_history: List[Dict[str, Any]] = []
        
        # Load existing metadata
        self._load_metadata()
        
        logger.info(
            f"SessionAIManager initialized: session={session_id}, "
            f"advanced_rag={self.use_advanced_rag}"
        )
    
    def _load_metadata(self):
        """Load AI session metadata"""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._chat_history = data.get("chat_history", [])
            except Exception as e:
                logger.warning(f"Error loading AI metadata: {e}")
    
    def _save_metadata(self):
        """Save AI session metadata"""
        try:
            data = {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "chat_history": self._chat_history[-100:],  # Keep last 100 messages
                "updated_at": datetime.utcnow().isoformat(),
                "rag_type": "advanced" if self.use_advanced_rag else "basic",
            }
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving AI metadata: {e}")
    
    @property
    def rag_engine(self):
        """Get or create RAG engine (Advanced or Basic based on configuration)"""
        if self._rag_engine is None:
            with self._lock:
                if self._rag_engine is None:
                    ai_index_dir = self.session_dir / "ai_index"
                    
                    if self.use_advanced_rag and ADVANCED_RAG_AVAILABLE:
                        # Use Advanced RAG Engine with LangGraph
                        self._rag_engine = AdvancedRAGEngine(
                            session_id=self.session_id,
                            persist_dir=ai_index_dir,
                            azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT or ""),
                            azure_api_key=settings.AZURE_OPENAI_API_KEY or "",
                            azure_api_version=settings.AZURE_OPENAI_API_VERSION or "2024-02-01",
                            chat_model=settings.AZURE_OPENAI_CHAT_MODEL or "gpt-4o",
                            embed_model=settings.AZURE_OPENAI_EMBED_MODEL or "text-embedding-3-small",
                            temperature=settings.RET_AI_TEMPERATURE,
                        )
                        logger.info(f"Created AdvancedRAGEngine for session {self.session_id}")
                    elif BASIC_RAG_AVAILABLE:
                        # Fallback to basic RAG Engine
                        self._rag_engine = RAGEngine(
                            session_id=self.session_id,
                            persist_dir=ai_index_dir,
                            azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT or ""),
                            azure_api_key=settings.AZURE_OPENAI_API_KEY or "",
                            azure_api_version=settings.AZURE_OPENAI_API_VERSION or "2024-02-01",
                            chat_deployment=settings.AZURE_OPENAI_CHAT_MODEL or "gpt-4o",
                            embed_deployment=settings.AZURE_OPENAI_EMBED_MODEL or "text-embedding-3-small",
                            temperature=settings.RET_AI_TEMPERATURE,
                        )
                        logger.info(f"Created basic RAGEngine for session {self.session_id}")
                    else:
                        raise RuntimeError("No RAG engine available")
        return self._rag_engine
    
    @property 
    def auto_indexer(self) -> AutoIndexer:
        """Get or create auto-indexer"""
        if self._auto_indexer is None:
            with self._lock:
                if self._auto_indexer is None:
                    self._auto_indexer = AutoIndexer(
                        session_id=self.session_id,
                        runtime_root=self.runtime_root,
                        rag_engine=self.rag_engine,
                    )
        return self._auto_indexer
    
    def is_configured(self) -> bool:
        """Check if AI is properly configured"""
        return (
            bool(settings.AZURE_OPENAI_API_KEY) and
            bool(settings.AZURE_OPENAI_ENDPOINT)
        )
    
    def chat(
        self,
        message: str,
        use_rag: bool = True,
        group_filter: Optional[str] = None,
        top_k: int = 16,
    ) -> Dict[str, Any]:
        """
        Send a chat message and get response using Advanced RAG.
        
        Args:
            message: User message
            use_rag: Whether to use RAG retrieval
            group_filter: Optional group to filter retrieval
            top_k: Number of chunks to retrieve
            
        Returns:
            Response dict with answer, sources, citations, and advanced metadata
        """
        if not self.is_configured():
            return {
                "answer": "AI is not configured. Please set Azure OpenAI credentials.",
                "sources": [],
                "citations": [],
                "error": "not_configured",
            }
        
        # Add to history
        self._chat_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        try:
            if use_rag:
                # Use RAG engine (Advanced or Basic)
                response = self.rag_engine.query(
                    question=message,
                    history=self._chat_history[-10:],  # Last 5 exchanges
                    group_filter=group_filter,
                    top_k=top_k,
                )
                
                # Build sources list
                sources = []
                for i, c in enumerate(response.chunks[:8]):  # Top 8 sources
                    sources.append({
                        "content": c.content[:500] if hasattr(c, 'content') else "",
                        "source": c.source if hasattr(c, 'source') else "",
                        "group": c.group if hasattr(c, 'group') else "",
                        "score": c.score if hasattr(c, 'score') else 0.0,
                        "rank": i,
                        "retrieval_method": getattr(c, 'retrieval_method', 'unknown'),
                    })
                
                # Build result with advanced metadata
                result = {
                    "answer": response.answer,
                    "sources": sources,
                    "citations": response.citations if hasattr(response, 'citations') else [],
                    "query_time_ms": response.query_time_ms if hasattr(response, 'query_time_ms') else 0,
                    "metadata": {},
                }
                
                # Add Advanced RAG specific metadata if available
                if hasattr(response, 'transformed_query') and response.transformed_query:
                    tq = response.transformed_query
                    result["metadata"]["query_transformation"] = {
                        "original": tq.original if hasattr(tq, 'original') else message,
                        "transformed": tq.transformed if hasattr(tq, 'transformed') else message,
                        "intent": tq.intent.value if hasattr(tq, 'intent') else "factual",
                        "keywords": tq.keywords if hasattr(tq, 'keywords') else [],
                    }
                
                if hasattr(response, 'retrieval_strategy'):
                    result["metadata"]["retrieval_strategy"] = (
                        response.retrieval_strategy.value 
                        if hasattr(response.retrieval_strategy, 'value') 
                        else str(response.retrieval_strategy)
                    )
                
                if hasattr(response, 'metadata'):
                    result["metadata"].update(response.metadata or {})
                    
            else:
                # Direct LLM call without RAG
                from langchain_core.messages import HumanMessage, SystemMessage
                
                messages = [
                    SystemMessage(content="You are a helpful assistant for the RET Application."),
                    HumanMessage(content=message),
                ]
                
                llm_response = self.rag_engine.llm.invoke(messages)
                
                result = {
                    "answer": llm_response.content if hasattr(llm_response, 'content') else str(llm_response),
                    "sources": [],
                    "citations": [],
                    "query_time_ms": 0,
                }
            
            # Add response to history
            self._chat_history.append({
                "role": "assistant",
                "content": result["answer"],
                "timestamp": datetime.utcnow().isoformat(),
                "sources": result.get("sources", []),
            })
            
            self._save_metadata()
            
            return result
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            error_msg = f"Error generating response: {str(e)}"
            
            self._chat_history.append({
                "role": "assistant",
                "content": error_msg,
                "timestamp": datetime.utcnow().isoformat(),
                "error": True,
            })
            
            self._save_metadata()
            
            return {
                "answer": error_msg,
                "sources": [],
                "citations": [],
                "error": str(e),
            }
    
    def index_groups(
        self,
        xml_inventory: List[Dict[str, Any]],
        groups: List[str],
    ) -> Dict[str, Any]:
        """
        Index specific groups from XML inventory.
        
        Args:
            xml_inventory: List of XML file entries
            groups: Groups to index
            
        Returns:
            Indexing statistics
        """
        if not self.is_configured():
            return {"error": "AI not configured", "indexed_docs": 0}
        
        total_docs = 0
        total_files = 0
        errors = []
        
        from api.services.ai.auto_indexer import XMLRecordExtractor
        extractor = XMLRecordExtractor()
        
        # Filter inventory
        target_groups = set(g.lower() for g in groups)
        
        for entry in xml_inventory:
            group = entry.get("group", "MISC")
            if group.lower() not in target_groups:
                continue
            
            xml_path = Path(entry.get("xml_path", ""))
            if not xml_path.exists():
                continue
            
            filename = entry.get("filename", xml_path.name)
            
            try:
                # Extract records
                records = extractor.extract_records(xml_path)
                
                if records:
                    record_dicts = [
                        {"content": r.content, "metadata": {"tag": r.tag}}
                        for r in records
                    ]
                    
                    stats = self.rag_engine.index_xml_records(
                        xml_records=record_dicts,
                        group=group,
                        filename=filename,
                    )
                    
                    total_docs += stats.get("indexed_docs", 0)
                    total_files += 1
                    
            except Exception as e:
                logger.error(f"Error indexing {filename}: {e}")
                errors.append(str(e))
        
        return {
            "indexed_files": total_files,
            "indexed_docs": total_docs,
            "groups": groups,
            "errors": errors[:10],
        }
    
    def start_auto_index(
        self,
        xml_inventory: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Start auto-indexing for admin-configured groups.
        
        Args:
            xml_inventory: List of XML file entries from ZIP scan
            
        Returns:
            Status dict with eligible groups
        """
        # Detect eligible groups
        eligible = self.auto_indexer.detect_eligible_groups(xml_inventory)
        
        if not eligible:
            return {
                "status": "no_eligible_groups",
                "eligible_groups": [],
                "message": "No groups match admin auto-index configuration",
            }
        
        # Start background indexing
        self.auto_indexer.start_auto_index(
            xml_inventory=xml_inventory,
            groups_to_index=eligible,
        )
        
        return {
            "status": "started",
            "eligible_groups": eligible,
            "message": f"Auto-indexing started for {len(eligible)} groups",
        }
    
    def get_auto_index_progress(self) -> IndexingProgress:
        """Get current auto-indexing progress"""
        return self.auto_indexer.progress
    
    def get_chat_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chat history"""
        return self._chat_history[-limit:]
    
    def clear_chat_history(self):
        """Clear chat history"""
        self._chat_history = []
        self._save_metadata()
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get vector store statistics"""
        return self.rag_engine.get_stats()
    
    def clear_index(self):
        """Clear all indexed data"""
        self.rag_engine.clear_session()
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self._rag_engine:
                self._rag_engine.clear_session()
            
            # Remove AI index directory
            ai_index_dir = self.session_dir / "ai_index"
            if ai_index_dir.exists():
                import shutil
                shutil.rmtree(ai_index_dir, ignore_errors=True)
            
            # Remove metadata
            if self.metadata_path.exists():
                self.metadata_path.unlink()
                
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# Global registry of session managers
_session_managers: Dict[str, SessionAIManager] = {}
_registry_lock = threading.Lock()


def get_session_ai_manager(
    session_id: str,
    user_id: str,
) -> SessionAIManager:
    """
    Get or create AI manager for a session.
    
    Args:
        session_id: Session identifier
        user_id: User identifier
        
    Returns:
        SessionAIManager instance
    """
    key = f"{user_id}:{session_id}"
    
    with _registry_lock:
        if key not in _session_managers:
            _session_managers[key] = SessionAIManager(
                session_id=session_id,
                user_id=user_id,
                runtime_root=Path(settings.RET_RUNTIME_ROOT),
            )
        return _session_managers[key]


def cleanup_session_ai(session_id: str, user_id: str):
    """Cleanup AI resources for a session (called on logout)"""
    key = f"{user_id}:{session_id}"
    
    with _registry_lock:
        if key in _session_managers:
            try:
                _session_managers[key].cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up AI session: {e}")
            finally:
                del _session_managers[key]
