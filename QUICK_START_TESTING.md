# RET v4 - Quick Start Testing Guide

**Version**: 1.0  
**Date**: January 27, 2026  
**Time to Complete**: 30 minutes for full test

---

## ⚡ 5-Minute Quick Test

Just want to verify everything works? Do this:

### 1. Start Services (2 min)
```bash
# Terminal 1: Backend
cd d:\WORK\RET_App\backend
.\.venv\Scripts\Activate.ps1
python scripts/demo_users.py  # Note the password
uvicorn api.main:app --reload

# Terminal 2: Frontend
cd d:\WORK\RET_App\frontend
npm run dev
```

### 2. Test in Browser (3 min)
```
1. Open http://localhost:5173
2. Login with credentials from step 1
3. Click "Ask RET AI" tab
4. Click "Upload ZIP File"
5. Select: d:\WORK\RET_App\Examples\BIg_test-examples\journal_article_4.4.2.xml
6. Click "Scan"
7. Click "Index Selected Groups" (if groups shown)
8. Ask: "What is this document about?"
9. Verify AI responds with document content
```

**✅ If you see an AI response with citations, everything works!**

---

## 📋 Full Testing Path (30 minutes)

### Test Suite Breakdown

#### Part 1: Setup & Startup (5 min)
- Start backend server
- Start frontend server
- Verify both running

#### Part 2: Authentication (5 min)
- Test login
- Verify token handling
- Test logout

#### Part 3: File Processing (5 min)
- Upload ZIP
- Scan for XML
- Detect groups

#### Part 4: Conversion (5 min)
- Convert XML to CSV
- Download results
- Verify CSV format

#### Part 5: AI/RAG (10 min) ⭐ CORE TEST
- Index to Chroma DB
- Ask multiple questions
- Verify citations
- Test memory clear

---

## 🚀 Recommended Test Scenarios

### Scenario A: Minimal Verification (10 min)
**Goal**: Confirm all systems operational

**Steps**:
1. ✅ Backend health check: `curl http://localhost:8000/health`
2. ✅ Frontend loads: Open http://localhost:5173
3. ✅ Login works: Use demo credentials
4. ✅ API responds: Check DevTools Network tab for successful requests

**Pass Criteria**: All 4 items working

---

### Scenario B: Feature Validation (30 min)
**Goal**: Test each feature works end-to-end

**Steps**:
1. ✅ Upload ZIP (Test 4.1)
2. ✅ Convert to CSV (Test 4.2)
3. ✅ Download & verify (Test 4.3)
4. ✅ Compare files (Test 5.1-5.3)
5. ✅ Index to AI (Test 6.2) ⭐
6. ✅ Chat with AI (Test 6.3) ⭐

**Pass Criteria**: All features complete without errors

---

### Scenario C: AI/RAG Deep Test (20 min)
**Goal**: Thoroughly test AI functionality

**Prerequisites**: Complete Scenario B steps 1-5

**Steps**:
1. ✅ Verify indexing completed
2. ✅ Ask 5 different questions
3. ✅ Check citation accuracy
4. ✅ Follow up on previous answers
5. ✅ Test memory clear
6. ✅ Verify clean re-indexing

**Sample Questions**:
- "What is the main topic?"
- "Who are the authors?"
- "What methodologies were used?"
- "Provide a summary"
- "[Follow-up] Tell me more about..."

**Pass Criteria**: 
- AI provides relevant answers
- Citations match question content
- No errors in backend logs
- Memory clears successfully

---

## 🧪 Running Automated Tests

### Test All Features (10 min)
```bash
# Terminal 3: Run automated API tests
cd d:\WORK\RET_App
python test_all_features.py
```

**Expected Output**:
```
======================================================================
  RET v4 Comprehensive API Test Suite
======================================================================
API Base URL: http://localhost:8000/api

Test 1: Backend Health Check
  → GET http://localhost:8000/health
  ✓ Status: 200
  ✅ Backend is healthy: {'status': 'ok', 'app': 'RET-v4'}

Test 2: Authentication - Login
  → POST http://localhost:8000/api/auth/login
  ✓ Status: 200
  ✅ Login successful, token saved

Test 3: Get Current User (/me)
  → GET http://localhost:8000/api/auth/me
  ✓ Status: 200
  ✅ Got user info: admin

...

======================================================================
SUMMARY: 11/11 tests passed
======================================================================

✅ All tests passed!
```

---

## 📊 Test Results Checklist

### Backend Tests
- [ ] Health endpoint responds
- [ ] API documentation loads (/docs)
- [ ] Database connection successful
- [ ] Demo users created

### Authentication Tests
- [ ] Login successful
- [ ] Token stored in memory
- [ ] Token refresh works
- [ ] Logout clears data
- [ ] 401 handling works

### File Processing Tests
- [ ] ZIP upload succeeds
- [ ] XML detection works
- [ ] Groups identified correctly
- [ ] Session created

### Conversion Tests
- [ ] CSV conversion succeeds
- [ ] Job tracking works
- [ ] Download available
- [ ] CSV data valid

### Comparison Tests
- [ ] File upload works
- [ ] Comparison completes
- [ ] Similarity score calculated
- [ ] Deltas display correctly

### AI/RAG Tests ⭐ CRITICAL
- [ ] Groups can be selected for indexing
- [ ] Indexing completes without errors
- [ ] Chroma DB created
- [ ] Chat interface responds
- [ ] Answers are relevant
- [ ] Citations display
- [ ] Memory clears successfully

### Admin Tests
- [ ] Admin button visible (admins only)
- [ ] Admin panel loads
- [ ] User management accessible

### Frontend Tests
- [ ] All tabs load
- [ ] Theme toggle works
- [ ] Responsive design
- [ ] No console errors

---

## 🔍 Troubleshooting Guide

### Backend Won't Start
```
Symptom: Connection refused or module not found

Fix:
1. Check Python: python --version (need 3.10+)
2. Create venv: python -m venv .venv
3. Activate: .venv\Scripts\Activate.ps1
4. Install: pip install -r requirements.txt
5. Check port: netstat -ano | findstr :8000
6. Start: uvicorn api.main:app --reload
```

### Login Fails
```
Symptom: 401 Unauthorized or invalid credentials

Fix:
1. Create users: python scripts/demo_users.py
2. Check .env: Verify JWT_SECRET_KEY is set
3. Check DB: python scripts/init_db.py
4. Use correct password from step 1
```

### AI Chat Empty Response
```
Symptom: Chat returns empty or "no context"

Fix:
1. Verify indexing completed successfully
2. Check Azure credentials in .env
3. Check backend logs for API errors
4. Verify Chroma DB folder created:
   runtime/sessions/{session_id}/ai_index/
5. Try re-indexing same group
```

### ZIP Scan Fails
```
Symptom: Upload fails or no groups detected

Fix:
1. Check file is valid ZIP
2. Verify contains XML files
3. Check extracted folder created:
   runtime/sessions/{session_id}/extracted/
4. Check file permissions
```

### Frontend Shows 404
```
Symptom: Blank page or component missing

Fix:
1. Check backend running: http://localhost:8000/docs
2. Check frontend running: npm run dev output
3. Clear browser cache: Ctrl+Shift+Delete
4. Check console errors: F12 > Console tab
5. Restart frontend: Stop npm, run npm run dev again
```

---

## 📈 Performance Expectations

### Speed Benchmarks

| Operation | Expected Time | Notes |
|-----------|---|---|
| Backend startup | 3-5s | First run may be slower |
| Frontend startup | 5-10s | Includes npm compilation |
| ZIP scan | 1-2s | Just detection, not extraction |
| CSV conversion (100 rows) | 3-5s | Async, progress shown |
| Indexing (10 documents) | 10-20s | Includes Azure API calls |
| AI chat response | 2-5s | Including embedding + GPT-4 |
| Login | 1-2s | Token generation |

### Network Requests Count

| Feature | Requests | Total Time |
|---------|---|---|
| Login flow | 2-3 | 1-2s |
| ZIP scan | 1 | 1-2s |
| Conversion | 3-5 | 5-10s (mostly async wait) |
| AI index | 5-100 | 10-30s (Azure API calls) |
| AI chat | 4-6 | 2-5s |

---

## 🎯 Success Criteria

### Minimal Success
- ✅ Backend starts without errors
- ✅ Frontend loads and displays login
- ✅ Can login with demo credentials
- ✅ Health endpoint responds

### Full Success
- ✅ All minimal criteria
- ✅ ZIP upload and scan works
- ✅ XML to CSV conversion works
- ✅ File comparison works
- ✅ Can index groups to Chroma
- ✅ AI chat responds with relevant answers
- ✅ Citations display correctly

### Production Ready
- ✅ All full criteria
- ✅ No errors in logs
- ✅ Performance meets benchmarks
- ✅ Admin features work
- ✅ Session cleanup on logout
- ✅ Token refresh automatic
- ✅ No data leakage between sessions

---

## 📝 Test Report Template

After running tests, use this to document results:

```markdown
# RET v4 Testing Report

**Date**: [Date]
**Tester**: [Name]
**Duration**: [minutes]

## Results Summary

### Status: ✅ PASS / ⚠️ PARTIAL / ❌ FAIL

### Feature Breakdown
- Backend: ✅ / ⚠️ / ❌
- Frontend: ✅ / ⚠️ / ❌
- Authentication: ✅ / ⚠️ / ❌
- File Conversion: ✅ / ⚠️ / ❌
- Comparison: ✅ / ⚠️ / ❌
- AI Indexing: ✅ / ⚠️ / ❌ (CRITICAL)
- AI Chat: ✅ / ⚠️ / ❌ (CRITICAL)

### Issues Found
[List any issues with severity: HIGH/MEDIUM/LOW]

### Performance Notes
[Record actual vs expected times]

### Recommendations
[Suggestions for improvements]

### Signed Off
Tester: __________ Date: __________ Time: __________
```

---

## 🔗 Important Resources

### Files & Folders
- **Backend**: `d:\WORK\RET_App\backend\`
- **Frontend**: `d:\WORK\RET_App\frontend\`
- **Example Data**: `d:\WORK\RET_App\Examples\BIg_test-examples\`
- **Tests**: `d:\WORK\RET_App\test_all_features.py`

### Documentation
- **Full Guide**: [COMPREHENSIVE_TEST_GUIDE.md](COMPREHENSIVE_TEST_GUIDE.md)
- **Manual Checklist**: [MANUAL_TESTING_CHECKLIST.md](MANUAL_TESTING_CHECKLIST.md)
- **Features Docs**: [FEATURES_DOCUMENTATION.md](FEATURES_DOCUMENTATION.md)

### APIs
- **Swagger UI**: http://localhost:8000/docs
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## ✅ Next Steps After Testing

### If All Tests Pass ✅
1. Document final test results
2. Note any performance improvements observed
3. Archive testing report
4. Application ready for staging/production
5. Consider load testing for production scale

### If Some Tests Fail ⚠️
1. Note which features failed
2. Check troubleshooting guide
3. Verify configuration (especially .env)
4. Check backend logs for errors
5. Re-run failed tests after fixing issues

### If Critical Features Fail ❌
1. Do not proceed to production
2. Check Azure OpenAI credentials
3. Verify database connection
4. Review backend logs thoroughly
5. Contact development team

---

**Quick Links**:
- 🚀 [Start Services](#-5-minute-quick-test)
- 📋 [Full Testing Path](#-full-testing-path-30-minutes)
- 🧪 [Run Automated Tests](#-running-automated-tests)
- 🔍 [Troubleshooting](#-troubleshooting-guide)

**Last Updated**: January 27, 2026  
**Document Version**: 1.0
