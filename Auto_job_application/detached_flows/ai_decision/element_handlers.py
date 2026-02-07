"""
Element Handlers - Specialized interaction handlers for different UI element types.

Each handler knows how to detect, read, fill, and verify a specific type of
web element. This handles the diversity of form controls across job sites.

Usage:
    registry = ElementHandlerRegistry()
    handler = registry.get_handler(element_type)
    await handler.fill(page, element_info, value)
"""
import asyncio
import logging
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("ElementHandlers")


class BaseElementHandler(ABC):
    """Base class for all element handlers."""

    @abstractmethod
    async def fill(self, page, element_info: Dict, value: str) -> bool:
        """
        Fill/interact with the element.

        Args:
            page: Playwright page or locator scope
            element_info: Element dict from DOM snapshot
            value: Value to set

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        """Verify the element has the expected value."""
        pass

    async def _locate(self, page, element_info: Dict):
        """Locate element using best available selector."""
        attrs = element_info.get('attributes', {})

        # Try specific selector first
        selector = attrs.get('selector', '')
        if selector:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    return locator.first
            except Exception:
                # Selector may have special chars — try attribute fallback
                el_id = attrs.get('id', '')
                if el_id:
                    try:
                        fallback = page.locator(f'[id="{el_id}"]')
                        if await fallback.count() > 0:
                            return fallback.first
                    except Exception:
                        pass

        # Fallback: locate by type and index
        tag = element_info.get('tag', 'input')
        el_type = element_info.get('type', '')

        # Build selector based on element type
        type_selectors = {
            'text_input': f'{tag}[type="text"]:visible, {tag}:not([type]):visible',
            'email_input': f'{tag}[type="email"]:visible',
            'password_input': f'{tag}[type="password"]:visible',
            'number_input': f'{tag}[type="number"]:visible',
            'phone_input': f'{tag}[type="tel"]:visible',
            'url_input': f'{tag}[type="url"]:visible',
            'date_input': f'{tag}[type="date"]:visible',
            'textarea': 'textarea:visible',
            'select': 'select:visible',
            'file_upload': f'{tag}[type="file"]',
            'checkbox': f'{tag}[type="checkbox"]:visible',
            'radio': f'{tag}[type="radio"]:visible',
        }

        css = type_selectors.get(el_type, f'{tag}:visible')
        all_elements = await page.locator(css).all()

        index = element_info.get('index', 0)

        # Find by matching label text
        label = element_info.get('label', '')
        if label:
            for elem in all_elements:
                try:
                    elem_label = await self._get_element_label(page, elem)
                    if elem_label and label.lower() in elem_label.lower():
                        return elem
                except Exception:
                    continue

        # Fallback: by position in same-type elements
        # Count how many elements of same type precede this index
        same_type_idx = 0
        for el in await page.locator(css).all():
            if same_type_idx == index:
                return el
            same_type_idx += 1

        # Last resort: use the element_info index against all interactives
        return None

    async def _get_element_label(self, page, elem) -> str:
        """Get label text for an element."""
        try:
            return await elem.evaluate("""
                (el) => {
                    if (el.id) {
                        const label = document.querySelector(`label[for="${el.id}"]`);
                        if (label) return label.innerText?.trim();
                    }
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) return ariaLabel;
                    const placeholder = el.getAttribute('placeholder');
                    if (placeholder) return placeholder;
                    return el.getAttribute('name') || '';
                }
            """)
        except Exception:
            return ''


class TextInputHandler(BaseElementHandler):
    """Handles text, email, number, phone, URL input fields."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            logger.warning(f"Could not locate text input: {element_info.get('label', '?')}")
            return False

        try:
            await elem.click()
            await asyncio.sleep(0.3)

            # Clear existing value
            await elem.fill('')
            await asyncio.sleep(0.2)

            # Type with human-like delay
            await elem.type(str(value), delay=30)
            await asyncio.sleep(0.3)

            logger.info(f"Filled text input '{element_info.get('label', '?')}' with '{value[:30]}...'")
            return True

        except Exception as e:
            logger.error(f"Failed to fill text input: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            actual = await elem.input_value()
            return actual.strip() == expected_value.strip()
        except Exception:
            return False


class NativeSelectHandler(BaseElementHandler):
    """Handles standard HTML <select> elements."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            logger.warning(f"Could not locate select: {element_info.get('label', '?')}")
            return False

        try:
            # Try to select by label (visible text)
            try:
                await elem.select_option(label=value)
                logger.info(f"Selected '{value}' in '{element_info.get('label', '?')}' (by label)")
                return True
            except Exception:
                pass

            # Try by value
            try:
                await elem.select_option(value=value)
                logger.info(f"Selected '{value}' in '{element_info.get('label', '?')}' (by value)")
                return True
            except Exception:
                pass

            # Try partial match on options
            options = element_info.get('options', [])
            value_lower = value.lower().strip()

            for opt in options:
                opt_text = opt.get('text', '').lower().strip()
                opt_value = opt.get('value', '').lower().strip()

                if value_lower in opt_text or opt_text in value_lower:
                    await elem.select_option(value=opt['value'])
                    logger.info(f"Selected '{opt['text']}' (partial match) in '{element_info.get('label', '?')}'")
                    return True

            logger.warning(f"No matching option for '{value}' in '{element_info.get('label', '?')}'")
            return False

        except Exception as e:
            logger.error(f"Failed to select option: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            selected_text = await elem.evaluate(
                "el => el.options[el.selectedIndex]?.text || ''"
            )
            return expected_value.lower() in selected_text.lower()
        except Exception:
            return False


class CustomDropdownHandler(BaseElementHandler):
    """
    Handles JavaScript-based custom dropdowns (non-native select).
    These require clicking to open, then clicking an option.
    """

    async def _open_dropdown(self, page, elem):
        """Dismiss any open dropdown then click to open this one."""
        try:
            await page.locator('body').click(position={'x': 0, 'y': 0}, timeout=1000)
            await asyncio.sleep(0.2)
        except Exception:
            pass

        try:
            await elem.click(timeout=5000)
        except Exception:
            await elem.click(force=True, timeout=5000)
        await asyncio.sleep(0.5)

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            logger.warning(f"Could not locate custom dropdown: {element_info.get('label', '?')}")
            return False

        label = element_info.get('label', '?')

        try:
            await self._open_dropdown(page, elem)

            # Strategy 1: Look for exact/partial text match in visible options
            option_selectors = [
                f'[role="option"]:has-text("{value}")',
                f'[role="listbox"] >> text="{value}"',
                f'li:has-text("{value}")',
                f'[class*="option"]:has-text("{value}")',
            ]

            for selector in option_selectors:
                try:
                    option = page.locator(selector).first
                    if await option.count() > 0:
                        await option.click(timeout=5000)
                        logger.info(f"Selected '{value}' in custom dropdown '{label}'")
                        await asyncio.sleep(0.3)
                        return True
                except Exception:
                    continue

            # Strategy 2: For combobox — type to filter, then pick first option
            if element_info.get('type') == 'combobox':
                # Selectors for autocomplete suggestion items (covers
                # React Select, Oracle Cloud, and generic listbox patterns)
                suggestion_selectors = [
                    '[role="option"]:visible',
                    'li[role="option"]:visible',
                    '.oj-listbox-result:visible',
                    'oj-option:visible',
                    '[class*="option"]:visible:not([aria-disabled="true"])',
                    '[class*="suggestion"]:visible',
                    '[class*="autocomplete"] li:visible',
                ]

                # Try progressively shorter fragments of the value
                fragments = [value]
                words = value.split()
                # Strip ", Country" suffixes (e.g., "Bangalore, India" → "Bangalore")
                if ',' in value:
                    fragments.insert(0, value.split(',')[0].strip())
                if len(words) > 3:
                    fragments.append(' '.join(words[:3]))
                if len(words) > 1:
                    fragments.append(words[0])
                # Add common affirmative keywords if value seems affirmative
                value_lower = value.lower()
                if any(kw in value_lower for kw in ['yes', 'confirm', 'agree', 'i can']):
                    fragments.extend(['Yes', 'I confirm', 'I agree'])

                for fragment in fragments:
                    try:
                        # Clear and type (use press_sequentially for autocomplete)
                        await elem.fill('', timeout=2000)
                        await asyncio.sleep(0.2)
                        try:
                            await elem.press_sequentially(fragment, delay=50, timeout=3000)
                        except Exception:
                            await elem.fill(fragment, timeout=3000)
                        # Wait longer for AJAX autocomplete suggestions
                        await asyncio.sleep(1.0)

                        # Try each suggestion selector
                        for sel in suggestion_selectors:
                            try:
                                first_option = page.locator(sel).first
                                if await first_option.count() > 0:
                                    option_text = await first_option.inner_text()
                                    await first_option.click(timeout=5000)
                                    logger.info(
                                        f"Typed '{fragment[:20]}' and selected "
                                        f"'{option_text.strip()[:40]}' in combobox '{label}'"
                                    )
                                    return True
                            except Exception:
                                continue

                        # Try keyboard Enter to select highlighted option
                        try:
                            await elem.press('Enter', timeout=1000)
                            await asyncio.sleep(0.3)
                            current_val = await elem.input_value()
                            if current_val and current_val != fragment:
                                logger.info(
                                    f"Enter-selected '{current_val[:40]}' in combobox '{label}'"
                                )
                                return True
                        except Exception:
                            pass
                    except Exception:
                        continue

                # Strategy 3: Last resort — open dropdown and pick first non-placeholder option
                try:
                    await elem.fill('', timeout=2000)
                    await asyncio.sleep(0.3)
                    await self._open_dropdown(page, elem)
                    for sel in suggestion_selectors:
                        all_options = page.locator(sel)
                        count = await all_options.count()
                        if count > 0:
                            for i in range(min(count, 5)):
                                opt = all_options.nth(i)
                                opt_text = (await opt.inner_text()).strip()
                                if opt_text.lower() not in ('select...', 'select', 'choose...', ''):
                                    await opt.click(timeout=5000)
                                    logger.info(
                                        f"Fallback: selected '{opt_text[:40]}' in combobox '{label}'"
                                    )
                                    return True
                except Exception:
                    pass

            logger.warning(f"Could not select '{value}' in custom dropdown '{label}'")
            return False

        except Exception as e:
            logger.error(f"Failed to interact with custom dropdown '{label}': {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            text = await elem.inner_text()
            return expected_value.lower() in text.lower()
        except Exception:
            return False


class DatePickerHandler(BaseElementHandler):
    """Handles date picker widgets - uses keyboard input for reliability."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            # Try direct input first (most reliable)
            await elem.click()
            await asyncio.sleep(0.3)

            # Clear and type date string
            await elem.fill('')
            await elem.type(value, delay=50)
            await asyncio.sleep(0.3)

            # Press Tab to confirm (closes most date pickers)
            await elem.press('Tab')
            await asyncio.sleep(0.3)

            logger.info(f"Filled date '{value}' in '{element_info.get('label', '?')}'")
            return True

        except Exception as e:
            logger.error(f"Failed to fill date: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            actual = await elem.input_value()
            return expected_value in actual
        except Exception:
            return False


class FileUploadHandler(BaseElementHandler):
    """Handles file upload inputs."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        """
        Upload a file.

        Args:
            value: Path to the file to upload
        """
        if not value or value.startswith('__'):
            logger.warning(f"File path not resolved: {value}")
            return False

        file_path = Path(value)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return False

        try:
            attrs = element_info.get('attributes', {})
            selector = attrs.get('selector', 'input[type="file"]')

            # File inputs are often hidden, use set_input_files
            locator = page.locator(selector)
            if await locator.count() == 0:
                locator = page.locator('input[type="file"]').first

            await locator.set_input_files(str(file_path))
            logger.info(f"Uploaded file: {file_path.name}")
            await asyncio.sleep(1)
            return True

        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        # File uploads are hard to verify directly
        return True


class RichTextHandler(BaseElementHandler):
    """Handles contenteditable rich text editors."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            # Try finding by contenteditable attribute
            elem = page.locator('[contenteditable="true"]:visible').first
            if await elem.count() == 0:
                return False

        try:
            await elem.click()
            await asyncio.sleep(0.3)

            # Clear existing content
            await page.keyboard.press('Control+a')
            await asyncio.sleep(0.1)
            await page.keyboard.press('Delete')
            await asyncio.sleep(0.2)

            # Type the content
            await page.keyboard.type(value, delay=20)
            await asyncio.sleep(0.3)

            logger.info(f"Filled rich text editor with {len(value)} chars")
            return True

        except Exception as e:
            logger.error(f"Failed to fill rich text editor: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            text = await elem.inner_text()
            return expected_value[:50] in text
        except Exception:
            return False


class CheckboxHandler(BaseElementHandler):
    """Handles checkboxes (both native and ARIA)."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        """value should be 'check', 'uncheck', 'true', 'false', etc."""
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        should_check = value.lower() in ('check', 'checked', 'true', 'yes', '1')

        try:
            # Native checkbox
            if element_info.get('tag') == 'input':
                is_checked = await elem.is_checked()
                if is_checked != should_check:
                    await elem.click()
                    await asyncio.sleep(0.3)
            else:
                # ARIA checkbox
                current = await elem.get_attribute('aria-checked')
                is_checked = current == 'true'
                if is_checked != should_check:
                    await elem.click()
                    await asyncio.sleep(0.3)

            logger.info(f"{'Checked' if should_check else 'Unchecked'} '{element_info.get('label', '?')}'")
            return True

        except Exception as e:
            logger.error(f"Failed to handle checkbox: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        should_check = expected_value.lower() in ('check', 'checked', 'true', 'yes', '1')

        try:
            if element_info.get('tag') == 'input':
                return await elem.is_checked() == should_check
            else:
                current = await elem.get_attribute('aria-checked')
                return (current == 'true') == should_check
        except Exception:
            return False


class RadioGroupHandler(BaseElementHandler):
    """Handles radio button groups."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        """value is the label or value of the radio option to select."""
        try:
            group_name = element_info.get('attributes', {}).get('group_name', '')

            if group_name:
                # Find the radio with matching value or label
                radios = await page.locator(f'input[type="radio"][name="{group_name}"]').all()
            else:
                radios = await page.locator('input[type="radio"]:visible').all()

            for radio in radios:
                radio_value = await radio.get_attribute('value') or ''
                radio_label = await self._get_element_label(page, radio)

                if (value.lower() in radio_value.lower() or
                    value.lower() in (radio_label or '').lower()):
                    await radio.click()
                    await asyncio.sleep(0.3)
                    logger.info(f"Selected radio option '{value}'")
                    return True

            logger.warning(f"Radio option '{value}' not found")
            return False

        except Exception as e:
            logger.error(f"Failed to select radio: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        try:
            group_name = element_info.get('attributes', {}).get('group_name', '')
            if group_name:
                checked = page.locator(f'input[type="radio"][name="{group_name}"]:checked')
                if await checked.count() > 0:
                    val = await checked.get_attribute('value') or ''
                    return expected_value.lower() in val.lower()
            return False
        except Exception:
            return False


class PhoneInputHandler(BaseElementHandler):
    """Handles phone number inputs with country code selectors."""

    async def fill(self, page, element_info: Dict, value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            # Check if there's a separate country code selector nearby
            parent = await elem.evaluate("el => el.parentElement?.innerHTML || ''")

            # Just fill the phone number directly
            await elem.click()
            await asyncio.sleep(0.3)
            await elem.fill('')
            await elem.type(value, delay=40)
            await asyncio.sleep(0.3)

            logger.info(f"Filled phone: {value}")
            return True

        except Exception as e:
            logger.error(f"Failed to fill phone: {e}")
            return False

    async def verify(self, page, element_info: Dict, expected_value: str) -> bool:
        elem = await self._locate(page, element_info)
        if not elem:
            return False

        try:
            actual = await elem.input_value()
            # Phone numbers might have formatting differences
            return expected_value.replace(' ', '').replace('-', '') in actual.replace(' ', '').replace('-', '')
        except Exception:
            return False


class ElementHandlerRegistry:
    """Registry of element handlers mapped by element type."""

    def __init__(self):
        self._handlers = {
            'text_input': TextInputHandler(),
            'email_input': TextInputHandler(),
            'password_input': TextInputHandler(),
            'number_input': TextInputHandler(),
            'url_input': TextInputHandler(),
            'textarea': TextInputHandler(),
            'phone_input': PhoneInputHandler(),
            'date_input': DatePickerHandler(),
            'select': NativeSelectHandler(),
            'combobox': CustomDropdownHandler(),
            'listbox': CustomDropdownHandler(),
            'file_upload': FileUploadHandler(),
            'rich_text': RichTextHandler(),
            'checkbox': CheckboxHandler(),
            'radio': RadioGroupHandler(),
        }

    def get_handler(self, element_type: str) -> Optional[BaseElementHandler]:
        """Get the appropriate handler for an element type."""
        return self._handlers.get(element_type)

    async def fill_element(
        self,
        page,
        element_info: Dict,
        value: str
    ) -> bool:
        """
        Fill an element using the appropriate handler.

        Args:
            page: Playwright page or locator scope
            element_info: Element dict from DOM snapshot
            value: Value to set

        Returns:
            True if successful
        """
        el_type = element_info.get('type', 'text_input')
        handler = self.get_handler(el_type)

        if not handler:
            logger.warning(f"No handler for element type: {el_type}")
            return False

        return await handler.fill(page, element_info, value)

    async def verify_element(
        self,
        page,
        element_info: Dict,
        expected_value: str
    ) -> bool:
        """Verify an element has the expected value."""
        el_type = element_info.get('type', 'text_input')
        handler = self.get_handler(el_type)

        if not handler:
            return False

        return await handler.verify(page, element_info, expected_value)
