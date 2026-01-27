# RET App Backend Architecture - Detailed Technical Guide

## System Overview

The RET (Regulatory Extract Tool) App v4 backend implements a complete XML-to-CSV conversion pipeline with AI-powered RAG (Retrieval-Augmented Generation) capabilities.

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue.js)                         │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTP/JSON
┌────────────────▼────────────────────────────────────────────┐
│                   FastAPI Backend                            │
├─────────────┬──────────────┬──────────────┬─────────────────┤
│   Auth      │  Conversion  │     AI       │    Admin        │
│   Router    │   Router     │    Router    │    Router       │
└─────────────┴──────────────┴──────────────┴─────────────────┘
                 │
      ┌──────────┼──────────────┐
      │          │              │
      ▼          ▼              ▼
  ┌────────┐ ┌─────────┐ ┌──────────────┐
  │ PostgreSQL │ Redis │ │ Chroma VDB  │
  │ Database │ Cache  │ │ (Vectors)   │
  └────────┘ └─────────┘ └──────────────┘
```

## Components

### 1. Conversion Service Stack

#### `conversion_service.py`
Handles XML file scanning and CSV conversion.

**Key Classes/Functions:**
```python
def scan_zip_with_groups(file_bytes, filename, user_id) -> Dict:
    """
    Scans ZIP/XML file and returns groups and file listing.
    
    Process:
    1. Save uploaded file to session storage
    2. Extract ZIP and find all .xml files
    3. Infer groups from file paths and names
    4. Return metadata for indexing UI
    """

def convert_session(session_id, groups=None) -> Dict:
    """
    Converts XML files to CSV format.
    
    Process:
    1. Find XML files in session
    2. Parse each XML with record detection
    3. Flatten hierarchical structure
    4. Write to CSV format
    5. Return conversion statistics
    """
```

#### `xml_processing_service.py`
Advanced XML processing with proper parsing.

**Key Functions:**
```python
def xml_to_rows(
    xml_bytes: bytes,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    path_sep: str = ".",
    include_root: bool = False,
) -> Tuple[List[dict], List[str], str]:
    """
    Convert XML to tabular rows.
    
    Features:
    - Automatic record element detection
    - Namespace-aware parsing
    - Hierarchical path preservation
    - Attribute extraction
    - Flexible chunking for embeddings
    
    Returns:
    - List of row dictionaries
    - Column headers in order
    - Detected record tag
    """

def detect_record_tag_auto(xml_path: str) -> Optional[str]:
    """Auto-detect most common child element as record."""

def iter_xml_record_chunks(
    xml_path: str,
    record_tag: Optional[str] = None,
    auto_detect: bool = True,
    max_records: int = 5000,
    max_chars_per_record: int = 6000,
) -> Iterator[Tuple[int, str, str]]:
    """Stream XML records in chunks for embedding."""
```

#### `conversion_router.py`
HTTP endpoints for conversion operations.

**Endpoints:**
```
POST /api/conversion/scan
    - Accepts: application/x-zip-compressed OR application/xml
    - Returns: ZipScanResponse with session_id, files, groups
    
POST /api/conversion/convert
    - Accepts: ConversionRequest (session_id, optional groups)
    - Returns: ConversionResponse with job_id
    
GET /api/conversion/download/{session_id}
    - Returns: ZIP file with all converted CSVs
```

### 2. AI/RAG Service Stack

#### `lite_ai_service.py`
Lightweight RAG implementation without LangChain dependency.

**Key Classes:**
```python
class LiteAIService:
    """
    Manages AI operations for a single session.
    
    Features:
    - CSV document indexing
    - Chroma vector storage
    - Azure OpenAI embeddings
    - RAG query with context retrieval
    - Conversation history support
    """
    
    def index_csv_files(csv_files: List[Path]) -> Dict:
        """
        Index CSV files into vector store.
        
        Process:
        1. Read CSV content
        2. Split into chunks (20 rows each)
        3. Generate embeddings via Azure OpenAI
        4. Store in Chroma with metadata
        5. Return indexing statistics
        
        Returns:
        {
            "status": "success",
            "documents_indexed": 10,
            "chunks_created": 45,
            "total_size_mb": 2.3
        }
        """
    
    def query(question: str, top_k: int = 5) -> Dict:
        """
        Query indexed documents with RAG.
        
        Process:
        1. Generate embedding for question
        2. Search similar documents in Chroma
        3. Retrieve top-k results
        4. Build context from retrieved docs
        5. Call Azure OpenAI with context + question
        6. Return answer + source citations
        """
    
    def chat(messages: List[Dict[str, str]]) -> str:
        """
        Chat without document context.
        Uses conversation history.
        """
    
    def clear():
        """Clear all indexed data for session."""
```

#### `ai_router.py`
HTTP endpoints for AI operations.

**Endpoints:**
```
POST /api/ai/index
    - Requires: Bearer token
    - Body: {session_id, groups (optional)}
    - Returns: Indexing statistics
    - Process: Calls lite_ai_service.index_csv_files()

GET /api/ai/indexed-groups/{session_id}
    - Returns: Indexing status for session

POST /api/ai/clear-memory/{session_id}
    - Clears all AI indexes for session

POST /api/ai/chat
    - Requires: Bearer token
    - Body: {session_id, question OR messages}
    - Returns: {answer, sources: [{file, snippet}]}
    - Process: Calls lite_ai_service.query() or chat()
```

### 3. Data Models

#### Session Management
```python
Session {
    id: UUID
    user_id: str
    created_at: datetime
    
    directories:
        - input/             # Uploaded files
        - extracted/         # Extracted XML files
        - output/            # Converted CSV files
        - ai_index/          # Vector DB & metadata
            - chroma_db/     # Persistent vector store
            - index_metadata.json
}
```

#### Conversion Flow
```
ZIP/XML File
    ↓
scan_zip_with_groups()
    ↓
XmlEntry[] {
    logical_path: str
    filename: str
    xml_path: str
    xml_size: int
    stub: str
}
    ↓
convert_session()
    ↓
CSV Files {
    group_name/
        - file1.csv
        - file2.csv
}
```

#### AI Indexing Flow
```
CSV Files
    ↓
index_csv_files()
    ↓
Document[] {
    content: str (CSV rows)
    metadata: {
        source: filename
        session_id: UUID
        chunk_index: int
    }
}
    ↓
Text Chunking (20 rows each)
    ↓
Embedding Generation (Azure OpenAI)
    ↓
Chroma Vector Store {
    id: "session-file-chunk"
    embedding: float[]
    document: str
    metadata: {}
}
```

#### Query Flow
```
User Question
    ↓
Embedding Generation (Azure OpenAI)
    ↓
Vector Similarity Search (Chroma)
    ↓
Context Assembly
    ↓
Azure OpenAI Chat + System Prompt
    ↓
Response + Citations
```

## Technology Stack

### Backend Framework
- **FastAPI** - Modern async Python web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation

### Data Storage
- **PostgreSQL** - Relational database (auth, jobs)
- **Redis** - Cache and sessions
- **Chroma** - Vector database (embeddings)

### XML Processing
- **lxml** - Fast C-based XML parser (preferred)
- **xml.etree.ElementTree** - Fallback parser

### AI/ML
- **Azure OpenAI** - Chat & embedding models
- **Chroma** - Vector search
- **LangChain** (optional) - For future graph agents

### Authentication
- **PyJWT** - JWT token generation/validation
- **Argon2** - Password hashing
- **Python-JOSE** - JWT implementation

## Request/Response Examples

### Conversion Flow

**1. Upload & Scan**
```
POST /api/conversion/scan
Authorization: Bearer eyJhbG...
Content-Type: multipart/form-data

[Binary ZIP/XML data]

200 OK:
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "xml_count": 15,
  "group_count": 3,
  "files": [
    {
      "filename": "journal_article.xml",
      "path": "articles/journal_article.xml",
      "group": "JOURNAL",
      "size": 45678
    }
  ],
  "groups": [
    {
      "name": "JOURNAL",
      "file_count": 8,
      "size": 234567
    },
    {
      "name": "BOOK",
      "file_count": 4,
      "size": 123456
    },
    {
      "name": "OTHER",
      "file_count": 3,
      "size": 45678
    }
  ]
}
```

**2. Convert to CSV**
```
POST /api/conversion/convert
Authorization: Bearer eyJhbG...
Content-Type: application/json

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "groups": ["JOURNAL"]  // optional, filters by group
}

200 OK:
{
  "job_id": 12345,  // for async tracking
  "status": "submitted"
}
```

### AI Flow

**1. Index Documents**
```
POST /api/ai/index
Authorization: Bearer eyJhbG...
Content-Type: application/json

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}

200 OK:
{
  "status": "success",
  "message": "Indexed 8 documents into 45 chunks",
  "stats": {
    "documents_indexed": 8,
    "chunks_created": 45,
    "total_size_mb": 2.34
  }
}
```

**2. Query with RAG**
```
POST /api/ai/chat
Authorization: Bearer eyJhbG...
Content-Type: application/json

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "What is the main topic discussed?"
}

200 OK:
{
  "answer": "Based on the indexed documents, the main topics discussed include XML processing, data extraction, and regulatory compliance frameworks. The documents focus on standardized formats for publishing scientific and regulatory content.",
  "sources": [
    {
      "file": "journal_article.csv",
      "group": "JOURNAL",
      "snippet": "This article describes XML processing standards for regulatory documents..."
    },
    {
      "file": "compliance_guide.csv",
      "group": "BOOK",
      "snippet": "Regulatory compliance requires proper data extraction and validation..."
    }
  ]
}
```

## Error Handling

All services implement consistent error handling:

```python
try:
    # Main operation
    result = process_data()
except SpecificException as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    raise HTTPException(status_code=400, detail="User-friendly message")
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error")
```

**HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad request (user error)
- `403` - Forbidden (unauthorized)
- `404` - Not found
- `500` - Server error

## Performance Considerations

### Conversion Service
- Streaming ZIP extraction to avoid memory issues
- Chunked XML parsing for large files
- Automatic record detection (binary search on most common tags)
- CSV writing with proper buffering

### AI Service
- Document chunking (20 rows) for better retrieval
- Batch embedding generation
- Vector similarity search (O(log n))
- Lazy loading of documents

### Scalability
- Session-based isolation (one AI service per session)
- Connection pooling for databases
- Redis caching for frequently accessed data
- Async endpoints for long operations

## Security

### Authentication
- JWT tokens with 30-minute expiration
- Refresh tokens with 7-day expiration
- Password hashing with Argon2

### Authorization
- User isolation (users can only access own sessions)
- Role-based access control (admin, user)
- CORS configuration for frontend access

### Input Validation
- Pydantic models validate all inputs
- ZIP file validation (checks for bomb attacks)
- CSV/XML encoding validation
- Filename sanitization

## Monitoring & Logging

### Log Levels
- **INFO**: Normal operations, milestone completions
- **WARNING**: Issues that don't prevent operation (missing Chroma, etc.)
- **ERROR**: Failures that prevent operation
- **DEBUG**: Detailed operation traces

### Log Locations
- Console output from Uvicorn
- `backend/logs/` directory for persistent logs
- Database audit logs for admin operations

## Future Enhancements

### Phase 2: LangChain Integration
```python
from langchain.chat_models import AzureChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor, create_openai_tools_agent

# Multi-turn conversations with memory
# Agentic workflows with tool use
# Advanced RAG with re-ranking
```

### Phase 3: Advanced Features
- Hybrid vector/keyword search
- Document summarization
- Batch processing with Celery
- Real-time indexing progress
- Multi-document QA
- Chart generation from data

## Deployment

### Production Checklist
- [ ] Set all Azure OpenAI environment variables
- [ ] Configure PostgreSQL with proper backups
- [ ] Set up Redis with persistence
- [ ] Configure CORS for frontend domain
- [ ] Enable SSL/TLS
- [ ] Set up monitoring/alerting
- [ ] Configure log rotation
- [ ] Test with production data
- [ ] Load test vector operations
- [ ] Document runbooks

### Docker Deployment
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0"]
```

## Support & Debugging

### Common Issues

**"ZIP file required" Error**
- Now fixed! Service accepts both ZIP and XML
- Check file extension is .zip or .xml

**Azure OpenAI Connection Error**
- Verify credentials in .env
- Check API version compatibility
- Ensure model names match deployed models

**Vector Search Slow**
- Increase chunk size for faster retrieval
- Ensure Chroma is using GPU if available
- Profile with timing instrumentation

**Memory Issues with Large Files**
- Use streaming extraction for ZIPs
- Increase chunk_size for chunking
- Enable page file on Windows

## References

- FastAPI Docs: https://fastapi.tiangolo.com/
- Chroma Docs: https://docs.trychroma.com/
- Azure OpenAI: https://learn.microsoft.com/en-us/azure/ai-services/openai/
- lxml: https://lxml.de/
