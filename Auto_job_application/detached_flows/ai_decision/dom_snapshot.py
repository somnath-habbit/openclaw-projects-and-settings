"""
DOM Snapshot Engine - Extracts clean, AI-friendly DOM representation from any webpage.

Strips noise (scripts, styles, hidden elements), keeps interactive elements
with their labels and attributes. Output is compact enough for a single AI call (~4000 tokens).

Usage:
    snapshot = await extract_dom_snapshot(page)
    # Returns structured dict with page metadata and interactive elements
"""
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("DOMSnapshot")

# JavaScript to extract interactive elements and page context
EXTRACT_INTERACTIVE_ELEMENTS_JS = """
() => {
    const result = {
        page: {
            title: document.title,
            url: window.location.href,
            headings: [],
            visible_text_blocks: []
        },
        elements: [],
        errors: [],
        progress_indicators: []
    };

    // Get visible headings (h1-h3)
    document.querySelectorAll('h1, h2, h3').forEach(h => {
        const text = h.innerText?.trim();
        if (text && h.offsetParent !== null) {
            result.page.headings.push({
                level: parseInt(h.tagName[1]),
                text: text.substring(0, 100)
            });
        }
    });

    // Get visible text blocks (paragraphs with substantial text)
    document.querySelectorAll('p, .description, [class*="description"], [class*="info"]').forEach(p => {
        const text = p.innerText?.trim();
        if (text && text.length > 20 && text.length < 500 && p.offsetParent !== null) {
            if (result.page.visible_text_blocks.length < 5) {
                result.page.visible_text_blocks.push(text.substring(0, 200));
            }
        }
    });

    // Get progress indicators
    document.querySelectorAll(
        '[role="progressbar"], .progress, [class*="step"], [class*="progress"], [aria-valuenow]'
    ).forEach(el => {
        const text = el.innerText?.trim();
        const value = el.getAttribute('aria-valuenow');
        const max = el.getAttribute('aria-valuemax');
        if (text || value) {
            result.progress_indicators.push({
                text: text?.substring(0, 50) || '',
                value: value,
                max: max
            });
        }
    });

    // Helper: get label for an element
    function getLabel(el) {
        // 1. Explicit <label for="id">
        const id = el.id;
        if (id) {
            // Use CSS.escape for IDs with special chars like []
            const escapedId = typeof CSS !== 'undefined' && CSS.escape
                ? CSS.escape(id) : id.replace(/([[\]"])/g, '\\$1');
            try {
                const label = document.querySelector(`label[for="${escapedId}"]`);
                if (label) return label.innerText?.trim();
            } catch(e) { /* invalid selector, skip */ }
        }

        // 2. aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel.trim();

        // 3. aria-labelledby
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.innerText?.trim();
        }

        // 4. Closest label ancestor
        const parentLabel = el.closest('label');
        if (parentLabel) {
            // Get label text excluding the input itself
            const clone = parentLabel.cloneNode(true);
            clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
            const text = clone.innerText?.trim();
            if (text) return text;
        }

        // 5. Placeholder
        const placeholder = el.getAttribute('placeholder');
        if (placeholder) return placeholder.trim();

        // 6. Previous sibling label or nearby text
        let prev = el.previousElementSibling;
        if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'DIV')) {
            const text = prev.innerText?.trim();
            if (text && text.length < 100) return text;
        }

        // 7. Parent fieldset legend
        const fieldset = el.closest('fieldset');
        if (fieldset) {
            const legend = fieldset.querySelector('legend');
            if (legend) return legend.innerText?.trim();
        }

        // 8. Name attribute as fallback
        const name = el.getAttribute('name');
        if (name) return name.replace(/[_-]/g, ' ').replace(/([A-Z])/g, ' $1').trim();

        return '';
    }

    // Helper: check if element is in viewport
    function isInViewport(el) {
        const rect = el.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    // Helper: check if element is visible
    function isVisible(el) {
        if (!el.offsetParent && el.tagName !== 'BODY') return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }

    // Helper: get nearby error messages
    function getNearbyError(el) {
        // Check for error siblings
        const parent = el.parentElement;
        if (!parent) return null;

        const errorSelectors = [
            '[role="alert"]',
            '.error', '.error-message', '.field-error',
            '[class*="error"]', '[class*="invalid"]',
            '.artdeco-inline-feedback--error'
        ];

        for (const sel of errorSelectors) {
            const error = parent.querySelector(sel);
            if (error && isVisible(error)) {
                return error.innerText?.trim();
            }
        }
        return null;
    }

    let elementIndex = 0;

    // Extract all interactive elements
    const interactiveSelectors = [
        'input:not([type="hidden"])',
        'textarea',
        'select',
        '[role="combobox"]',
        '[role="listbox"]',
        '[contenteditable="true"]',
        'button',
        'a[href]',
        '[role="button"]',
        '[role="checkbox"]',
        '[role="radio"]',
        'input[type="file"]'
    ];

    const allElements = document.querySelectorAll(interactiveSelectors.join(', '));

    allElements.forEach(el => {
        if (!isVisible(el)) return;

        const tagName = el.tagName.toLowerCase();
        const type = el.getAttribute('type') || '';
        const role = el.getAttribute('role') || '';
        const label = getLabel(el);
        const inViewport = isInViewport(el);
        const error = getNearbyError(el);

        let elementType = 'unknown';
        let currentValue = '';
        let options = [];
        let isRequired = el.hasAttribute('required') || el.getAttribute('aria-required') === 'true';

        // Classify element type
        // Check role="combobox" BEFORE input type (React Select uses <input type="text" role="combobox">)
        if (role === 'combobox') {
            elementType = 'combobox';
            currentValue = el.innerText?.trim() || el.value || '';
        } else if (tagName === 'input') {
            switch (type) {
                case 'text': elementType = 'text_input'; break;
                case 'email': elementType = 'email_input'; break;
                case 'password': elementType = 'password_input'; break;
                case 'number': elementType = 'number_input'; break;
                case 'tel': elementType = 'phone_input'; break;
                case 'url': elementType = 'url_input'; break;
                case 'date': elementType = 'date_input'; break;
                case 'file': elementType = 'file_upload'; break;
                case 'checkbox': elementType = 'checkbox'; break;
                case 'radio': elementType = 'radio'; break;
                case 'submit': elementType = 'submit_button'; break;
                default: elementType = 'text_input';
            }
            currentValue = el.value || '';
            if (type === 'checkbox' || type === 'radio') {
                currentValue = el.checked ? 'checked' : 'unchecked';
            }
        } else if (tagName === 'textarea') {
            elementType = 'textarea';
            currentValue = el.value || '';
        } else if (tagName === 'select') {
            elementType = 'select';
            currentValue = el.options[el.selectedIndex]?.text || '';
            options = Array.from(el.options).map(o => ({
                value: o.value,
                text: o.text?.trim(),
                selected: o.selected
            })).filter(o => o.value && o.text);
        } else if (tagName === 'button' || role === 'button' || type === 'submit') {
            elementType = 'button';
            currentValue = el.innerText?.trim() || el.value || '';
        } else if (tagName === 'a') {
            elementType = 'link';
            currentValue = el.innerText?.trim() || '';
        } else if (el.getAttribute('contenteditable') === 'true') {
            elementType = 'rich_text';
            currentValue = el.innerText?.trim() || '';
        } else if (role === 'checkbox') {
            elementType = 'checkbox';
            currentValue = el.getAttribute('aria-checked') || 'unchecked';
        } else if (role === 'radio') {
            elementType = 'radio';
            currentValue = el.getAttribute('aria-checked') || 'unchecked';
        } else if (role === 'listbox') {
            elementType = 'listbox';
            currentValue = '';
        }

        // Build selector for reliable relocation
        let selector = '';
        if (el.id) {
            // Use CSS.escape() to handle special chars like [] in IDs
            selector = typeof CSS !== 'undefined' && CSS.escape
                ? `#${CSS.escape(el.id)}`
                : `[id="${el.id.replace(/"/g, '\\\\"')}"]`;
        } else if (el.getAttribute('name')) {
            selector = `${tagName}[name="${el.getAttribute('name')}"]`;
        } else if (el.getAttribute('data-testid')) {
            selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
        }

        // Determine field category based on label and type
        let fieldCategory = 'unknown';
        const labelLower = (label || '').toLowerCase();
        if (['email_input', 'password_input'].includes(elementType)) {
            fieldCategory = 'credentials';
        } else if (/\b(name|first|last|middle)\b/.test(labelLower)) {
            fieldCategory = 'personal_info';
        } else if (/\b(phone|mobile|tel)\b/.test(labelLower)) {
            fieldCategory = 'contact';
        } else if (/\b(email)\b/.test(labelLower)) {
            fieldCategory = 'contact';
        } else if (/\b(education|degree|university|college|school|gpa)\b/.test(labelLower)) {
            fieldCategory = 'education';
        } else if (/\b(experience|years|company|role|title|position)\b/.test(labelLower)) {
            fieldCategory = 'experience';
        } else if (/\b(salary|ctc|compensation|pay|lpa)\b/.test(labelLower)) {
            fieldCategory = 'compensation';
        } else if (/\b(resume|cv|cover.letter|portfolio)\b/.test(labelLower)) {
            fieldCategory = 'documents';
        } else if (/\b(skill|proficien|technolog|language)\b/.test(labelLower)) {
            fieldCategory = 'skills';
        } else if (elementType === 'button' || elementType === 'link') {
            fieldCategory = 'action';
        }

        const elementData = {
            index: elementIndex++,
            type: elementType,
            tag: tagName,
            label: label.substring(0, 150),
            required: isRequired,
            current_value: currentValue.substring(0, 200),
            in_viewport: inViewport,
            field_category: fieldCategory,
            attributes: {}
        };

        // Add relevant attributes
        if (selector) elementData.attributes.selector = selector;
        if (el.id) elementData.attributes.id = el.id;
        if (el.getAttribute('inputmode')) elementData.attributes.inputmode = el.getAttribute('inputmode');
        if (el.getAttribute('pattern')) elementData.attributes.pattern = el.getAttribute('pattern');
        if (el.getAttribute('maxlength')) elementData.attributes.maxlength = el.getAttribute('maxlength');
        if (el.getAttribute('autocomplete')) elementData.attributes.autocomplete = el.getAttribute('autocomplete');
        if (options.length > 0) elementData.options = options;
        if (error) elementData.error = error;

        // For radio/checkbox groups, include the group name
        if ((type === 'radio' || type === 'checkbox') && el.getAttribute('name')) {
            elementData.attributes.group_name = el.getAttribute('name');
        }

        result.elements.push(elementData);
    });

    // Get visible error messages not attached to specific fields
    document.querySelectorAll(
        '[role="alert"], .alert-danger, .error-summary, .form-error, [class*="error-message"]'
    ).forEach(el => {
        if (isVisible(el)) {
            const text = el.innerText?.trim();
            if (text && text.length > 5 && text.length < 500) {
                result.errors.push(text);
            }
        }
    });

    return result;
}
"""


async def extract_dom_snapshot(page, scope=None) -> Dict:
    """
    Extract a clean, AI-friendly DOM snapshot from the page.

    Args:
        page: Playwright page object
        scope: Optional Playwright locator to scope extraction (e.g., a modal)
               If None, extracts from the full page.

    Returns:
        Dict with structure:
        {
            "page": {"title", "url", "headings", "visible_text_blocks"},
            "elements": [...interactive elements...],
            "errors": [...visible error messages...],
            "progress_indicators": [...]
        }
    """
    try:
        if scope:
            # Run extraction within a scoped element
            snapshot = await scope.evaluate(f"""
                (scopeEl) => {{
                    // Override document.querySelectorAll within scope
                    const origQSA = document.querySelectorAll.bind(document);
                    const scopedQSA = scopeEl.querySelectorAll.bind(scopeEl);

                    // Temporarily patch for the extraction
                    const extractFn = {EXTRACT_INTERACTIVE_ELEMENTS_JS};

                    // We need a modified version that scopes to the element
                    // For now, run on full page and filter by scope
                    return extractFn();
                }}
            """)
            # Filter elements to only those within the scope
            # (The JS runs on full page; we post-filter here)
        else:
            snapshot = await page.evaluate(EXTRACT_INTERACTIVE_ELEMENTS_JS)

        element_count = len(snapshot.get('elements', []))
        error_count = len(snapshot.get('errors', []))
        logger.info(
            f"DOM snapshot: {element_count} elements, {error_count} errors, "
            f"URL: {snapshot['page']['url'][:80]}"
        )

        return snapshot

    except Exception as e:
        logger.error(f"DOM snapshot extraction failed: {e}")
        return {
            "page": {"title": "", "url": "", "headings": [], "visible_text_blocks": []},
            "elements": [],
            "errors": [f"Extraction failed: {str(e)}"],
            "progress_indicators": []
        }


def snapshot_to_text(snapshot: Dict, max_elements: int = 50) -> str:
    """
    Convert a DOM snapshot to a compact text representation for AI prompts.

    Keeps it under ~4000 tokens for efficient AI processing.

    Args:
        snapshot: DOM snapshot dict from extract_dom_snapshot()
        max_elements: Maximum number of elements to include

    Returns:
        Compact text representation of the page
    """
    lines = []

    # Page info
    page = snapshot.get('page', {})
    lines.append(f"Page: {page.get('title', 'Untitled')}")
    lines.append(f"URL: {page.get('url', 'unknown')}")

    # Headings
    headings = page.get('headings', [])
    if headings:
        for h in headings[:5]:
            lines.append(f"{'#' * h['level']} {h['text']}")

    # Progress indicators
    progress = snapshot.get('progress_indicators', [])
    if progress:
        for p in progress[:3]:
            text = p.get('text', '')
            value = p.get('value', '')
            if text or value:
                lines.append(f"Progress: {text} {value}/{p.get('max', '?')}")

    # Errors
    errors = snapshot.get('errors', [])
    if errors:
        lines.append("\nErrors:")
        for err in errors[:5]:
            lines.append(f"  ! {err}")

    # Interactive elements
    elements = snapshot.get('elements', [])
    if elements:
        lines.append(f"\nInteractive Elements ({len(elements)} total):")

        # Group by category for readability
        form_fields = []
        buttons = []
        other = []

        for el in elements[:max_elements]:
            if el['type'] in ('button', 'submit_button', 'link'):
                buttons.append(el)
            elif el['field_category'] == 'action':
                buttons.append(el)
            else:
                form_fields.append(el)

        # Form fields
        if form_fields:
            lines.append("\n  Form Fields:")
            for el in form_fields:
                required = "*" if el.get('required') else ""
                value_info = f" = \"{el['current_value']}\"" if el.get('current_value') else ""
                viewport = "" if el.get('in_viewport') else " [below fold]"
                error = f" ERROR: {el['error']}" if el.get('error') else ""

                line = f"  [{el['index']}] {el['type']}: {el['label']}{required}{value_info}{viewport}{error}"

                # Add options for selects
                if el.get('options'):
                    opts = [o['text'] for o in el['options'][:10]]
                    line += f" Options: [{', '.join(opts)}]"

                lines.append(line)

        # Buttons and actions
        if buttons:
            lines.append("\n  Buttons/Actions:")
            for el in buttons:
                viewport = "" if el.get('in_viewport') else " [below fold]"
                lines.append(
                    f"  [{el['index']}] {el['type']}: {el.get('label') or el.get('current_value', 'unlabeled')}{viewport}"
                )

    # Visible text blocks (truncated)
    text_blocks = page.get('visible_text_blocks', [])
    if text_blocks:
        lines.append("\nPage Context:")
        for block in text_blocks[:3]:
            lines.append(f"  {block[:150]}")

    return '\n'.join(lines)


def get_form_fields_only(snapshot: Dict) -> List[Dict]:
    """
    Extract only fillable form fields from snapshot (no buttons/links).

    Returns:
        List of element dicts that are form fields (inputs, selects, textareas, etc.)
    """
    form_types = {
        'text_input', 'email_input', 'password_input', 'number_input',
        'phone_input', 'url_input', 'date_input', 'file_upload',
        'textarea', 'select', 'combobox', 'checkbox', 'radio',
        'rich_text', 'listbox'
    }

    return [
        el for el in snapshot.get('elements', [])
        if el['type'] in form_types
    ]


def get_buttons(snapshot: Dict) -> List[Dict]:
    """
    Extract only buttons and action elements from snapshot.

    Returns:
        List of element dicts that are buttons or action links
    """
    action_types = {'button', 'submit_button', 'link'}

    return [
        el for el in snapshot.get('elements', [])
        if el['type'] in action_types or el.get('field_category') == 'action'
    ]


def get_unfilled_fields(snapshot: Dict) -> List[Dict]:
    """
    Get form fields that don't have a value yet (need to be filled).

    Returns:
        List of element dicts that are empty/unfilled
    """
    fields = get_form_fields_only(snapshot)
    unfilled = []

    for field in fields:
        value = field.get('current_value', '').strip()

        # Skip if already has a value
        if value and value not in ('unchecked', ''):
            # Check if it's a placeholder value for selects
            if field['type'] == 'select':
                placeholder_words = ['select', 'choose', 'please', '--', '...']
                if any(pw in value.lower() for pw in placeholder_words):
                    unfilled.append(field)
                    continue
            continue

        unfilled.append(field)

    return unfilled
