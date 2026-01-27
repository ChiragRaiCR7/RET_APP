# RET v4 - Comprehensive Application Testing Guide

**Date**: January 27, 2026  
**Purpose**: Complete feature testing with AI/RAG functionality using Example XML files

---

## 📋 Overview

This guide covers testing ALL features of the RET v4 application:
- Authentication & Authorization
- File Upload & XML Processing
- Comparison Features with Delta Highlighting
- AI/RAG with Chroma DB for local sessions
- Admin Features
- Frontend User Interface

**Key Focus**: Testing AI functionality with Azure OpenAI embeddings and chat models using Example ZIP files with XML content for Chroma DB indexing.

---

## 🔧 Prerequisites Setup

### Step 1: Verify Environment Configuration

Check `.env` file has all required settings:

```bash
# Backend/.env (d:\WORK\RET_App\backend\.env)
- DATABASE_URL=postgresql+psycopg2://ret_admin:Band8697@localhost/ret_db
- AZURE_OPENAI_ENDPOINT=https://btgazureopenai.openai.azure.com/
- AZURE_OPENAI_API_KEY=b7a813d6bdd8487c954991961f6d174e
- AZURE_OPENAI_CHAT_DEPLOYMENT=ESU_CBG_gpt-4.1
- AZURE_OPENAI_EMBED_DEPLOYMENT=ESU_CBG_text-embedding-3-large
- JWT_SECRET_KEY=set (min 32 chars)
- CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

**Status**: ✅ All credentials are configured in the provided .env file

---

## 🚀 Step 1: Setup & Start Backend

### Commands:

```bash
# Terminal 1: Backend
cd D:\WORK\RET_App\backend

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies (if not already done)
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Create demo users
python scripts/demo_users.py

# Start backend server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Verification:**
- Open http://localhost:8000/docs (Swagger UI should load)
- Call `/health` endpoint - should return `{"status": "ok", "app": "RET-v4"}`

---

## 🚀 Step 2: Setup & Start Frontend

### Commands:

```bash
# Terminal 2: Frontend
cd D:\WORK\RET_App\frontend

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev
```

**Expected Output:**
```
  VITE v7.2.4  ready in XXX ms

  ➜  Local:   http://localhost:5173/
```

**Verification:**
- Open http://localhost:5173
- Login form should be visible
- No console errors

---

## 🧪 TEST SECTION 1: Authentication & Authorization

### Test 1.1: Login with Demo User

**Objective**: Verify login flow works end-to-end

**Steps**:
1. Open http://localhost:5173 in browser
2. Login with credentials:
   - **Username**: `admin` (or created user)
   - **Password**: Check terminal output from `python scripts/demo_users.py`
3. Check browser console (F12) for any errors
4. Verify redirect to main application page

**Expected Results**:
- ✅ Login successful
- ✅ Redirected to /app (Main View)
- ✅ User info shown in top-right corner
- ✅ No 401/403 errors in console
- ✅ Authorization header present in API requests

**Sample Network Request**:
```
POST /api/auth/login
Request: {
  "username": "admin",
  "password": "password"
}

Response (200): {
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "username": "admin",
    "is_admin": true
  }
}
```

---

### Test 1.2: Token Refresh on Expiry

**Objective**: Verify automatic token refresh mechanism

**Steps**:
1. While logged in, open DevTools (F12)
2. Note access_token in request headers
3. Wait for token to expire (or manually modify in storage)
4. Make any API request (e.g., click a feature button)
5. Monitor Network tab for refresh request

**Expected Results**:
- ✅ Initial request gets 401 (if token expired)
- ✅ Automatic POST to `/api/auth/refresh`
- ✅ New access_token obtained
- ✅ Original request retried automatically
- ✅ User continues without logout

---

### Test 1.3: Logout Flow

**Objective**: Verify logout clears all session data

**Steps**:
1. While logged in, click Logout button (top-right)
2. Verify redirect to login page
3. Check browser DevTools > Application tab
4. Look for localStorage/sessionStorage - should be cleared
5. Try accessing /app directly - should redirect to /login

**Expected Results**:
- ✅ Logout successful
- ✅ Redirected to /login
- ✅ All auth data cleared
- ✅ Session directory cleaned up on backend
- ✅ Chroma DB for session deleted

**API Call Flow**:
```
POST /api/auth/logout
Response (200): {
  "message": "Successfully logged out"
}
```

---

## 🧪 TEST SECTION 2: File Upload & XML Processing

### Test 2.1: ZIP File Scan with XML Detection

**Objective**: Test ZIP upload and group detection

**Steps**:
1. Login to the application
2. Navigate to "Utility" tab
3. Click "Upload ZIP File"
4. Select a ZIP file from `d:\WORK\RET_App\Examples\BIg_test-examples\`
   - Recommendation: Start with a small file like `journal_article_4.4.2.xml` (single file)
   - Or a multi-file example
5. Click "Scan"
6. Observe detected groups and XML counts

**Expected Results**:
- ✅ File uploads successfully
- ✅ ZIP is scanned for XML files
- ✅ Groups detected from file paths/names
- ✅ XML file count displayed
- ✅ Session created on backend
- ✅ Response shows all detected groups

**Example Response** (from AI Panel / Utility):
```json
{
  "session_id": "uuid-session-id",
  "groups": [
    {"name": "JOURNAL", "count": 5},
    {"name": "BOOK", "count": 2},
    {"name": "DISSERTATION", "count": 1}
  ],
  "total_files": 8,
  "status": "ready_for_processing"
}
```

---

### Test 2.2: XML to CSV Conversion

**Objective**: Test XML parsing and CSV conversion

**Steps**:
1. After scanning ZIP (Test 2.1)
2. In Utility tab, select groups to convert
3. Choose output format: CSV or XLSX
4. Click "Convert"
5. Wait for conversion job to complete
6. Click "Download" for results

**Expected Results**:
- ✅ Conversion job created
- ✅ Job status visible in job list
- ✅ CSV/XLSX file generated with:
  - All XML elements flattened to columns
  - Data from all records in group
  - Proper encoding and formatting
- ✅ Download link works

**Sample CSV Output**:
```
article_id,title,author,publication_date,...
DOI-001,Article Title 1,Author Name,2025-01-20,...
DOI-002,Article Title 2,Another Author,2025-01-21,...
```

---

## 🧪 TEST SECTION 3: Comparison Features

### Test 3.1: File Comparison with Delta Analysis

**Objective**: Test file comparison with field-level change detection

**Steps**:
1. Navigate to "Comparison" tab
2. Upload two CSV/JSON files (can use converted XML outputs)
3. Click "Compare"
4. View detailed comparison results

**Expected Results**:
- ✅ Comparison completes successfully
- ✅ Shows:
  - Field changes (🟢 changed, 🔴 unchanged)
  - Added rows (new records)
  - Deleted rows (missing records)
  - Modified rows with specific field changes
  - Similarity percentage (%)
- ✅ Delta indicators clearly visible
- ✅ Detailed field-by-field breakdown

**Example Comparison Output**:
```json
{
  "total_rows_a": 50,
  "total_rows_b": 52,
  "added_rows": 3,
  "removed_rows": 1,
  "modified_rows": 5,
  "similarity_percentage": 87.5,
  "field_changes": [
    {
      "row_id": 1,
      "field": "title",
      "value_a": "Old Title",
      "value_b": "New Title",
      "changed": true
    }
  ]
}
```

---

## 🧪 TEST SECTION 4: AI/RAG with Chroma DB - CORE TEST

This is the **MAIN FEATURE** to test comprehensively.

### Test 4.1: AI Indexing - Create Chroma DB for Session

**Objective**: Index XML groups into Chroma vector database

**Steps**:

1. **Upload & Scan ZIP** (using Examples folder):
   ```
   - Navigate to Conversion/Utility tab
   - Upload ZIP from: d:\WORK\RET_App\Examples\BIg_test-examples\
   - Click "Scan" to detect groups
   - Note: session_id returned
   ```

2. **Navigate to "Ask RET AI" Tab**:
   ```
   - Click AI/Chat tab
   - View detected groups from scanned ZIP
   - Select groups to index (e.g., JOURNAL, BOOK)
   ```

3. **Index Groups to Chroma DB**:
   ```
   - Click "Index Selected Groups" button
   - Wait for indexing to complete
   - Should see progress: "Indexing JOURNAL (5 files)..."
   ```

4. **Verify Indexing**:
   ```
   - "Indexed Groups" section should show checked items
   - Status: "✅ JOURNAL (5 documents indexed)"
   - Total documents visible
   ```

**Backend Process**:
```
1. Request: POST /api/ai/index
   {
     "session_id": "xxx",
     "groups": ["JOURNAL", "BOOK"]
   }

2. Backend:
   - Loads XML files for selected groups
   - Extracts text from XML elements
   - Creates chunks (e.g., 800 chars each)
   - Calls AZURE_OPENAI_EMBED_DEPLOYMENT
   - Embeds chunks (vector representation)
   - Stores in Chroma DB (session-specific)

3. Response:
   {
     "status": "success",
     "indexed_groups": ["JOURNAL", "BOOK"],
     "total_documents": 1250
   }
```

**Expected Results**:
- ✅ Indexing completes without errors
- ✅ Shows number of documents indexed
- ✅ Chroma DB created at: `backend/runtime/sessions/{session_id}/ai_index`
- ✅ Indexed groups persist during session
- ✅ Can see indexed files count

---

### Test 4.2: AI Chat with RAG - Query Indexed Data

**Objective**: Ask questions answered by indexed XML data via RAG

**Steps**:

1. **After indexing (Test 4.1)**, remain on AI tab
2. **Ask Sample Questions** about indexed content:

   **Question 1 (Factual)**: 
   ```
   "What is the title of the first journal article?"
   ```

   **Question 2 (Metadata)**:
   ```
   "List all authors mentioned in the indexed documents"
   ```

   **Question 3 (Comparison)**:
   ```
   "Compare the publication dates in the documents"
   ```

   **Question 4 (Filtering)**:
   ```
   "Show me all articles from 2024 or later"
   ```

   **Question 5 (Aggregation)**:
   ```
   "How many unique publishers are represented?"
   ```

3. **Observe Chat Response**:
   ```
   - System retrieves relevant documents from Chroma DB
   - Azure OpenAI Chat model generates answer
   - Shows citations/sources from indexed data
   - References specific documents with similarity scores
   ```

**Backend RAG Process**:
```
1. User Question: "What titles are in the data?"

2. POST /api/ai/chat
   {
     "session_id": "xxx",
     "question": "What titles are in the data?",
     "collection": "session-xxx"
   }

3. Backend:
   - Embed user question using AZURE_OPENAI_EMBED_DEPLOYMENT
   - Vector search in Chroma DB (similarity search)
   - Retrieve top-5 most relevant documents/chunks
   - Construct prompt with context:
     ```
     System: You are RETv4 assistant. Answer using provided context.
     
     Context:
     [Retrieved document 1]
     [Retrieved document 2]
     ...
     
     Question: What titles are in the data?
     ```
   - Call AZURE_OPENAI_CHAT_DEPLOYMENT (gpt-4.1) for answer
   - Include citations with source docs and similarity scores

4. Response:
   {
     "answer": "Based on the indexed documents, the titles are: 1) 'Journal Article Title 1' (score: 0.92), 2) 'Book Chapter Title' (score: 0.87), ...",
     "citations": [
       {
         "document": "...[chunk content]...",
         "source": "JOURNAL/article_1.xml",
         "similarity_score": 0.92
       },
       ...
     ]
   }

5. Frontend displays answer with citation sources
```

**Expected Results**:
- ✅ Chat interface loads
- ✅ Can type and send questions
- ✅ Receives answers from AI model (not plain search)
- ✅ Answers are relevant to indexed content
- ✅ Citations show source documents
- ✅ Similarity scores visible
- ✅ Multiple turns in conversation possible

---

### Test 4.3: Clear Session Memory

**Objective**: Test clearing indexed data for session

**Steps**:
1. On AI tab with indexed data
2. Click "Clear All Memory" button
3. Confirm action
4. Verify:
   - Indexed groups section cleared
   - Status shows "No groups indexed"
   - Chroma DB cleaned up

**Expected Results**:
- ✅ All indexed data removed
- ✅ Session directory cleaned
- ✅ Can re-index different groups
- ✅ Previous indexed data inaccessible

---

### Test 4.4: Session Isolation on Logout

**Objective**: Verify AI data deleted completely on logout

**Steps**:
1. With indexed session data, click Logout
2. Log back in with different user (if available)
3. Create new session with different data
4. Verify:
   - Old session data not accessible
   - New session uses fresh Chroma DB
   - No data leakage between sessions

**Expected Results**:
- ✅ Chroma DB deleted on logout
- ✅ Sessions completely isolated
- ✅ New sessions start fresh

---

## 🧪 TEST SECTION 5: Admin Features

### Test 5.1: Admin Dashboard Access

**Objective**: Test admin-only features visibility

**Steps**:
1. Login as admin user
2. Check for "Admin" button in header
3. Click Admin button
4. Observe admin panel features

**Expected Results**:
- ✅ Admin button visible for admin users only
- ✅ Admin panel accessible
- ✅ Cannot access as non-admin user

---

### Test 5.2: Group Indexing Configuration (Admin)

**Objective**: Test admin-level group indexing settings

**Steps**:
1. In Admin panel, find "AI Group Configuration" tab
2. View available groups (left side)
3. Select groups and move to auto-index list (right side)
4. Save configuration
5. Logout and log back in

**Expected Results**:
- ✅ Groups can be moved between lists
- ✅ Configuration saves
- ✅ Persists across sessions

---

## 🧪 TEST SECTION 6: Frontend Features

### Test 6.1: Theme Toggle

**Objective**: Test dark/light mode switching

**Steps**:
1. Click theme toggle (🌓) in header
2. Switch between dark and light modes
3. Refresh page
4. Check if theme persists

**Expected Results**:
- ✅ Theme switches immediately
- ✅ All components styled appropriately
- ✅ Theme persists after refresh

---

### Test 6.2: Navigation Between Tabs

**Objective**: Test all main tabs work correctly

**Steps**:
1. Login to app
2. Click each tab:
   - Conversion
   - Comparison
   - Ask RET AI
   - Admin (if available)
3. Verify each loads without errors

**Expected Results**:
- ✅ All tabs load
- ✅ No console errors
- ✅ Tab content displays correctly

---

## 📊 Example Test Data

Use Example XML files from: `d:\WORK\RET_App\Examples\BIg_test-examples\`

### Available Example Files:
- `journal_article_4.4.2.xml` - Single journal article
- `book_4.4.2.xml` - Book chapter
- `dissertation_4.4.2.xml` - Dissertation
- `crossmark_*.xml` - Multiple variants
- `peer_review_R1-*.xml` - Peer review documents

### Recommended Test Sequence:

**Phase 1 (Basic)**: 
- Start with single XML file
- Test scan & conversion

**Phase 2 (Integration)**:
- Use 3-5 XML files of same type
- Test group detection
- Test conversion

**Phase 3 (AI - CORE)**:
- Use 5+ XML files (mixed types)
- Test indexing
- Test AI chat with multiple questions
- Test citation/source tracking

**Phase 4 (Stress)**:
- Use all available XML files
- Test with large document collection
- Monitor performance

---

## 🔍 Verification Checklist

### Backend Health:
- [ ] http://localhost:8000/docs loads Swagger UI
- [ ] GET /health returns 200 with status
- [ ] Database connected (check logs)
- [ ] Redis available (if using Celery)

### Frontend Health:
- [ ] http://localhost:5173 loads without errors
- [ ] Login form visible
- [ ] No 404/500 errors

### Authentication:
- [ ] Can login with valid credentials
- [ ] Token stored in memory
- [ ] API requests include Authorization header
- [ ] Token refresh works automatically
- [ ] Logout clears all data

### File Processing:
- [ ] ZIP file uploads successfully
- [ ] XML files detected in ZIP
- [ ] Groups inferred correctly
- [ ] CSV/XLSX conversion produces valid output

### Comparison:
- [ ] File upload works for both files
- [ ] Comparison completes without errors
- [ ] Delta indicators display correctly
- [ ] Similarity percentage calculated

### AI/RAG (KEY):
- [ ] Groups can be selected for indexing
- [ ] Indexing completes successfully
- [ ] Chat interface loads
- [ ] Questions generate relevant answers
- [ ] Citations show source documents
- [ ] Memory can be cleared
- [ ] Data isolated per session

### Admin:
- [ ] Admin button visible for admins only
- [ ] Admin panel accessible
- [ ] Can configure groups

---

## 🐛 Troubleshooting

### Backend won't start:
```
Check: 
- Python 3.10+ installed
- Virtual env activated
- Dependencies installed (pip install -r requirements.txt)
- Port 8000 not in use
- Database URL correct in .env
```

### Frontend won't start:
```
Check:
- Node.js 18+ installed
- npm install ran successfully
- Port 5173 not in use
- .env has correct API_BASE
```

### Login fails:
```
Check:
- Backend is running
- Database initialized
- Demo users created (python scripts/demo_users.py)
- Correct credentials used
```

### AI indexing fails:
```
Check:
- Azure OpenAI credentials in .env
- AZURE_OPENAI_ENDPOINT accessible
- AZURE_OPENAI_API_KEY valid
- Chroma DB installed (chromadb in pip)
- Session has extracted XML files
```

### Chat returns empty answers:
```
Check:
- Groups properly indexed
- Documents in Chroma DB
- Similarity search returning results
- Azure OpenAI chat model responding
```

---

## 📝 Testing Report Template

After testing, complete this report:

```markdown
# RET v4 - Testing Report

**Date**: [Date]
**Tester**: [Name]
**Environment**: Windows, Python 3.12, Node 18+

## Results Summary

### Authentication: ✅ PASS / ❌ FAIL
- [x] Login works
- [x] Token refresh works
- [x] Logout clears data
**Notes**: 

### File Processing: ✅ PASS / ❌ FAIL
- [x] ZIP upload works
- [x] XML detection works
- [x] CSV conversion works
**Notes**:

### Comparison: ✅ PASS / ❌ FAIL
- [x] File upload works
- [x] Comparison completes
- [x] Deltas display correctly
**Notes**:

### AI/RAG (CORE): ✅ PASS / ❌ FAIL
- [x] Indexing works
- [x] Chat interface works
- [x] Answers are relevant
- [x] Citations display
**Notes**:

### Admin: ✅ PASS / ❌ FAIL
- [x] Admin button visible
- [x] Admin panel works
**Notes**:

### Frontend: ✅ PASS / ❌ FAIL
- [x] All tabs load
- [x] Theme toggle works
- [x] No console errors
**Notes**:

## Issues Found

1. **[Issue Title]**: Description
   - Steps to reproduce: 
   - Expected: 
   - Actual: 
   - Severity: HIGH/MEDIUM/LOW

## Performance Metrics

- Backend response time (avg): __ms
- Frontend load time: __ms
- Indexing time (100 docs): __s
- Query response time (avg): __ms

## Conclusion

Overall assessment: ✅ READY FOR PRODUCTION / ⚠️ NEEDS FIXES / ❌ NOT READY

Additional notes:
```

---

## ✅ Next Steps After Testing

1. **If All Tests Pass**:
   - Document any behavior differences from expectations
   - Note performance metrics
   - Archive testing report
   - Ready for deployment

2. **If Issues Found**:
   - Create GitHub issues for each bug
   - Prioritize fixes by severity
   - Re-test after fixes
   - Document workarounds if needed

3. **Optimization Opportunities**:
   - Review performance metrics
   - Optimize slow endpoints
   - Consider caching strategies
   - Profile AI indexing bottlenecks

---

**Document Version**: 1.0  
**Last Updated**: January 27, 2026
