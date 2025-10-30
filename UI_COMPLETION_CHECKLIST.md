# AskLytics UI/UX Completion Checklist

## Summary of Required Changes

Based on user feedback, the following features need to be added:

### 1. Database Connection Testing (Settings Page)
- [ ] Add connection test form with fields for:
  - Server/Host
  - Database Name  
  - Username
  - Password (masked input)
  - Port (optional)
- [ ] Add "Test Connection" button
- [ ] Show connection status (success/fail) with visual feedback
- [ ] Store connection settings

### 2. Table Selection with Checkboxes (Settings Page)
- [ ] Convert table list to checkboxes
- [ ] Add "Select All" / "Deselect All" toggle button
- [ ] Show count of selected tables
- [ ] Persist selected tables
- [ ] Add "Save Selection" button
- [ ] Visual indication of selected vs available tables

### 3. Dashboard Page Redesign
- [ ] Apply same modern UI theme as chat interface
- [ ] Use consistent color scheme (--primary-color, etc.)
- [ ] Add proper spacing and card layouts
- [ ] Ensure responsive design
- [ ] Add loading states
- [ ] Match navigation and header style

### 4. Mobile Hamburger Close Button
- [ ] Add close/X button inside mobile sidebar
- [ ] Position at top-right of sidebar
- [ ] Only visible on mobile view
- [ ] Properly close sidebar and overlay on click

### 5. Send Button State Management
- [ ] Disable send button when query is submitted
- [ ] Show loading indicator in button
- [ ] Re-enable button only when results are received
- [ ] Handle error cases (re-enable on error)
- [ ] Disable on empty input

### 6. User Feedback Buttons
- [ ] Add thumbs up/down buttons to each result
- [ ] Position feedback buttons in results panel
- [ ] Show feedback state (selected/unselected)
- [ ] Send feedback to `/api/feedback` endpoint
- [ ] Show confirmation message
- [ ] Store feedback per query

## Implementation Priority

1. **HIGH PRIORITY** (Blocking user experience):
   - Send button disable/enable (prevents duplicate queries)
   - Mobile close button (navigation issue)
   - Feedback buttons (core feature)

2. **MEDIUM PRIORITY** (Important features):
   - Table selection (data filtering)
   - Dashboard redesign (consistency)

3. **NORMAL PRIORITY** (Nice to have):
   - Connection testing (advanced feature)

## Technical Notes

### Send Button State
```javascript
// When sending message
sendBtn.disabled = true;
sendBtn.innerHTML = '<i data-feather="loader" class="w-5 h-5 animate-spin"></i>';

// When results received
sendBtn.disabled = false;
sendBtn.innerHTML = '<i data-feather="send" class="w-5 h-5"></i>';
feather.replace();
```

### Feedback Buttons
```javascript
// Add to each result display
<div class="feedback-container">
  <button class="feedback-btn" data-feedback="correct" onclick="submitFeedback('correct', messageId)">
    <i data-feather="thumbs-up"></i>
  </button>
  <button class="feedback-btn" data-feedback="incorrect" onclick="submitFeedback('incorrect', messageId)">
    <i data-feather="thumbs-down"></i>
  </button>
</div>

// Submit function
async function submitFeedback(verdict, messageId) {
  await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: currentSessionId,
      message_id: messageId,
      verdict: verdict
    })
  });
}
```

### Mobile Close Button
```html
<!-- Add inside sidebar, visible only on mobile -->
<button class="mobile-close-btn" id="mobileCloseBtn">
  <i data-feather="x" class="w-6 h-6"></i>
</button>
```

```css
.mobile-close-btn {
  display: none;
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  padding: 0.5rem;
  border-radius: 0.5rem;
  z-index: 60;
}

@media (max-width: 768px) {
  .mobile-close-btn {
    display: block;
  }
}
```

### Table Selection
```javascript
// Load tables with checkboxes
async function loadTablesWithSelection() {
  const response = await fetch('/api/settings/tables/list');
  const data = await response.json();
  
  let html = '<div class="table-selection-header">';
  html += '<button class="btn btn-sm btn-secondary" id="selectAllBtn">Select All</button>';
  html += '<span class="text-sm text-gray-600" id="selectedCount">0 selected</span>';
  html += '</div>';
  
  html += '<div class="table-list">';
  data.tables.forEach(table => {
    html += `
      <label class="table-checkbox">
        <input type="checkbox" name="table" value="${table}" class="table-check">
        <span>${table}</span>
      </label>
    `;
  });
  html += '</div>';
  
  html += '<button class="btn btn-primary mt-3" id="saveTablesBtn">Save Selection</button>';
  
  document.getElementById('tablesList').innerHTML = html;
}
```

## Files to Modify

1. **templates/index.html** - Add feedback buttons, disable send button, mobile close
2. **templates/settings.html** - Add connection test form, table checkboxes
3. **templates/dashboard.html** - Complete redesign with new theme
4. **static/css/asklytics.css** - Add new component styles

## API Endpoints Needed

- `POST /api/settings/db/test` - Test database connection
- `POST /api/settings/tables/save` - Save table selection
- `GET /api/settings/tables/selected` - Get selected tables
- `POST /api/feedback` - Submit user feedback (already exists)

## Next Steps

Would you like me to:
1. Implement all 6 features in order of priority?
2. Focus on specific features first?
3. Create complete updated template files?

Please confirm and I'll proceed with implementation.
