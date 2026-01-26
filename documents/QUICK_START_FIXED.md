# RET v4 - Quick Start Guide (Fixed Version)

## 🚀 Quick Start (5 Minutes)

### Prerequisites
- Python 3.9+
- Node.js 16+
- Git

### Step 1: Start Backend

```bash
cd d:\WORK\RET_App\backend

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Run server
uvicorn api.main:app --reload --port 8000
```

Expected output:
```
INFO:     Started server process
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 2: Start Frontend

In a new terminal:
```bash
cd d:\WORK\RET_App\frontend

# Install dependencies (first time only)
npm install

# Start dev server
npm run dev
```

Expected output:
```
VITE v... ready in ... ms

➜  Local:   http://localhost:5173/
```

### Step 3: Open Application

Navigate to: **http://localhost:5173**

### Step 4: Test File Upload

1. **Login** with test credentials (check create_admin.py for defaults)
2. **Go to Main View** (Utility Workflow tab)
3. **Upload a ZIP file** with XML files
4. **Click "Scan ZIP"** button
5. **View detected groups** and metrics
6. **Click "Bulk Convert All"** to convert to CSV
7. **Download results** as ZIP

---

## 📝 Test Data

Create a test ZIP with sample XML:

### Test ZIP Structure
```
test.zip
├── JOURNAL/
│   ├── article_001.xml
│   └── article_002.xml
├── BOOK/
│   └── book_001.xml
└── DISS/
    └── dissertation_001.xml
```

### Sample XML (article_001.xml)
```xml
<?xml version="1.0"?>
<root>
  <article>
    <title>Test Article Title</title>
    <author>John Doe</author>
    <year>2025</year>
  </article>
</root>
```

### Running Test Suite

```bash
cd backend
python test_workflow.py
```

Expected output:
```
============================================================
✓ ALL TESTS PASSED
============================================================
```

---

## 🔧 Key Features Tested & Working

✅ **File Upload**
- Drag & drop ZIP support
- Multiple file selection
- Progress indication

✅ **XML Scanning**
- Automatic detection of XML files
- Group detection from folder structure
- Summary metrics (files, groups, size)

✅ **Group Detection**
- Automatic categorization (JOURNAL, BOOK, DISS, etc.)
- Fallback to filename detection
- Group statistics

✅ **XML to CSV Conversion**
- Recursive XML flattening
- Attribute extraction
- Proper CSV formatting
- Group-specific conversion

✅ **Session Management**
- User-specific sessions
- Automatic cleanup on logout
- Secure session tracking

✅ **Authentication**
- Login/logout
- JWT tokens
- Refresh token handling
- Secure HttpOnly cookies

---

## 📊 API Endpoints (Tested)

### File Upload & Scanning
```bash
POST /api/conversion/scan
Authorization: Bearer <token>
Content-Type: multipart/form-data

# Response
{
  "session_id": "abc123...",
  "xml_count": 4,
  "group_count": 3,
  "groups": [
    {"name": "JOURNAL", "file_count": 2, "size": 10240},
    {"name": "BOOK", "file_count": 1, "size": 5120},
    {"name": "DISS", "file_count": 1, "size": 2560}
  ]
}
```

### Conversion
```bash
POST /api/conversion/convert
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "abc123...",
  "groups": ["JOURNAL", "BOOK"]  // Optional - specific groups
}

# Response
{
  "job_id": 1,
  "status": "started"
}
```

### Download Results
```bash
GET /api/conversion/download/{session_id}
Authorization: Bearer <token>

# Returns: ZIP file with all CSV files
```

---

## 🐛 Troubleshooting

### Backend Won't Start
```bash
# Check Python version
python --version  # Should be 3.9+

# Check dependencies
pip install -r requirements.txt

# Check database path
dir runtime/  # Should exist and be writable
```

### Frontend Won't Connect to Backend
```bash
# Check backend is running
curl http://localhost:8000/health

# Check CORS settings in .env
CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Check API_BASE in frontend .env
VITE_API_BASE=http://localhost:8000/api
```

### Upload Fails
```bash
# Check ZIP file is valid
# Verify token in browser dev tools (Application → Cookies)
# Check backend logs for errors
# Ensure runtime/sessions/ directory exists
```

### Groups Not Detected
```bash
# Verify ZIP structure - needs folders like:
# JOURNAL/file.xml (not file_journal.xml)

# Check that folder names start with letters:
# ✓ JOURNAL/article.xml
# ✓ BOOK_2025/book.xml  
# ✗ 2025_JOURNAL/article.xml
```

---

## 📈 What's Improved

**From Previous Version:**
- ✅ Added authentication to all file endpoints
- ✅ User-specific session tracking
- ✅ Automatic XML group detection
- ✅ Improved XML to CSV conversion
- ✅ Session cleanup on logout
- ✅ Better error handling
- ✅ Frontend shows group results
- ✅ Comprehensive test coverage

---

## 🔐 Security Notes

- JWT tokens expire in 30 minutes
- Refresh tokens stored in HttpOnly cookies
- Path traversal protection in ZIP extraction
- CORS enabled only for localhost (dev)
- All file operations require authentication

---

## 📚 Documentation

- **FIXES_SUMMARY.md** - Comprehensive changes documentation
- **test_workflow.py** - Executable test suite
- **API endpoints** - All tested and working
- **Frontend components** - Updated with group display

---

## ✅ Verification Checklist

- [ ] Backend running on port 8000
- [ ] Frontend running on port 5173 or 3000
- [ ] Can login with valid credentials
- [ ] Can upload ZIP file
- [ ] ZIP scan shows groups
- [ ] Conversion creates CSV files
- [ ] Can download results
- [ ] Logout clears data
- [ ] Test suite passes

---

## Next Steps

1. **Verify file upload workflow works** (this guide)
2. **Run test suite** to validate core functionality
3. **Check CSV output** quality and correctness
4. **Prepare for Chroma DB integration** (vector embeddings)
5. **Add AI agent features** (already scaffolded)

---

**Ready to go! Start with Step 1 above.** 🚀

