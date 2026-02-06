"""
LangChain AI Strategy - Uses LangChain with Azure OpenAI for advanced RAG.

This strategy provides more sophisticated document processing and retrieval
using the LangChain framework.
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
from api.core.config import settings

logger = logging.getLogger(__name__)

# Try to import LangChain components
RecursiveCharacterTextSplitter = None
AzureOpenAIEmbeddings = None
AzureChatOpenAI = None
Chroma = None
Document = None
HumanMessage = None
SystemMessage = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        pass

try:
    from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
except ImportError:
    pass

try:
    from langchain_community.vectorstores import Chroma
except ImportError:
    try:
        from langchain.vectorstores import Chroma
    except ImportError:
        pass

try:
    from langchain_core.documents import Document
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    try:
        from langchain.schema import Document, HumanMessage, SystemMessage
    except ImportError:
        pass

LANGCHAIN_AVAILABLE = all([
    RecursiveCharacterTextSplitter,
    AzureOpenAIEmbeddings,
    AzureChatOpenAI,
    Chroma,
    Document,
])


class LangChainAIStrategy(BaseAIService):
    """
    AI service using LangChain with Azure OpenAI and Chroma.
    Provides sophisticated document processing and retrieval.
    """
    
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    DEFAULT_TOP_K = 5
    
    def __init__(self, session_id: str, persist_dir: Optional[str] = None):
        super().__init__(session_id, persist_dir)
        self.embeddings = None
        self.llm = None
        self.vector_store = None
        self.text_splitter = None
    
    def initialize(self) -> bool:
        """Initialize LangChain components"""
        if not LANGCHAIN_AVAILABLE:
            logger.warning("LangChain components not available")
            self._initialized = False
            return False
        
        try:
            # Initialize embeddings
            self.embeddings = AzureOpenAIEmbeddings(
                azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT),
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                model=settings.AZURE_OPENAI_EMBED_MODEL,
            )
            
            # Initialize LLM
            self.llm = AzureChatOpenAI(
                azure_endpoint=str(settings.AZURE_OPENAI_ENDPOINT),
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                temperature=0.2,
                max_tokens=2000,
            )
            
            # Initialize text splitter
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.CHUNK_SIZE,
                chunk_overlap=self.CHUNK_OVERLAP,
                separators=["\n\n", "\n", " ", ""]
            )
            
            # Initialize vector store
            self._init_vector_store()
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize LangChain service: {e}")
            self._initialized = False
            return False
    
    def _init_vector_store(self) -> None:
        """Initialize or load vector store"""
        if not self.persist_dir:
            return
        
        try:
            chroma_path = str(self.persist_dir / "chroma_db")
            self.vector_store = Chroma(
                embedding_function=self.embeddings,
                persist_directory=chroma_path,
            )
            logger.info(f"Initialized vector store for session {self.session_id}")
        except Exception as e:
            logger.warning(f"Creating new vector store: {e}")
            self.vector_store = Chroma(
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_dir / "chroma_db") if self.persist_dir else None,
            )
    
    def is_available(self) -> bool:
        """Check if service is available"""
        return (
            LANGCHAIN_AVAILABLE
            and self.embeddings is not None
            and self.llm is not None
        )
    
    def index_documents(
        self,
        files: List[Path],
        groups: Optional[Dict[str, List[Path]]] = None,
    ) -> IndexingStats:
        """Index documents using LangChain"""
        stats = IndexingStats()
        
        if not LANGCHAIN_AVAILABLE:
            stats.errors.append("LangChain not available")
            return stats
        
        try:
            documents: List[Document] = []
            total_size = 0
            groups_seen = set()
            
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
                    groups_seen.add(group)
                    
                    # Create document with metadata
                    doc = Document(
                        page_content=content,
                        metadata={
                            "source": file_path.name,
                            "group": group,
                            "session_id": self.session_id,
                        }
                    )
                    documents.append(doc)
                    stats.documents_indexed += 1
                    
                except Exception as e:
                    logger.error(f"Failed to read file {file_path}: {e}")
                    stats.errors.append(f"Failed to read {file_path.name}")
            
            if not documents:
                stats.errors.append("No documents to index")
                return stats
            
            # Split documents into chunks
            chunks = self.text_splitter.split_documents(documents)
            
            # Add to vector store
            ids = [f"{self.session_id}-{i}" for i in range(len(chunks))]
            self.vector_store.add_documents(chunks, ids=ids)
            
            # Persist
            if hasattr(self.vector_store, 'persist'):
                self.vector_store.persist()
            
            stats.chunks_created = len(chunks)
            stats.total_size_mb = total_size / (1024 * 1024)
            stats.groups_processed = len(groups_seen)
            
            logger.info(
                f"Indexed {stats.documents_indexed} documents "
                f"({stats.chunks_created} chunks) for session {self.session_id}"
            )
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            stats.errors.append(str(e))
        
        return stats
    
    def chat(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> ChatResponse:
        """Chat using LangChain retrieval"""
        if not self.is_available():
            return ChatResponse(
                answer="LangChain service is not available.",
                metadata={"error": "service_unavailable"}
            )
        
        if not self.vector_store:
            return ChatResponse(
                answer="No documents have been indexed yet.",
                metadata={"error": "no_documents"}
            )
        
        try:
            # Retrieve relevant documents
            retriever = self.vector_store.as_retriever(
                search_kwargs={"k": self.DEFAULT_TOP_K}
            )
            docs = retriever.invoke(query)
            
            if not docs:
                return ChatResponse(
                    answer="No relevant documents found.",
                    metadata={"error": "no_results"}
                )
            
            # Build context
            context_text = "\n\n".join([doc.page_content for doc in docs])
            
            # Build messages
            system_msg = SystemMessage(content=(
                "You are a RETv4 assistant. Answer strictly using the provided context. "
                "Cite facts from the context. If information is not in the context, say so."
            ))
            
            human_msg = HumanMessage(content=f"Context:\n{context_text}\n\nQuestion: {query}")
            
            messages = [system_msg]
            
            # Add history if provided
            if history:
                for msg in history[-4:]:  # Keep last 4 messages
                    if msg.get("role") == "user":
                        messages.append(HumanMessage(content=msg["content"]))
                    else:
                        from langchain_core.messages import AIMessage
                        messages.append(AIMessage(content=msg["content"]))
            
            messages.append(human_msg)
            
            # Get response
            response = self.llm.invoke(messages)
            answer = response.content
            
            # Build citations
            citations = [
                Citation(
                    content=doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                    source=doc.metadata.get("source", "unknown"),
                    score=0.0,  # LangChain doesn't provide scores by default
                    metadata=doc.metadata,
                )
                for doc in docs
            ]
            
            return ChatResponse(
                answer=answer,
                citations=citations,
                metadata={"query": query, "context_chunks": len(docs)},
            )
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return ChatResponse(
                answer=f"An error occurred: {str(e)}",
                metadata={"error": str(e)},
            )
    
    def cleanup(self) -> None:
        """Cleanup resources"""
        self.vector_store = None
        self.embeddings = None
        self.llm = None
        self._initialized = False
