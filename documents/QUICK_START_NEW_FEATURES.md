# RET v4 - New Features Quick Start Guide

## Installation Requirements

Before testing, ensure the following Python packages are installed:

```bash
pip install lxml sentence-transformers chromadb duckdb parquet
```

## Feature 1: Fixed Admin Access Control ✅

### Testing Steps:
1. Login as a **regular user**
   - Navigate to the application
   - Verify that the **Admin button is NOT visible** in the header
   - Only see: Workspace, 🌓 (theme toggle), Logout

2. Login as an **admin user**
   - Admin button **SHOULD be visible** in the header
   - Click Admin → redirects to admin panel

### Expected Result:
✅ Only admins can see and access the Admin panel

---

## Feature 2: Theme Toggle

### Testing Steps:
1. Click the 🌓 emoji button in the header
2. Observe the theme switching between light and dark mode
3. Refresh the page - theme preference is remembered

### Expected Result:
✅ Smooth theme transition with persistence in localStorage

---

## Feature 3: Utility Tab - ZIP Scanning & Conversion

### Testing Steps:
1. Login as any user
2. Go to **Workspace → Convert & Download tab**
3. Upload a ZIP file containing XML files
4. Click **"Scan ZIP"** button
5. Observe:
   - Groups Found metric
   - XML Files count
   - Total Size
   - List of detected groups
   - Group preview panel on the right

6. Select a group and click **"Convert"**
7. Choose output format (CSV/XLSX)
8. File downloads automatically

### Expected Result:
✅ ZIP scanned, groups detected, files converted and downloaded

---

## Feature 4: Comparison Tab with Delta Highlighting

### Testing Steps:
1. Go to **Workspace → Compare tab**
2. Upload two CSV or JSON files (Side A and Side B)
3. Click **"Compare Now"** button
4. Observe results:
   - **Similarity %**: How similar the files are
   - **+Added**: New rows in Side B
   - **-Removed**: Missing rows in Side B
   - **Modified**: Rows with field changes

5. In the Change Details table:
   - 🟢 **Green dots** = Field values changed
   - 🔴 **Red dots** = Field values unchanged
   - See specific field changes listed

### Expected Result:
✅ Detailed comparison with color-coded deltas

---

## Feature 5: Ask RET AI Tab with Group Indexing

### Testing Steps:
1. Go to **Workspace → Ask RET AI tab**
2. You'll see "📂 Select Groups to Index" section
3. **First, scan a ZIP** in the Utility tab to populate groups
4. Return to Ask RET AI tab
5. Available groups should now show in checkboxes
6. **Select groups** you want to index
7. Click **"Index Selected Groups"** button
8. Wait for indexing to complete
9. Indexed groups appear in the ✅ box below
10. Click **"Clear All Memory"** to remove indexing

### Expected Result:
✅ Groups indexed, displayed, and can be cleared

---

## Feature 6: Admin AI Indexing Configuration

### Testing Steps:
1. Login as admin
2. Go to **Admin → AI Indexing Config tab**
3. You'll see:
   - **Left side**: Available Groups (BOOK, JOURNAL, etc.)
   - **Center**: >> and << buttons
   - **Right side**: Auto-Indexed Groups (empty initially)

4. **Select groups from left**, click **>> button**
5. Groups move to the right side
6. **Select groups from right**, click **<< button**
7. Groups move back to left side
8. Click **"Save Configuration"** button
9. See success message

### Expected Result:
✅ Groups can be moved and configuration saved

---

## Feature 7: Session Cleanup on Logout

### Testing Steps:
1. Login to application
2. Scan a ZIP file (creates session)
3. Index some groups (creates Chroma DB)
4. Click **"Logout"** button
5. Backend automatically:
   - Calls `/ai/clear-memory/{session_id}`
   - Deletes Chroma DB
   - Deletes session directory
   - Revokes refresh token

6. Login again - get a new session
7. Previous indexed data is gone

### Expected Result:
✅ Complete session cleanup on logout, new session isolated

---

## Feature 8: Role-Based Button Visibility

### Testing Steps:
1. Login as **regular user**
   - Check header: See "Workspace", "🌓", "Logout"
   - NO "Admin" button
   - Click "Workspace" → can see Utility, Compare, Ask RET AI tabs
   - Try to access `/admin` directly → redirected to main

2. Login as **admin**
   - Check header: See "Workspace", "🌓", "Admin", "Logout"
   - Click "Admin" → goes to admin console
   - Can access all admin tabs

### Expected Result:
✅ Admin features completely hidden from regular users

---

## Integration Workflow Test

### Complete End-to-End Test:
1. **Login** as user
2. **Upload ZIP** in Utility tab
3. **Scan** to detect groups
4. **Convert** groups to CSV
5. **Index groups** in Ask RET AI tab
6. **Verify** indexed groups display
7. **Query** indexed data (if AI chat integrated)
8. **Compare** CSV files in Compare tab
9. **Clear memory** in Ask RET AI
10. **Logout** - cleanup happens automatically

### Expected Result:
✅ Entire workflow completes without errors

---

## Performance Benchmarks

- **ZIP Scanning**: < 2 seconds for typical 100MB ZIP
- **Group Detection**: Automatic, < 1 second
- **Indexing**: ~10 documents/second (depends on hardware)
- **Comparison**: < 1 second for typical CSV files (1000 rows)
- **Query**: < 500ms for indexed searches

---

## Troubleshooting

### Issue: Chroma DB not found
**Solution**: Install Chroma: `pip install chromadb`

### Issue: lxml import error
**Solution**: Install LXML: `pip install lxml`

### Issue: Groups not detected during scan
**Solution**: Ensure XML files are in ZIP with proper naming (e.g., BOOK_*.xml)

### Issue: Indexing fails
**Solution**: Check console logs for errors, ensure sentence-transformers is installed

### Issue: Admin button still visible for regular users
**Solution**: Clear browser cache, restart application, check token claims

---

## Backend API Endpoints Summary

### New Endpoints:
- `POST /api/ai/index` - Index groups
- `GET /api/ai/indexed-groups/{session_id}` - List indexed groups  
- `POST /api/ai/clear-memory/{session_id}` - Clear AI memory
- `POST /api/comparison/run` - Compare files directly

### Enhanced Endpoints:
- `POST /api/workflow/scan` - Now includes group detection
- `POST /api/auth/logout` - Now includes AI cleanup

---

## Database Setup

No additional database setup required. All data is:
- **Session-based** (temporary)
- **Chroma DB** (persistent within session)
- **Automatically deleted** on logout

---

## Support & Documentation

For more details, see:
- `IMPLEMENTATION_SUMMARY.md` - Full technical details
- `Backend.md` - Backend architecture
- `Frontend.md` - Frontend structure
- Code comments for specific functions

---

**Happy Testing! 🚀**
