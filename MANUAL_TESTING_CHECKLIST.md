# RET v4 - Manual Frontend Testing Checklist

## Environment Setup

### Prerequisites Checklist:
- [ ] Python 3.10+ installed
- [ ] Node.js 18+ installed  
- [ ] PostgreSQL running (or update DATABASE_URL in .env)
- [ ] Azure OpenAI credentials in .env file

### Port Availability:
- [ ] Port 8000 available (backend)
- [ ] Port 5173 available (frontend)

---

## Phase 1: Backend Startup

### Step 1.1-1.5: Start Backend Server

```bash
cd d:\WORK\RET_App\backend
.\.venv\Scripts\Activate.ps1
python scripts/init_db.py
python scripts/demo_users.py
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Expected: Server running on http://0.0.0.0:8000 ✅ / ❌

---

## Phase 2: Frontend Startup

```bash
cd d:\WORK\RET_App\frontend
npm install
npm run dev
```

Expected: Server running on http://localhost:5173 ✅ / ❌

---

## Phase 3: Basic Tests

### Test 3.1: Frontend Loads
- Open http://localhost:5173
- [ ] Page loads without errors
- [ ] Login form visible
- [ ] No red errors in console
**Result**: ✅ / ❌

### Test 3.2: Backend Health
- Open http://localhost:8000/docs
- Call GET `/health`
- [ ] Returns `{"status": "ok", "app": "RET-v4"}`
**Result**: ✅ / ❌

### Test 3.3: Login
- Use credentials from `python scripts/demo_users.py`
- [ ] Login successful
- [ ] Redirected to main page
- [ ] User info visible (top-right)
- [ ] Authorization header in requests
**Result**: ✅ / ❌

### Test 3.4: Theme Toggle
- Click 🌓 in header
- [ ] Dark mode activates
- [ ] Persists after refresh
**Result**: ✅ / ❌

### Test 3.5: Navigate Tabs
- Click: Conversion, Comparison, Ask RET AI, Admin
- [ ] All load without 404 errors
- [ ] No console errors
**Result**: ✅ / ❌

---

## Phase 4: Conversion Feature

### Test 4.1: Upload & Scan ZIP
- Navigate to Conversion tab
- Use file: `d:\WORK\RET_App\Examples\BIg_test-examples\journal_article_4.4.2.xml`
- Click "Scan"
- [ ] Groups detected
- [ ] File count shown
- [ ] Session created
**Result**: ✅ / ❌

### Test 4.2: Convert to CSV
- Select groups from scan results
- Choose CSV format
- Click "Convert"
- [ ] Job created with ID
- [ ] Progress visible
- [ ] Download available when complete
- [ ] CSV file valid (open in Excel)
**Result**: ✅ / ❌

---

## Phase 5: Comparison Feature

### Test 5.1: Compare Two Files
- Navigate to Comparison tab
- Upload two CSV files (can use converted XMLs)
- Click "Compare"
- [ ] Comparison completes
- [ ] Shows similarity %
- [ ] Shows added/removed/modified rows
- [ ] Delta indicators (🟢/🔴) visible
**Result**: ✅ / ❌

---

## Phase 6: AI/RAG Feature (CORE)

### Test 6.1: Upload Multiple XMLs for Indexing
- Navigate to "Ask RET AI" tab
- Upload ZIP with multiple XMLs from Examples
- Scan to detect groups
- [ ] Multiple groups shown
- [ ] Session created
**Result**: ✅ / ❌

### Test 6.2: Index Groups to Chroma DB
- Select 2-3 groups for indexing
- Click "Index Selected Groups"
- Wait for completion
- [ ] Shows "Indexing..." progress
- [ ] Shows document count when complete
- [ ] Indexed groups highlighted/checked
- [ ] No errors in console
- [ ] Backend console shows embedding API calls
**Result**: ✅ / ❌

### Test 6.3: Chat with AI Using RAG
Ask sample questions (after Test 6.2):

1. **Question**: "What is the title of the article?"
   - [ ] AI responds with actual title from data
   - [ ] Cites source document
   - [ ] Shows similarity score
   **Result**: ✅ / ❌

2. **Question**: "What topics are discussed?"
   - [ ] AI provides topic summary
   - [ ] Based on indexed content
   - [ ] Shows citations
   **Result**: ✅ / ❌

3. **Question**: "How many authors are mentioned?"
   - [ ] AI counts from actual data
   - [ ] Shows sources
   **Result**: ✅ / ❌

4. **Follow-up Question**: "Tell me more about [topic]"
   - [ ] AI uses previous context
   - [ ] Provides deeper information
   - [ ] Shows citations
   **Result**: ✅ / ❌

### Test 6.4: Clear Session Memory
- Click "Clear All Memory" button
- Confirm action
- [ ] Indexed groups cleared
- [ ] Status shows "No groups indexed"
- [ ] Can re-index different groups
**Result**: ✅ / ❌

---

## Phase 7: Admin Features

### Test 7.1: Admin Button Visibility
- Login as admin user
- [ ] Admin button visible in header
- [ ] Only visible for admin users
**Result**: ✅ / ❌

### Test 7.2: Admin Panel
- Click Admin button
- [ ] Admin panel loads
- [ ] No 403 errors
- [ ] Can see admin features
**Result**: ✅ / ❌

---

## Phase 8: Session Management

### Test 8.1: Logout
- Click Logout button
- [ ] Redirected to login page
- [ ] Session cleared
- [ ] Can log back in
**Result**: ✅ / ❌

### Test 8.2: Token Refresh
- Login successfully
- Wait or force token expiry
- Make API request
- [ ] Automatic refresh to /api/auth/refresh
- [ ] New token obtained
- [ ] Original request retried
- [ ] No user intervention needed
**Result**: ✅ / ❌

---

## Summary

### Critical Features Status:
- Backend Health: ✅ / ❌
- Frontend Loads: ✅ / ❌
- Authentication: ✅ / ❌
- File Conversion: ✅ / ❌
- Comparison: ✅ / ❌
- **AI/RAG Indexing**: ✅ / ❌
- **AI/RAG Chat**: ✅ / ❌
- Admin Panel: ✅ / ❌
- Session Management: ✅ / ❌
- Theme Toggle: ✅ / ❌

### Overall Status:
- **READY FOR PRODUCTION**: All tests ✅
- **NEEDS FIXES**: Some tests ❌
- **PARTIALLY WORKING**: Mixed results ⚠️

### Issues Found:
[List any issues discovered during testing]

### Notes:
[Additional observations and recommendations]

---

## Key Testing URLs

- **Frontend**: http://localhost:5173
- **Backend**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **Example Files**: d:\WORK\RET_App\Examples\BIg_test-examples\

## Testing Commands

```bash
# Terminal 1: Backend
cd d:\WORK\RET_App\backend
.\.venv\Scripts\Activate.ps1
python scripts/demo_users.py  # Note credentials
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd d:\WORK\RET_App\frontend
npm run dev

# Terminal 3: Run automated tests
cd d:\WORK\RET_App
python test_all_features.py
```

---

**Date**: January 27, 2026
**Last Updated**: Testing Guide Created
