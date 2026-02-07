# Known Issues & Manual Interventions

## Issues Requiring Manual Intervention

### 1. Extra Modal - "Old Model" Selection (CONFIRMED 2026-02-05)

**Description:**
An extra modal sometimes pops up during the Easy Apply process that requires clicking on "old model" or similar option.

**Current Status:**
- ⚠️ Requires manual click
- User had to manually click during successful test
- Bot doesn't detect/handle this modal automatically

**Impact:**
- Application flow blocked until manual click
- Reduces automation effectiveness
- May not occur on every application

**Solution Needed:**
Add modal detection and automatic click handling in `easy_apply_bot.py`:

```python
async def _handle_extra_modals(self):
    """Handle unexpected LinkedIn modals that may appear."""

    # Check for "old model" / "new model" selection modal
    modal_selectors = [
        'button:has-text("Old")',
        'button:has-text("old model")',
        'button:has-text("Previous")',
        '[data-test-modal-close-btn]',
        # Add more as we discover them
    ]

    for selector in modal_selectors:
        try:
            button = self.session.page.locator(selector).first
            if await button.is_visible(timeout=1000):
                await button.click()
                logger.info(f"Clicked extra modal button: {selector}")
                await human_delay(1, 2)
                return True
        except:
            continue

    return False
```

**Where to Add:**
- Call `_handle_extra_modals()` after clicking Easy Apply
- Call before each form step
- Call before clicking Next/Submit buttons

**Priority:** HIGH - Blocks automation

### 2. Search Field Overlay (INTERMITTENT)

**Description:**
Filling the "Search..." field triggers LinkedIn search dropdown overlay.

**Current Status:**
- ⚠️ Intermittent - sometimes blocks Next button, sometimes doesn't
- Modal rendering order seems to affect whether it blocks
- Successful test showed overlay present but didn't block

**Workarounds:**
1. Press Escape after filling search fields
2. Skip fields with label containing "search"
3. Add delay after filling to let overlay settle

**Priority:** MEDIUM - Intermittent, may self-resolve

## Testing Recommendations

**Before declaring "production ready":**
1. Add automatic modal handling
2. Test 5+ applications without manual intervention
3. Monitor for other unexpected modals
4. Add screenshot capture for any detected modals
5. Log all modal types encountered

**Test Coverage Needed:**
- Different companies
- Different job types
- Different form complexity
- Different times of day (LinkedIn A/B testing)

## Workaround Until Fixed

**For now:**
- Run with visible browser (`PLAYWRIGHT_HEADLESS=false`)
- Monitor for popups
- Manually click if needed
- Document which modals appear
- Update bot code with selectors for each modal type
