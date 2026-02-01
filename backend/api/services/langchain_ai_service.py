"""
LangChain + LangGraph AI Service with Azure OpenAI
Implements RAG and conversation management
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json
from dataclasses import dataclass
import tempfile

from api.core.config import settings

logger = logging.getLogger(__name__)

# Try to import LangChain components
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        RecursiveCharacterTextSplitter = None

try:
    from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
except ImportError:
    AzureOpenAIEmbeddings = None
    AzureChatOpenAI = None

try:
    from langchain_community.vectorstores import Chroma
except ImportError:
    try:
        from langchain.vectorstores import Chroma
    except ImportError:
        Chroma = None

try:
    from langchain_core.documents import Document
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    try:
        from langchain.schema import Document, HumanMessage, SystemMessage
    except ImportError:
        Document = None
        HumanMessage = None
        SystemMessage = None

try:
    from langchain.chains import RetrievalQA
except ImportError:
    RetrievalQA = None

try:
    from langchain.prompts import PromptTemplate
except ImportError:
    PromptTemplate = None

LANGCHAIN_AVAILABLE = all([
    RecursiveCharacterTextSplitter,
    AzureOpenAIEmbeddings,
    AzureChatOpenAI,
    Chroma,
    Document,
    HumanMessage,
    SystemMessage,
    RetrievalQA,
    PromptTemplate,
])


@dataclass
class IndexingStats:
    """Statistics from indexing operation"""
    documents_indexed: int
    chunks_created: int
    groups_processed: int
    total_size_mb: float


class LangChainAIService:
    """AI service using LangChain with Azure OpenAI and Chroma"""
    
    def __init__(self, session_id: str, persist_dir: str):
        """Initialize AI service for a session"""
        self.session_id = session_id
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize embeddings
        self.embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            model=settings.AZURE_OPENAI_EMBED_MODEL,
        )
        
        # Initialize LLM
        self.llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            temperature=0.2,
            max_tokens=2000,
        )
        
        # Initialize vector store
        self.vector_store = None
        self.retriever = None
        self.qa_chain = None
        self._init_vector_store()
    def _init_vector_store(self):
        """Initialize or load vector store"""
        try:
            self.vector_store = Chroma(
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_dir / "chroma_db"),
            )
            logger.info(f"Loaded existing vector store for session {self.session_id}")
        except Exception as e:
            logger.warning(f"Creating new vector store: {e}")
            self.vector_store = Chroma(
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_dir / "chroma_db"),
            )
    
    def index_csv_files(
        self,
        csv_files: List[Path],
        groups: Optional[Dict[str, List[Path]]] = None,
    ) -> IndexingStats:
        """
        Index CSV files into vector store
        
        Args:
            csv_files: List of CSV file paths
            groups: Optional dict mapping group names to file lists
        
        Returns:
            IndexingStats with indexing results
        """
        try:
            documents: List[Document] = []
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", " ", ""]
            )
            
            total_size = 0
            for csv_file in csv_files:
                if not csv_file.exists():
                    logger.warning(f"CSV file not found: {csv_file}")
                    continue
                
                try:
                    # Read CSV content
                    content = csv_file.read_text(encoding='utf-8')
                    total_size += len(content.encode('utf-8'))
                    
                    # Determine group
                    group = "default"
                    if groups:
                        for g, files in groups.items():
                            if csv_file in files:
                                group = g
                                break
                    
                    # Create document with metadata
                    doc = Document(
                        page_content=content,
                        metadata={
                            "source": csv_file.name,
                            "group": group,
                            "session_id": self.session_id,
                        }
                    )
                    documents.append(doc)
                    
                except Exception as e:
                    logger.error(f"Failed to read CSV {csv_file}: {e}")
                    continue
            
            if not documents:
                logger.warning("No documents to index")
                return IndexingStats(
                    documents_indexed=0,
                    chunks_created=0,
                    groups_processed=0,
                    total_size_mb=0.0,
                )
            
            # Split documents into chunks
            chunks = text_splitter.split_documents(documents)
            
            # Add to vector store
            ids = [f"{self.session_id}-{i}" for i in range(len(chunks))]
            self.vector_store.add_documents(chunks, ids=ids)
            self.vector_store.persist()
            
            # Setup retriever and QA chain
            self._setup_qa_chain()
            
            stats = IndexingStats(
                documents_indexed=len(documents),
                chunks_created=len(chunks),
                groups_processed=len(set(d.metadata.get("group") for d in documents)),
                total_size_mb=total_size / (1024 * 1024),
            )
            
            logger.info(f"Indexed {len(documents)} documents into {len(chunks)} chunks")
            return stats
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            raise
    
    def _setup_qa_chain(self):
        """Setup QA chain with retriever"""
        self.retriever = self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )
        
        # Custom prompt template
        prompt_template = """Use the following pieces of context to answer the user's question. 
If you don't know the answer from the context, say you don't have that information in the documents.
Cite the source file when relevant.

Context:
{context}

Question: {question}

Answer:"""
        
        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
    
    def query(self, question: str) -> Dict[str, Any]:
        """
        Query the indexed documents
        
        Args:
            question: User question
        
        Returns:
            Dict with answer and source documents
        """
        if not self.qa_chain:
            self._setup_qa_chain()
        
        try:
            result = self.qa_chain({"query": question})
            
            sources = []
            if result.get("source_documents"):
                for doc in result["source_documents"]:
                    sources.append({
                        "file": doc.metadata.get("source", "unknown"),
                        "group": doc.metadata.get("group", "default"),
                        "snippet": doc.page_content[:500],
                    })
            
            return {
                "answer": result.get("result", ""),
                "sources": sources,
                "status": "success",
            }
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {
                "answer": f"Error processing query: {str(e)}",
                "sources": [],
                "status": "error",
            }
    
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Chat with the AI using conversation history
        
        Args:
            messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        
        Returns:
            AI response
        """
        try:
            # Build message objects
            formatted_messages = []
            
            # Add system message
            system_prompt = """You are a helpful data analysis assistant for the RET application. 
You help users understand and analyze their uploaded XML/CSV data. 
Be concise, accurate, and cite specific data when relevant."""
            formatted_messages.append(SystemMessage(content=system_prompt))
            
            # Add conversation history
            for msg in messages:
                role = msg.get("role", "user").lower()
                content = msg.get("content", "")
                
                if role == "user":
                    formatted_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    from langchain.schema import AIMessage
                    formatted_messages.append(AIMessage(content=content))
            
            # Get response
            response = self.llm.invoke(formatted_messages)
            return response.content
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"Error: {str(e)}"
    
    def clear(self):
        """Clear all indexed data"""
        try:
            if self.vector_store:
                self.vector_store.delete_collection()
            self.qa_chain = None
            self.retriever = None
            logger.info(f"Cleared AI index for session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")


# Global cache of AI services per session
_AI_SERVICES: Dict[str, LangChainAIService] = {}


def get_ai_service(session_id: str, persist_dir: Optional[str] = None) -> LangChainAIService:
    """Get or create AI service for session"""
    if session_id in _AI_SERVICES:
        return _AI_SERVICES[session_id]
    
    if persist_dir is None:
        persist_dir = str(Path(settings.RET_RUNTIME_ROOT) / "sessions" / session_id / "ai_index")
    
    service = LangChainAIService(session_id, persist_dir)
    _AI_SERVICES[session_id] = service
    return service


def clear_ai_service(session_id: str):
    """Clear AI service for session"""
    if session_id in _AI_SERVICES:
        _AI_SERVICES[session_id].clear()
        del _AI_SERVICES[session_id]
