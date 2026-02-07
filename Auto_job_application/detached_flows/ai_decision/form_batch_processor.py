"""
Batch form processor - extracts all questions at once and prepares answers efficiently.

New architecture:
1. Extract entire modal HTML with all questions
2. Match with existing Q&A dataset (exact/fuzzy)
3. For unmatched: Single AI call with all questions → returns JSON
4. Fill form with prepared answer mappings
"""
import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("FormBatchProcessor")


class FormBatchProcessor:
    """Process entire form in batch mode for better accuracy and performance."""

    def __init__(self, question_handler, profile: dict):
        """
        Initialize batch processor.

        Args:
            question_handler: QuestionHandler instance for AI calls
            profile: User profile dict from user_profile.json
        """
        self.question_handler = question_handler
        self.profile = profile

    async def extract_form_questions(self, modal) -> List[Dict]:
        """
        Extract all questions from modal - ONLY TEXT, no element objects.

        Quick extraction to avoid browser timeouts/detection.

        Returns:
            List of question dicts: [
                {
                    "field_id": "input_0",
                    "field_type": "text|number|select",
                    "question": "Years of experience...",
                    "index": 0,  # Position in input list for later relocation
                    "required": bool,
                    "options": [...] # For select fields only
                },
                ...
            ]
        """
        questions = []

        # Get all visible text inputs
        text_inputs = await modal.locator(
            'input[type="text"]:visible, input[type="number"]:visible, input:not([type]):visible, textarea:visible'
        ).all()

        input_index = 0  # Track actual index for relocation

        for idx, input_elem in enumerate(text_inputs):
            try:
                # Skip if already filled
                value = await input_elem.input_value()
                if value and len(value.strip()) > 0:
                    continue

                # Get field metadata (ONLY TEXT, no objects)
                html_type = await input_elem.get_attribute('type') or 'text'
                field_name = await input_elem.get_attribute('name') or ''
                is_required = await input_elem.get_attribute('required') is not None

                # Get label
                label = await self._get_input_label(input_elem)

                # Detect semantic field type (number vs text)
                field_type = await self._detect_field_type(input_elem, label, html_type)

                if label and label != "Unknown field":
                    questions.append({
                        "field_id": f"input_{input_index}",
                        "field_type": field_type,
                        "field_name": field_name,
                        "question": label,
                        "index": idx,  # Original index for relocation
                        "required": is_required,
                        "element_type": "input"
                    })
                    input_index += 1

            except Exception as e:
                logger.debug(f"Error extracting question {idx}: {e}")
                continue

        # Get all visible select/dropdown fields (standard HTML select)
        select_elems = await modal.locator('select:visible').all()
        logger.info(f"Found {len(select_elems)} native select elements")
        select_index = 0

        for idx, select_elem in enumerate(select_elems):
            try:
                # Get selected value and text
                selected_value = await select_elem.input_value()
                selected_text = await select_elem.evaluate("el => el.options[el.selectedIndex]?.text || ''")

                # Skip if already selected with a real value (not placeholder)
                if selected_value and selected_value.strip():
                    # Check if it's a placeholder text
                    placeholder_keywords = ['select an option', 'select', 'choose', 'please select', '--', '...']
                    is_placeholder = any(keyword in selected_text.lower() for keyword in placeholder_keywords)

                    if not is_placeholder:
                        continue  # Skip only if it's a real selected value, not a placeholder

                # Get label
                label = await self._get_select_label(select_elem)
                is_required = await select_elem.get_attribute('required') is not None

                # Extract all options
                options = await self._extract_select_options(select_elem)

                if label and label != "Unknown field" and options:
                    questions.append({
                        "field_id": f"select_{select_index}",
                        "field_type": "select",
                        "question": label,
                        "index": idx,  # Original index for relocation
                        "required": is_required,
                        "options": options,
                        "element_type": "select",
                        "selector_type": "native"
                    })
                    select_index += 1

            except Exception as e:
                logger.debug(f"Error extracting select {idx}: {e}")
                continue

        # Get custom LinkedIn dropdowns (non-standard select elements)
        # Simple approach: find dropdown elements directly, filter by text to exclude action buttons
        try:
            # Find all potential dropdown elements
            all_dropdown_candidates = await modal.locator(
                '[role="combobox"], [aria-haspopup="listbox"], button:has-text("Select an option")'
            ).all()

            custom_dropdown_elems = []
            for elem in all_dropdown_candidates:
                try:
                    # Get element text and position
                    elem_text = await elem.inner_text()
                    elem_text_lower = elem_text.lower() if elem_text else ""

                    # Filter out action buttons by text
                    action_keywords = ['save', 'cancel', 'submit', 'close', 'done', 'send']
                    if any(action in elem_text_lower for action in action_keywords):
                        logger.debug(f"Skipping action button: {elem_text}")
                        continue

                    # Filter out navigation buttons
                    nav_keywords = ['back', 'next', 'continue', 'review', 'previous']
                    if any(nav in elem_text_lower for nav in nav_keywords):
                        logger.debug(f"Skipping navigation button: {elem_text}")
                        continue

                    # Only include if it looks like a form field (has placeholder or is unselected)
                    if "select" in elem_text_lower or len(elem_text.strip()) == 0:
                        custom_dropdown_elems.append(elem)
                    # OR if it's a dropdown that's already selected (like country codes)
                    elif await elem.get_attribute('aria-haspopup') or await elem.get_attribute('role') == 'combobox':
                        # Check if it's in the upper half of modal (form fields) vs bottom (action buttons)
                        try:
                            box = await elem.bounding_box()
                            if box and box['y'] < 400:  # Upper portion of modal
                                custom_dropdown_elems.append(elem)
                        except Exception:
                            pass

                except Exception as e:
                    logger.debug(f"Error checking dropdown candidate: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Error finding custom dropdowns: {e}")
            custom_dropdown_elems = []

        logger.info(f"Found {len(custom_dropdown_elems)} potential custom dropdown elements")
        custom_index = 0

        for idx, dropdown_elem in enumerate(custom_dropdown_elems):
            try:
                # Get current value/text
                current_text = await dropdown_elem.inner_text()

                # Skip if already selected (not "Select an option")
                if current_text and current_text.strip() and not any(placeholder in current_text.lower() for placeholder in ['select an option', 'select', 'choose']):
                    continue

                # Get label
                label = await self._get_custom_dropdown_label(dropdown_elem)
                is_required = await dropdown_elem.get_attribute('required') is not None

                # Click to reveal options
                await dropdown_elem.click()
                await modal.page.wait_for_timeout(500)  # Wait for dropdown menu to appear

                # Extract options from revealed menu
                options = await self._extract_custom_dropdown_options(modal)

                # Close dropdown by clicking elsewhere or pressing Escape
                await modal.page.keyboard.press('Escape')
                await modal.page.wait_for_timeout(300)

                if label and label != "Unknown field" and options:
                    questions.append({
                        "field_id": f"custom_dropdown_{custom_index}",
                        "field_type": "select",
                        "question": label,
                        "index": idx,  # Original index for relocation
                        "required": is_required,
                        "options": options,
                        "element_type": "custom_dropdown",
                        "selector_type": "custom"
                    })
                    custom_index += 1
                    logger.info(f"✓ Detected custom dropdown: {label[:50]}... with {len(options)} options")

            except Exception as e:
                logger.debug(f"Error extracting custom dropdown {idx}: {e}")
                continue

        return questions

    async def _detect_field_type(self, input_elem, label: str, html_type: str) -> str:
        """
        Detect semantic field type (number vs text) using multiple signals.

        LinkedIn uses <input type="text"> with validation patterns, so we need
        to check attributes and label text to identify numeric fields.
        """
        try:
            # Check if HTML type is explicitly number
            if html_type == 'number':
                return 'number'

            # Check input attributes for numeric indicators
            inputmode = await input_elem.get_attribute('inputmode')
            if inputmode in ['numeric', 'decimal']:
                return 'number'

            pattern = await input_elem.get_attribute('pattern')
            if pattern and any(indicator in pattern for indicator in ['[0-9]', '\\d', '[0-9]+']):
                return 'number'

            # Check label text for numeric keywords
            label_lower = label.lower()
            numeric_keywords = [
                'years', 'year', 'experience', 'ctc', 'salary', 'lacs', 'lpa',
                'lakhs', 'notice period', 'days', 'months', 'age', 'percentage',
                'how many', 'number of', 'total', 'compensation'
            ]

            if any(keyword in label_lower for keyword in numeric_keywords):
                return 'number'

            # Default to text
            return 'text'

        except Exception as e:
            logger.debug(f"Error detecting field type: {e}")
            return 'text'

    async def _get_input_label(self, input_elem) -> str:
        """Extract label for input field (same logic as original bot)."""
        try:
            # Try aria-label first
            aria_label = await input_elem.get_attribute('aria-label')
            if aria_label and aria_label.strip():
                return aria_label.strip()

            # Try placeholder
            placeholder = await input_elem.get_attribute('placeholder')
            if placeholder and placeholder.strip():
                return placeholder.strip()

            # Try associated label element
            input_id = await input_elem.get_attribute('id')
            if input_id:
                page = input_elem.page
                label_elem = page.locator(f'label[for="{input_id}"]').first
                if await label_elem.is_visible(timeout=500):
                    label_text = await label_elem.inner_text()
                    if label_text and label_text.strip():
                        return label_text.strip()

            return "Unknown field"

        except Exception:
            return "Unknown field"

    async def _get_select_label(self, select_elem) -> str:
        """Extract label for select/dropdown field."""
        try:
            # Try aria-label first
            aria_label = await select_elem.get_attribute('aria-label')
            if aria_label and aria_label.strip():
                return aria_label.strip()

            # Try associated label element
            select_id = await select_elem.get_attribute('id')
            if select_id:
                page = select_elem.page
                label_elem = page.locator(f'label[for="{select_id}"]').first
                if await label_elem.is_visible(timeout=500):
                    label_text = await label_elem.inner_text()
                    if label_text and label_text.strip():
                        return label_text.strip()

            # Try finding label in parent
            parent = select_elem.locator('xpath=ancestor::div[contains(@class, "form") or contains(@class, "field")]').first
            label_elem = parent.locator('label').first
            if await label_elem.is_visible(timeout=500):
                label_text = await label_elem.inner_text()
                if label_text and label_text.strip():
                    return label_text.strip()

            return "Unknown field"

        except Exception:
            return "Unknown field"

    async def _extract_select_options(self, select_elem) -> List[str]:
        """Extract all option values from a select element."""
        try:
            option_elems = await select_elem.locator('option').all()
            options = []

            for opt in option_elems:
                text = await opt.inner_text()
                value = await opt.get_attribute('value')

                # Skip placeholder options (empty or "Select...")
                if not value or not text or text.strip().lower() in ['select', 'choose', 'select one', '']:
                    continue

                # Use text for display, value for selection
                options.append(text.strip())

            return options

        except Exception as e:
            logger.debug(f"Error extracting select options: {e}")
            return []

    async def _get_custom_dropdown_label(self, dropdown_elem) -> str:
        """Extract label for custom dropdown field."""
        try:
            # Try aria-label first
            aria_label = await dropdown_elem.get_attribute('aria-label')
            if aria_label and aria_label.strip():
                return aria_label.strip()

            # Try looking for label in parent or preceding sibling
            parent = dropdown_elem.locator('xpath=ancestor::div[contains(@class, "form") or contains(@class, "field")]').first
            label_elem = parent.locator('label').first

            if await label_elem.is_visible(timeout=500):
                label_text = await label_elem.inner_text()
                if label_text and label_text.strip():
                    return label_text.strip()

            # Try finding text before the dropdown
            page = dropdown_elem.page
            dropdown_id = await dropdown_elem.get_attribute('id')
            if dropdown_id:
                label_elem = page.locator(f'label[for="{dropdown_id}"]').first
                if await label_elem.is_visible(timeout=500):
                    label_text = await label_elem.inner_text()
                    if label_text and label_text.strip():
                        return label_text.strip()

            return "Unknown field"

        except Exception:
            return "Unknown field"

    async def _extract_custom_dropdown_options(self, modal) -> List[str]:
        """Extract options from a custom dropdown menu (LinkedIn style)."""
        try:
            # Wait for dropdown menu to appear
            await modal.page.wait_for_timeout(300)

            # Look for visible list items, options, or menu items
            # LinkedIn uses various patterns: ul > li, [role="option"], etc.
            option_selectors = [
                '[role="option"]:visible',
                '[role="menuitem"]:visible',
                'ul:visible > li',
                '[class*="dropdown"]:visible [class*="option"]',
                '[class*="menu"]:visible [class*="item"]'
            ]

            options = []
            for selector in option_selectors:
                option_elems = await modal.locator(selector).all()

                if option_elems and len(option_elems) > 0:
                    for opt in option_elems:
                        if await opt.is_visible():
                            text = await opt.inner_text()
                            if text and text.strip() and text.strip() not in ['Select an option', 'Choose', 'Select']:
                                options.append(text.strip())

                    if options:
                        # Found options with this selector
                        break

            # Remove duplicates while preserving order
            seen = set()
            unique_options = []
            for opt in options:
                if opt not in seen:
                    seen.add(opt)
                    unique_options.append(opt)

            return unique_options

        except Exception as e:
            logger.debug(f"Error extracting custom dropdown options: {e}")
            return []

    async def _click_custom_dropdown_option(self, modal, option_text: str) -> bool:
        """Click an option in a custom dropdown menu."""
        try:
            # Wait for dropdown menu to appear
            await modal.page.wait_for_timeout(300)

            # Try different selectors for dropdown options
            option_selectors = [
                f'[role="option"]:has-text("{option_text}")',
                f'[role="menuitem"]:has-text("{option_text}")',
                f'ul:visible > li:has-text("{option_text}")',
                f'[class*="option"]:has-text("{option_text}")'
            ]

            for selector in option_selectors:
                try:
                    option_elem = modal.locator(selector).first
                    if await option_elem.is_visible(timeout=1000):
                        await option_elem.click()
                        await modal.page.wait_for_timeout(300)
                        return True
                except Exception:
                    continue

            # Fallback: try finding by exact text match
            all_options = await modal.locator('[role="option"]:visible, [role="menuitem"]:visible, ul:visible > li').all()
            for opt in all_options:
                text = await opt.inner_text()
                if text and text.strip() == option_text:
                    await opt.click()
                    await modal.page.wait_for_timeout(300)
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error clicking custom dropdown option '{option_text}': {e}")
            return False

    def prepare_answers_batch(
        self,
        questions: List[Dict],
        job_context: dict
    ) -> Dict[str, str]:
        """
        Prepare answers for all questions in batch.

        Strategy:
        1. Check existing Q&A dataset for exact/similar matches
        2. For unmatched: Single AI call with all questions → JSON response
        3. Return field_id → answer mapping

        Args:
            questions: List of question dicts from extract_form_questions
            job_context: Job context (title, company, etc.)

        Returns:
            Dict mapping field_id to answer: {"input_0": "10 years", ...}
        """
        answers = {}

        # ALWAYS generate fresh AI answers with profile context
        # Database caching disabled to ensure accurate, profile-based responses
        logger.info(f"Generating AI answers for {len(questions)} questions...")
        ai_answers = self._generate_ai_answers_batch(questions, job_context)
        answers.update(ai_answers)

        return answers

    def _find_existing_answer(self, question: str, field_type: str) -> Optional[str]:
        """
        Check if we have an existing answer for this question.

        Uses fuzzy matching on question text and field type.
        """
        # Get similar questions from database
        similar_qa = self.question_handler._get_similar_qa(question, "", limit=1)

        if similar_qa and len(similar_qa) > 0:
            qa = similar_qa[0]
            # Only use if field types match (type-aware)
            if qa.get('field_type') == field_type:
                return qa['answer']

        return None

    def _generate_ai_answers_batch(
        self,
        questions: List[Dict],
        job_context: dict
    ) -> Dict[str, str]:
        """
        Generate answers for multiple questions in a single AI call.

        Returns JSON: {"input_0": "answer1", "input_1": "answer2", ...}
        """
        # Build profile summary
        profile_summary = self.question_handler._build_profile_summary()

        # Build questions list for AI
        questions_text = ""
        for q in questions:
            # Defensive: use .get() to avoid KeyError
            field_id = q.get('field_id', 'unknown')
            field_type = q.get('field_type', 'text')
            question_text = q.get('question', 'Unknown field')

            questions_text += f"- **{field_id}** (type: {field_type}): {question_text}\n"
            # Include options for select fields
            if field_type == 'select' and 'options' in q:
                questions_text += f"  Options: {', '.join(q['options'])}\n"

        # Get existing Q&A for context
        try:
            all_existing_qa = self.question_handler.get_stored_responses(limit=20)
        except Exception as e:
            logger.warning(f"Could not get stored responses: {e}")
            all_existing_qa = []

        existing_context = ""
        if all_existing_qa:
            existing_context = "\n**Existing Answers for Reference:**\n"
            for qa in all_existing_qa[:10]:  # Top 10
                # Defensive: use .get() to avoid KeyError
                q_text = qa.get('question_text', 'Unknown')
                a_text = qa.get('response', 'N/A')
                existing_context += f"- Q: {q_text}\n  A: {a_text}\n"
            existing_context += "\nUse these as examples to maintain consistency.\n"

        prompt = f"""You are filling out a job application form. Provide answers for ALL questions below.

**Candidate Profile:**
{profile_summary}

**Job Context:**
- Title: {job_context.get('job_title', 'Unknown')}
- Company: {job_context.get('company', 'Unknown')}
- Location: {job_context.get('location', 'Unknown')}

{existing_context}

**Questions to Answer:**
{questions_text}

**CRITICAL INSTRUCTIONS:**
1. Return ONLY a valid JSON object mapping field_id to answer
2. Each answer must be:
   - Clean text only (no markdown, no formatting)
   - Concise and direct
   - Professional and truthful based on profile
   - For experience: be realistic about technology maturity (LangChain ~2 years old, AWS 10+ years, etc.)
3. For number fields: return only numeric value (e.g., "10" not "10 years")
4. For text fields: return text (e.g., "10 years" or "10+ years")
5. For select fields: return EXACTLY one of the provided options (exact match required)
6. Maintain consistency across related questions
7. Use existing Q&A examples as reference for style

**Response Format (valid JSON only):**
{{
    "input_0": "answer text here",
    "input_1": "answer text here",
    ...
}}

Return ONLY the JSON object, nothing else:"""

        try:
            # Call AI
            from detached_flows.ai_decision.claude_fast import call_claude_fast
            response = call_claude_fast(prompt, max_tokens=2048, timeout=30)

            # Parse JSON
            # Handle case where AI wraps JSON in ```json``` code blocks
            response = response.strip()
            if response.startswith("```"):
                # Extract JSON from code block
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1])  # Remove first and last line

            answers_json = json.loads(response)

            # Store answers in database for future reuse
            for q in questions:
                field_id = q['field_id']
                if field_id in answers_json:
                    answer = answers_json[field_id]
                    self.question_handler._store_response(
                        q['question'],
                        answer,
                        "",  # question_type (empty for batch)
                        job_context.get('external_id'),
                        q['field_type']
                    )
                    logger.info(f"✓ AI answer: {q['question'][:50]}... → {answer}")

            return answers_json

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI JSON response: {e}")
            logger.error(f"Response was: {response[:500]}")
            # Fallback: return empty dict
            return {}
        except Exception as e:
            logger.error(f"AI batch answer generation failed: {e}")
            return {}

    def _clean_answer_for_field_type(self, answer: str, field_type: str) -> str:
        """
        Clean answer based on field type.

        - number: Extract only digits (e.g., "5 years" → "5")
        - text: Keep as is
        """
        if field_type == "number":
            # Extract only numbers (handle cases like "5 years", "5+", "10-12")
            import re
            numbers = re.findall(r'\d+', answer)
            if numbers:
                return numbers[0]  # Return first number found
            return answer  # Fallback if no numbers found

        # For text fields, return as is
        return answer

    async def fill_form_with_answers(
        self,
        modal,
        questions: List[Dict],
        answers: Dict[str, str]
    ) -> bool:
        """
        Fill form fields with prepared answers.

        Includes fallback AI post-processing for validation errors.

        Args:
            modal: Modal element to scope searches
            questions: List of question dicts (text only, no elements)
            answers: Dict mapping field_id to answer

        Returns:
            True if all required fields filled successfully
        """
        success_count = 0
        failed_fields = []

        # Get all visible inputs again (fresh locators)
        text_inputs = await modal.locator(
            'input[type="text"]:visible, input[type="number"]:visible, input:not([type]):visible, textarea:visible'
        ).all()

        # Get all visible select elements
        select_elems = await modal.locator('select:visible').all()

        # Get all custom dropdown elements
        custom_dropdown_elems = await modal.locator('[role="combobox"]:visible, [role="listbox"]:visible, button:has-text("Select an option")').all()

        # First pass: fill all fields
        for q in questions:
            field_id = q['field_id']
            answer = answers.get(field_id)

            if not answer or answer == "N/A":
                if q['required']:
                    logger.warning(f"Missing answer for required field: {q['question'][:50]}...")
                    failed_fields.append({'question': q, 'reason': 'Missing answer'})
                continue

            try:
                # Determine which element list to use
                if q.get('element_type') == 'custom_dropdown':
                    # Handle custom LinkedIn dropdowns
                    dropdown_index = q['index']
                    if dropdown_index >= len(custom_dropdown_elems):
                        logger.error(f"Custom dropdown index {dropdown_index} out of range (only {len(custom_dropdown_elems)} dropdowns)")
                        failed_fields.append({'question': q, 'reason': 'Element not found'})
                        continue

                    dropdown_elem = custom_dropdown_elems[dropdown_index]

                    # Click to open dropdown
                    await dropdown_elem.click()
                    await modal.page.wait_for_timeout(500)

                    # Find and click the option
                    option_clicked = await self._click_custom_dropdown_option(modal, answer)

                    if option_clicked:
                        logger.info(f"✓ Selected {q['question'][:40]}... → {answer} (type: custom_dropdown)")
                        success_count += 1
                    else:
                        logger.warning(f"Failed to select option '{answer}' for {q['question'][:40]}...")
                        failed_fields.append({
                            'question': q,
                            'original_answer': answer,
                            'cleaned_answer': answer,
                            'reason': f'Option "{answer}" not found in dropdown'
                        })
                        # Close dropdown
                        await modal.page.keyboard.press('Escape')

                elif q.get('element_type') == 'select':
                    # Handle dropdown/select fields
                    select_index = q['index']
                    if select_index >= len(select_elems):
                        logger.error(f"Select index {select_index} out of range (only {len(select_elems)} selects)")
                        failed_fields.append({'question': q, 'reason': 'Element not found'})
                        continue

                    select_elem = select_elems[select_index]

                    # Select the option by label (exact match)
                    await select_elem.select_option(label=answer)
                    logger.info(f"✓ Selected {q['question'][:40]}... → {answer} (type: select)")

                    # Check for validation errors
                    await modal.page.wait_for_timeout(300)
                    is_invalid = await select_elem.get_attribute('aria-invalid')

                    if is_invalid == 'true':
                        logger.warning(f"Validation failed for {q['question'][:40]}...")
                        failed_fields.append({
                            'question': q,
                            'original_answer': answer,
                            'cleaned_answer': answer,
                            'reason': 'Invalid selection'
                        })
                    else:
                        success_count += 1

                else:
                    # Handle text/number input fields
                    input_index = q['index']
                    if input_index >= len(text_inputs):
                        logger.error(f"Index {input_index} out of range (only {len(text_inputs)} inputs)")
                        failed_fields.append({'question': q, 'reason': 'Element not found'})
                        continue

                    input_elem = text_inputs[input_index]

                    # Clean answer based on field type
                    cleaned_answer = self._clean_answer_for_field_type(answer, q['field_type'])

                    # Fill the field
                    await input_elem.fill('')  # Clear first
                    await input_elem.fill(cleaned_answer)
                    logger.info(f"✓ Filled {q['question'][:40]}... → {cleaned_answer} (type: {q['field_type']})")

                    # Check for validation errors
                    await modal.page.wait_for_timeout(300)  # Brief wait for validation
                    is_invalid = await input_elem.get_attribute('aria-invalid')

                    # Look for error messages near this field
                    error_message = await self._get_field_error(input_elem)

                    if is_invalid == 'true' or error_message:
                        logger.warning(f"Validation failed for {q['question'][:40]}...")
                        if error_message:
                            logger.warning(f"  Error: {error_message}")
                        failed_fields.append({
                            'question': q,
                            'original_answer': answer,
                            'cleaned_answer': cleaned_answer,
                            'reason': error_message or 'Invalid format'
                        })
                    else:
                        success_count += 1

            except Exception as e:
                logger.error(f"Failed to fill {field_id} ({q['question'][:30]}...): {e}")
                failed_fields.append({'question': q, 'reason': str(e)})

        # Fallback: AI post-processing for failed fields
        if failed_fields and len(failed_fields) <= 5:  # Only if not too many failures
            logger.info(f"Attempting AI post-processing for {len(failed_fields)} failed fields...")
            fixed_answers = await self._ai_postprocess_failed_fields(failed_fields)

            if fixed_answers:
                # Retry filling failed fields
                retry_success = await self._retry_fill_fields(modal, text_inputs, select_elems, custom_dropdown_elems, failed_fields, fixed_answers)
                success_count += retry_success

        logger.info(f"Filled {success_count} fields successfully, {len(failed_fields)} failed")
        return len(failed_fields) == 0

    async def _get_field_error(self, input_elem) -> Optional[str]:
        """Extract validation error message for a field."""
        try:
            # Check for error message in parent container
            parent = input_elem.locator('xpath=ancestor::div[contains(@class, "form") or contains(@class, "field")]').first
            error_elem = parent.locator('[class*="error"], [role="alert"]').first

            if await error_elem.is_visible(timeout=500):
                error_text = await error_elem.inner_text()
                if error_text and error_text.strip():
                    return error_text.strip()
        except Exception:
            pass
        return None

    async def _ai_postprocess_failed_fields(
        self,
        failed_fields: List[Dict]
    ) -> Dict[str, str]:
        """
        Use AI to fix failed fields based on validation feedback.

        Args:
            failed_fields: List of dicts with 'question', 'original_answer', 'cleaned_answer', 'reason'

        Returns:
            Dict mapping field_id to corrected answer
        """
        try:
            # Build prompt with failed field details
            failed_details = ""
            for f in failed_fields:
                q = f['question']
                failed_details += f"- **{q['field_id']}**: {q['question']}\n"
                failed_details += f"  Original answer: {f.get('original_answer', 'N/A')}\n"
                failed_details += f"  Cleaned answer: {f.get('cleaned_answer', 'N/A')}\n"
                failed_details += f"  Field type detected: {q['field_type']}\n"
                failed_details += f"  Validation error: {f['reason']}\n\n"

            prompt = f"""Some form fields failed validation. Fix the answers based on validator feedback.

**Failed Fields:**
{failed_details}

**Instructions:**
1. Return ONLY a JSON object mapping field_id to corrected answer
2. For number fields: return ONLY digits (e.g., "5", "10", "30")
3. For text fields: use full text but ensure it matches expected format
4. Consider the validation error message to understand the expected format
5. Be concise and remove unnecessary text

**Response Format (JSON only):**
{{
    "input_0": "corrected answer",
    "input_1": "corrected answer",
    ...
}}

Return ONLY the JSON object:"""

            from detached_flows.ai_decision.claude_fast import call_claude_fast
            response = call_claude_fast(prompt, max_tokens=1024, timeout=15)

            # Parse JSON
            response = response.strip()
            if response.startswith("```"):
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1])

            fixed_answers = json.loads(response)
            logger.info(f"AI post-processing generated {len(fixed_answers)} corrected answers")
            return fixed_answers

        except Exception as e:
            logger.error(f"AI post-processing failed: {e}")
            return {}

    async def _retry_fill_fields(
        self,
        modal,
        text_inputs: List,
        select_elems: List,
        custom_dropdown_elems: List,
        failed_fields: List[Dict],
        fixed_answers: Dict[str, str]
    ) -> int:
        """
        Retry filling fields with AI-corrected answers.

        Returns:
            Number of successfully filled fields
        """
        success_count = 0

        for f in failed_fields:
            q = f['question']
            field_id = q['field_id']
            corrected_answer = fixed_answers.get(field_id)

            if not corrected_answer:
                continue

            try:
                if q.get('element_type') == 'custom_dropdown':
                    # Retry custom dropdown
                    dropdown_index = q['index']
                    if dropdown_index >= len(custom_dropdown_elems):
                        continue

                    dropdown_elem = custom_dropdown_elems[dropdown_index]

                    # Click to open dropdown
                    await dropdown_elem.click()
                    await modal.page.wait_for_timeout(500)

                    # Find and click the option
                    option_clicked = await self._click_custom_dropdown_option(modal, corrected_answer)

                    if option_clicked:
                        success_count += 1
                        logger.info(f"✓ Retry success: {q['question'][:40]}... → {corrected_answer}")
                    else:
                        logger.warning(f"Retry still invalid: {q['question'][:40]}...")
                        await modal.page.keyboard.press('Escape')

                elif q.get('element_type') == 'select':
                    # Retry select field
                    select_index = q['index']
                    if select_index >= len(select_elems):
                        continue

                    select_elem = select_elems[select_index]

                    # Select with corrected answer
                    await select_elem.select_option(label=corrected_answer)

                    # Check validation again
                    await modal.page.wait_for_timeout(300)
                    is_invalid = await select_elem.get_attribute('aria-invalid')

                    if is_invalid != 'true':
                        success_count += 1
                        logger.info(f"✓ Retry success: {q['question'][:40]}... → {corrected_answer}")
                    else:
                        logger.warning(f"Retry still invalid: {q['question'][:40]}...")

                else:
                    # Retry input field
                    input_index = q['index']
                    if input_index >= len(text_inputs):
                        continue

                    input_elem = text_inputs[input_index]

                    # Fill with corrected answer
                    await input_elem.fill('')
                    await input_elem.fill(corrected_answer)

                    # Check validation again
                    await modal.page.wait_for_timeout(300)
                    is_invalid = await input_elem.get_attribute('aria-invalid')

                    if is_invalid != 'true':
                        success_count += 1
                        logger.info(f"✓ Retry success: {q['question'][:40]}... → {corrected_answer}")
                    else:
                        logger.warning(f"Retry still invalid: {q['question'][:40]}...")

            except Exception as e:
                logger.error(f"Retry fill failed for {field_id}: {e}")

        return success_count
