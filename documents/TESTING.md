# RET v4 Integration Checklist & Testing Guide

## Pre-Launch Verification

### Backend Setup Checklist
- [ ] Python 3.10+ installed (`python --version`)
- [ ] Virtual environment created (`.venv` folder exists)
- [ ] Dependencies installed (`pip install -r requirements.txt` succeeded)
- [ ] `.env` file configured with:
  - [ ] `DATABASE_URL=sqlite:///./ret_app.db`
  - [ ] `JWT_SECRET_KEY` set (min 32 chars)
  - [ ] `CORS_ORIGINS` includes `http://localhost:3000`
  - [ ] `REDIS_URL` correct if using Celery
- [ ] Database initialized (`ret_app.db` exists in backend folder)
- [ ] Admin user created (optional but recommended)

### Frontend Setup Checklist
- [ ] Node.js 18+ installed (`node --version`)
- [ ] npm/yarn installed (`npm --version`)
- [ ] Dependencies installed (`node_modules` folder exists)
- [ ] `.env` file has `VITE_API_BASE=http://localhost:8000/api`
- [ ] `vite.config.js` proxy configured for `/api`

### System Services Checklist
- [ ] Redis running (if using Celery jobs):
  - [ ] `redis://localhost:6379` accessible
  - [ ] Or skip if using SQLite for job storage

---

## Integration Test Suite

### Test 1: Backend Health Check

**Objective**: Verify backend is running and responding

**Steps**:
1. Start backend: `uvicorn api.main:app --reload`
2. Open browser: `http://localhost:8000/docs`
3. Look for Swagger UI interface
4. Call GET `/health` endpoint
5. Expected response: `{"status": "ok"}`

**Pass Criteria**: ✓ Swagger UI loads, health check returns 200

---

### Test 2: Frontend Health Check

**Objective**: Verify frontend bundles and loads

**Steps**:
1. Start frontend: `npm run dev`
2. Open browser: `http://localhost:3000`
3. Check browser console (F12)
4. Verify no errors appear

**Pass Criteria**: ✓ App loads without errors, login form visible

---

### Test 3: Login Flow

**Objective**: Test complete authentication chain

**Steps**:
1. Frontend: Open login page
2. Backend: Create test user
   ```bash
   cd backend
   python scripts/create_admin.py  # or create via /api/admin/users
   ```
3. Frontend: Enter username/password
4. Frontend: Click login button
5. Check console for requests

**Expected Flow**:
```
Frontend → POST /api/auth/login
Backend → Validate credentials
Backend → Issue tokens & create session
Backend → Return {access_token, refresh_token, user}
Frontend → Store access_token in memory
Frontend → Redirect to /app
```

**Pass Criteria**: 
- ✓ Login successful
- ✓ Redirected to main page
- ✓ User info displayed (top right)
- ✓ No 401/403 errors

---

### Test 4: API Request with Token

**Objective**: Verify token injection and authorization

**Steps**:
1. After login, open browser DevTools (F12)
2. Go to Network tab
3. Call any protected endpoint (e.g., `/api/jobs`)
4. Check headers in request

**Expected Headers**:
```
Authorization: Bearer eyJhbGc...
```

**Pass Criteria**: ✓ Authorization header present in API calls

---

### Test 5: Token Refresh

**Objective**: Test automatic token refresh on 401

**Steps**:
1. Login successfully
2. Wait for access token to expire (or manually expire in devtools)
3. Make API request
4. Monitor Network tab

**Expected Behavior**:
```
1. Initial request → 401 Unauthorized
2. Intercept: POST /api/auth/refresh
3. Backend: Rotate refresh token
4. Frontend: Store new access_token
5. Retry original request → 200 OK
```

**Pass Criteria**: ✓ Request retried automatically after refresh

---

### Test 6: CORS Validation

**Objective**: Verify CORS headers allow frontend<->backend communication

**Steps**:
1. Start both frontend and backend
2. Open DevTools Network tab
3. Make API request from frontend
4. Check response headers

**Expected Headers** (response):
```
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
```

**Pass Criteria**: ✓ No CORS errors in browser console

---

### Test 7: File Upload (Conversion)

**Objective**: Test file upload and conversion workflow

**Steps**:
1. Login successfully
2. Navigate to "Conversion" tab (if available)
3. Upload a ZIP file with sample XMLs
4. Click "Scan" or "Convert"
5. Monitor requests

**Expected Flow**:
```
Frontend → POST /api/conversion/scan (multipart/form-data)
Backend → Process upload, return session_id
Frontend → Store session_id
Frontend → POST /api/conversion/convert {session_id}
Backend → Create Job, enqueue conversion_task
Backend → Return {job_id}
Frontend → Poll GET /api/jobs/{job_id}
```

**Pass Criteria**: ✓ File uploaded, session created, job started

---

### Test 8: Logout Flow

**Objective**: Test session cleanup and token invalidation

**Steps**:
1. While logged in, click Logout button
2. Check browser storage/cookies
3. Try accessing protected route

**Expected Behavior**:
```
Frontend → POST /api/auth/logout
Backend → Invalidate session
Backend → Clear refresh_token cookie
Frontend → Clear auth store
Frontend → Redirect to /login
```

**Verification**:
- ✓ Token cleared from memory
- ✓ Redirect to login page
- ✓ Cannot access /app without re-login

---

### Test 9: Error Handling

**Objective**: Verify graceful error handling

**Steps**:
1. Try login with wrong password
2. Try accessing /api/me without token
3. Try accessing /admin without admin role

**Expected Behavior**:
```
Wrong password → 401 Unauthorized + error message
No token → 401 Unauthorized + redirect to login
No admin → 403 Forbidden
```

**Pass Criteria**: ✓ Proper HTTP status codes, error messages shown

---

### Test 10: Database Persistence

**Objective**: Verify data persists across restarts

**Steps**:
1. Create a user via frontend or admin endpoint
2. Stop backend
3. Restart backend
4. Login with same credentials
5. Verify user data still exists

**Pass Criteria**: ✓ User data persists, login still works

---

## Manual Testing Checklist

### Functionality Tests

#### Authentication
- [ ] Login with valid credentials
- [ ] Login with invalid credentials shows error
- [ ] Logout clears session
- [ ] Password reset request works
- [ ] Password reset confirm works
- [ ] Accessing protected page without token redirects to login
- [ ] Token refresh works automatically

#### File Operations
- [ ] ZIP file upload succeeds
- [ ] File scan shows file list
- [ ] Conversion starts successfully
- [ ] Job status polls correctly
- [ ] Download converted files
- [ ] Large files handled properly

#### User Interface
- [ ] All pages load without errors
- [ ] Theme switcher works (if implemented)
- [ ] Responsive design on mobile/tablet
- [ ] Dark mode CSS variables apply
- [ ] Form validation shows errors
- [ ] Loading states display correctly

#### Admin Functions (if admin user)
- [ ] View users list
- [ ] Create new user
- [ ] Edit user role
- [ ] Delete user
- [ ] View audit logs
- [ ] Session cleanup

---

## Performance Testing

### Load Test
- [ ] 10 concurrent users can login
- [ ] File conversion handles 5 concurrent jobs
- [ ] API response time < 2 seconds (excluding file ops)

### Memory Test
- [ ] Backend memory stable after 1 hour
- [ ] Frontend memory stable after 1 hour
- [ ] No memory leaks on page navigation

### Database Test
- [ ] SQLite performs well with 1000 records
- [ ] Queries complete in < 100ms
- [ ] Indexes working properly

---

## Debugging Guide

### Backend Debugging

**Enable verbose logging**:
```python
# In .env
LOG_LEVEL=DEBUG
```

**Check logs**:
```bash
# Terminal where backend runs - watch for errors
```

**Database inspection**:
```bash
# SQLite CLI
sqlite3 ret_app.db
sqlite> .tables
sqlite> SELECT * FROM users;
```

**JWT token inspection**:
```javascript
// In browser console
const token = 'eyJ...'
const parts = token.split('.')
const payload = JSON.parse(atob(parts[1]))
console.log(payload)
```

### Frontend Debugging

**Vue DevTools**:
- Install Vue DevTools extension in Chrome
- Inspect Pinia state in DevTools
- Watch components re-render

**Network Debugging**:
1. Open DevTools (F12)
2. Network tab → API requests
3. Check headers and responses
4. Look for CORS errors

**Console Errors**:
1. Check browser console (F12 → Console)
2. Look for red errors
3. Check "Issues" tab for warnings

---

## Common Issues & Solutions

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| 401 Unauthorized | Expired/invalid token | Logout & login again |
| CORS error | Wrong origins in config | Update CORS_ORIGINS in .env |
| Connection refused | Backend not running | Start uvicorn |
| Module not found | Missing dependency | `pip install -r requirements.txt` |
| Port already in use | Service already running | Kill process or change port |
| Database locked | Concurrent access | Restart backend |
| Redis connection error | Redis not running | Start Redis or skip for local dev |

---

## Sign-Off Checklist

**Developer**: _________________ **Date**: _____________

- [ ] All 10 integration tests pass
- [ ] All manual tests pass
- [ ] No console errors or warnings
- [ ] Performance acceptable
- [ ] Documentation complete
- [ ] Code follows project conventions
- [ ] Ready for staging/production

---

## Notes

```
Test Date: _______________
Tester: __________________
Environment: ______________
Notes: _____________________
_____________________________
_____________________________
```

---

**Document Version**: 1.0
**Last Updated**: January 25, 2026
