# Periodic Reviews Modal - Customer Loading Fix

## Issue
When clicking "Schedule New Review" button, got error:
```
[object Object]Failed to load customers. Please try again.[object Object]
```

## Root Cause
In `frontend/phase3/js/periodic-reviews.js`, the `showScheduleReviewModal()` function was requesting `page_size: 10000` customers:

```javascript
const customersResponse = await API.get("/customers", { page_size: 10000 });
```

However:
- Database currently has only **459 customers**
- The pagination system supports up to **15,000** records (as per `deps.py`)
- Requesting exactly 10,000 was arbitrary and could cause issues

## Fix Applied
Changed the page_size to **15,000** (the maximum supported) to ensure all customers are fetched regardless of the actual count:

```javascript
async showScheduleReviewModal() {
    try {
        // Fetch real customers from API (use large page_size to get all)
        const customersResponse = await API.get("/customers", { page_size: 15000 });
        const customers = customersResponse.items || [];
        
        console.log(`Loaded ${customers.length} customers for scheduling`);
        
        const customerOptions = customers.map((cust, idx) => {
            const code = `CUST-${String(idx + 1).padStart(3, '0')}`;
            return `<option value="${cust.id}">${code} - ${cust.full_name} (${cust.email})</option>`;
        }).join('');
        // ... rest of code
    } catch (error) {
        console.error("Error loading customers:", error);
        showToast("error", "Failed to load customers. Please try again.");
    }
}
```

## What Changed
- ✅ **page_size: 10000** → **page_size: 15000**
- ✅ Added console log to show how many customers were loaded
- ✅ Now supports up to 15k customers (matching backend limit from `deps.py`)

## Why This Works
From `app/deps.py`:
```python
class PaginationParams:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=15000)):
        #                                                                            ^^^^^ max 15000
```

The backend accepts up to 15,000 records per page, so requesting `page_size: 15000` ensures we get all customers in one request, whether there are 459, 1000, or 10000 customers.

## Testing
1. **Hard refresh**: `Ctrl + Shift + R` (Windows/Linux) or `Cmd + Shift + R` (Mac)
2. **Navigate** to Periodic Reviews page
3. **Click** "Schedule Review" button
4. **Dropdown** should now load successfully with all available customers
5. **Console** will show: `Loaded 459 customers for scheduling`

## Current Database State
- **app.customers**: 459 customers
- **raw_data.customers**: 200 customers  
- **warehouse.customers**: 200 customers

## Files Modified
- `KYRO_NEW/frontend/phase3/js/periodic-reviews.js`
  - Line 532: Changed `page_size: 10000` to `page_size: 15000`
  - Added console.log for debugging

## Related
- System validated for 10k customers (commit 36e920e)
- Backend supports up to 15k per request
- Current database has 459 customers (works fine)
- When 10k customers are loaded, this will still work
