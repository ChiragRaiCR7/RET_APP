"""
Lightweight AI Service for RET App
Uses Azure OpenAI directly with Chroma for RAG
Can be upgraded to LangChain/LangGraph later
"""

import logging
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
import csv
from collections import defaultdict

try:
    import chromadb
    from chromadb.config import Settings
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
        
        self.openai = AzureOpenAIClient()
        self.chroma = None
        self.collection = None
        
        if CHROMA_AVAILABLE:
            self._init_chroma()
    
    def _init_chroma(self):
        """Initialize Chroma vector store"""
        try:
            chroma_path = str(self.persist_dir / "chroma_db")
            
            settings_obj = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=chroma_path,
                anonymized_telemetry=False,
            )
            
            self.chroma = chromadb.Client(settings_obj)
            self.collection = self.chroma.get_or_create_collection(
                name=f"session_{self.session_id}",
                metadata={"session_id": self.session_id}
            )
            logger.info(f"Initialized Chroma for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to initialize Chroma: {e}")
    
    def index_csv_files(self, csv_files: List[Path]) -> Dict[str, Any]:
        """Index CSV files into vector store"""
        if not CHROMA_AVAILABLE:
            return {
                "status": "error",
                "message": "Chroma not available",
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
            
            # Add to Chroma
            logger.info(f"Adding to Chroma...")
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
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
        
        try:
            # Get embedding for question
            q_embedding = self.openai.embed_texts([question])[0]
            
            # Search similar documents
            results = self.collection.query(
                query_embeddings=[q_embedding],
                n_results=top_k
            )
            
            # Extract context
            documents = results.get("documents", [[]])[0] or []
            metadatas = results.get("metadatas", [[]])[0] or []
            distances = results.get("distances", [[]])[0] or []
            
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
                model=settings.AZURE_OPENAI_CHAT_MODEL,
                messages=[{"role": "system", "content": system_msg}] + msg_list,
                temperature=0.2,
                max_tokens=2000,
            )
            
            return response.choices[0].message.content
        
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
