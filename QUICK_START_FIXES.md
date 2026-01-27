# RET App - Quick Start Guide for Fixed Services

## Backend Setup

### 1. Start the Backend Server

```bash
cd backend
python ./start.py
```

The server will start on `http://localhost:8000`

### 2. API Endpoints

#### Authentication
```bash
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin123"
}
```

#### File Conversion (ZIP/XML to CSV)
```bash
POST /api/conversion/scan
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <your_file.zip or file.xml>
```

Response:
```json
{
  "session_id": "uuid-here",
  "xml_count": 5,
  "group_count": 2,
  "files": [...],
  "groups": [...]
}
```

#### AI Indexing
```bash
POST /api/ai/index
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid-here",
  "groups": null
}
```

Response:
```json
{
  "status": "success",
  "message": "Indexed X documents",
  "stats": {
    "documents_indexed": 10,
    "chunks_created": 45,
    "total_size_mb": 2.3
  }
}
```

#### AI Chat/Query
```bash
POST /api/ai/chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid-here",
  "question": "What is the main topic?"
}
```

Response:
```json
{
  "answer": "Based on the documents...",
  "sources": [
    {
      "file": "document.csv",
      "group": "JOURNAL",
      "snippet": "Relevant excerpt..."
    }
  ]
}
```

## Key Improvements

### Conversion Service
- ✓ Now handles both ZIP and XML files
- ✓ Proper XML parsing with namespace support
- ✓ Automatic record element detection
- ✓ Hierarchical XML flattening to CSV
- ✓ Error handling and validation
- ✓ Detailed statistics

### AI Service  
- ✓ RAG (Retrieval-Augmented Generation) enabled
- ✓ Azure OpenAI embeddings
- ✓ Chroma vector database storage
- ✓ Conversational AI support
- ✓ Source citation in responses
- ✓ Document chunking for better retrieval

### Authentication
- ✓ All endpoints require Bearer token
- ✓ User isolation (can only access own sessions)
- ✓ Session-based indexing

## Configuration

Update `.env` with Azure OpenAI credentials:

```
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_CHAT_MODEL=gpt-4
AZURE_OPENAI_EMBED_MODEL=text-embedding-ada-002
```

## Testing

Run the comprehensive test suite:

```bash
# Terminal 1: Start backend
cd backend
python ./start.py

# Terminal 2: Run tests
python test_all_features.py
```

Expected test results:
1. ✓ Backend Health Check
2. ✓ Authentication - Login
3. ✓ Get Current User
4. ✓ ZIP/XML file scan
5. ✓ File Comparison
6. ✓ Admin Features
7. ✓ AI Indexing
8. ✓ AI Chat

## Troubleshooting

### "ZIP file required" Error
**Fixed!** The endpoint now accepts both ZIP and XML files.

### "Chroma not available" Warning
This is informational. The service still works with basic vector storage.
To enable advanced features, install chromadb:
```bash
pip install chromadb
```

### Azure OpenAI Errors
Make sure `.env` has correct credentials:
```bash
echo $env:AZURE_OPENAI_API_KEY  # Verify it's set
```

### Port 8000 Already in Use
Kill the existing process:
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use a different port
python ./start.py --port 8001
```

## API Documentation

Full Swagger docs available at:
```
http://localhost:8000/docs
```

## Next Steps

1. **Frontend Integration** - Connect the Vue.js frontend to these endpoints
2. **Advanced Features** - Implement conversation memory, multi-turn chats
3. **Performance** - Add caching, optimize embeddings
4. **Monitoring** - Add metrics, logging, alerting

## Support

For issues or questions about:
- Conversion service: Check `backend/api/services/conversion_service.py`
- AI service: Check `backend/api/services/lite_ai_service.py`
- Endpoints: Check `backend/api/routers/`
- Logs: Check `backend/logs/` and console output

## Files Modified

```
backend/
  api/
    routers/
      conversion_router.py      [UPDATED]
      ai_router.py              [UPDATED]
    services/
      conversion_service.py      [REWRITTEN]
      lite_ai_service.py         [NEW]
      xml_processing_service.py  [ENHANCED]
    schemas/
      ai.py                      [UPDATED]
  pyproject.toml                 [UPDATED]
```

All changes maintain backward compatibility with the existing admin and auth systems.
