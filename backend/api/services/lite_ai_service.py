"""
Lightweight AI Service for RET App
Uses Azure OpenAI directly with Chroma for RAG
Can be upgraded to LangChain/LangGraph later
"""

import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
import csv

# Try to import chromadb
chromadb = None
Settings = None
CHROMA_AVAILABLE = False

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logging.warning("Chroma not available")

from api.integrations.azure_openai import AzureOpenAIClient
from api.core.config import settings

logger = logging.getLogger(__name__)


class LiteAIService:
    """Lightweight AI service without LangChain dependency"""
    
    def __init__(self, session_id: str, persist_dir: str):
        self.session_id = session_id
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to initialize OpenAI client (graceful degradation)
        self.openai = None
        try:
            self.openai = AzureOpenAIClient()
            if not self.openai.is_available():
                logger.warning("Azure OpenAI not available - AI features limited")
                self.openai = None
        except Exception as e:
            logger.warning(f"Could not initialize OpenAI client: {e}")
            self.openai = None
        
        self.chroma = None
        self.collection = None
        
        if CHROMA_AVAILABLE and chromadb:
            self._init_chroma()
    
    def _init_chroma(self):
        """Initialize Chroma vector store"""
        if not chromadb:
            logger.warning("chromadb not available")
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
                # Fallback for older versions or different API
                try:
                    self.chroma = chromadb.Client(chromadb.Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=chroma_path,
                        anonymized_telemetry=False,
                    ))
                except:
                    # Last resort - ephemeral client
                    self.chroma = chromadb.Client()
            
            # Sanitize collection name (must be alphanumeric with underscores)
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
    
    def index_csv_files(self, csv_files: List[Path]) -> Dict[str, Any]:
        """Index CSV files into vector store"""
        if not CHROMA_AVAILABLE:
            return {
                "status": "error",
                "message": "ChromaDB not available",
                "documents_indexed": 0,
            }
        
        # Re-initialize Chroma if collection is None
        if self.collection is None:
            self._init_chroma()
        
        if self.collection is None:
            return {
                "status": "error",
                "message": "ChromaDB collection could not be initialized",
                "documents_indexed": 0,
            }
        
        if not self.openai:
            return {
                "status": "error",
                "message": "Azure OpenAI not configured - cannot generate embeddings",
                "documents_indexed": 0,
            }
        
        try:
            documents = []
            metadatas = []
            embeddings = []
            ids = []
            
            total_size = 0
            
            for csv_file in csv_files:
                if not csv_file.exists():
                    logger.warning(f"CSV file not found: {csv_file}")
                    continue
                
                try:
                    # Read CSV
                    content = csv_file.read_text(encoding='utf-8')
                    total_size += len(content.encode('utf-8'))
                    
                    # Split into chunks (simple chunking)
                    lines = content.split('\n')
                    chunk_size = 20  # ~20 rows per chunk
                    
                    for i in range(0, len(lines), chunk_size):
                        chunk = '\n'.join(lines[i:i+chunk_size])
                        if chunk.strip():
                            doc_id = f"{self.session_id}-{csv_file.stem}-{i//chunk_size}"
                            documents.append(chunk)
                            metadatas.append({
                                "source": csv_file.name,
                                "session_id": self.session_id,
                                "chunk_index": i // chunk_size,
                            })
                            ids.append(doc_id)
                    
                except Exception as e:
                    logger.error(f"Failed to read CSV {csv_file}: {e}")
                    continue
            
            if not documents:
                return {
                    "status": "error",
                    "message": "No documents to index",
                    "documents_indexed": 0,
                }
            
            # Get embeddings from Azure OpenAI
            logger.info(f"Getting embeddings for {len(documents)} chunks...")
            embeddings = self.openai.embed_texts(documents)
            
            # Add to Chroma with proper error handling
            logger.info(f"Adding to Chroma...")
            try:
                self.collection.add(
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    ids=ids,
                )
            except (TypeError, ValueError):
                try:
                    # Try with numpy arrays
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
            
            return {
                "status": "success",
                "message": f"Indexed {len(documents)} documents",
                "documents_indexed": len(csv_files),
                "chunks_created": len(documents),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            }
        
        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "documents_indexed": 0,
            }
    
    def query(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """Query indexed documents with RAG"""
        if not self.collection:
            return {
                "answer": "AI indexing not initialized. Please index documents first.",
                "sources": [],
            }
        
        if not self.openai:
            return {
                "answer": "Azure OpenAI is not configured. Please set up Azure OpenAI credentials.",
                "sources": [],
            }
        
        try:
            # Get embedding for question
            q_embedding = self.openai.embed_texts([question])[0]
            
            # Search similar documents
            results = self.collection.query(
                query_embeddings=[q_embedding],
                n_results=top_k
            )
            
            # Extract context with proper type checking
            documents_list = results.get("documents", [])
            metadatas_list = results.get("metadatas", [])
            distances_list = results.get("distances", [])
            
            documents = documents_list[0] if documents_list and isinstance(documents_list[0], list) else []
            metadatas = metadatas_list[0] if metadatas_list and isinstance(metadatas_list[0], list) else []
            distances = distances_list[0] if distances_list and isinstance(distances_list[0], list) else []
            
            if not documents:
                return {
                    "answer": "No relevant documents found.",
                    "sources": [],
                }
            
            # Build context
            context_parts = []
            for doc, meta, dist in zip(documents, metadatas, distances):
                context_parts.append(f"[From {meta.get('source', 'unknown')}]\n{doc}")
            
            context_text = "\n\n---\n\n".join(context_parts)
            
            # Generate answer with Azure OpenAI
            system_msg = (
                "You are a data analysis assistant for RET application. "
                "Answer the user's question based ONLY on the provided context. "
                "If the answer is not in the context, say so clearly."
            )
            
            user_msg = f"Context from documents:\n\n{context_text}\n\nQuestion: {question}"
            
            answer = self.openai.chat(system_msg, user_msg)
            
            # Prepare sources
            sources = [
                {
                    "file": meta.get("source", "unknown"),
                    "snippet": doc[:300] + ("..." if len(doc) > 300 else ""),
                }
                for doc, meta in zip(documents, metadatas)
            ]
            
            return {
                "answer": answer,
                "sources": sources,
            }
        
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            return {
                "answer": f"Error processing query: {str(e)}",
                "sources": [],
            }
    
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Chat with AI using conversation history"""
        try:
            system_msg = (
                "You are a helpful data analysis assistant for RET application. "
                "Help users understand and analyze their uploaded data."
            )
            
            # Build messages
            msg_list = []
            for msg in messages:
                role = msg.get("role", "user").lower()
                content = msg.get("content", "")
                
                if role == "user":
                    msg_list.append({"role": "user", "content": content})
                elif role == "assistant":
                    msg_list.append({"role": "assistant", "content": content})
            
            # Get response
            response = self.openai.client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT or "gpt-4",
                messages=[{"role": "system", "content": system_msg}] + msg_list,
                temperature=0.2,
                max_tokens=2000,
            )
            
            return response.choices[0].message.content or ""
        
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"Error: {str(e)}"
    
    def clear(self):
        """Clear all indexed data"""
        try:
            if self.chroma and self.collection:
                # Delete all documents in collection
                ids = self.collection.get()["ids"]
                if ids:
                    self.collection.delete(ids=ids)
            logger.info(f"Cleared AI index for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to clear: {e}")


# Global cache
_AI_SERVICES: Dict[str, LiteAIService] = {}


def get_ai_service(session_id: str, persist_dir: Optional[str] = None) -> LiteAIService:
    """Get or create AI service"""
    if session_id in _AI_SERVICES:
        return _AI_SERVICES[session_id]
    
    if persist_dir is None:
        persist_dir = str(Path(settings.RET_RUNTIME_ROOT) / "sessions" / session_id / "ai_index")
    
    service = LiteAIService(session_id, persist_dir)
    _AI_SERVICES[session_id] = service
    return service


def clear_ai_service(session_id: str):
    """Clear AI service"""
    if session_id in _AI_SERVICES:
        _AI_SERVICES[session_id].clear()
        del _AI_SERVICES[session_id]
