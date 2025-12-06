"""
LLM output parser for aare.ai
Extracts structured data from unstructured LLM text
"""
import logging
import operator
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union, Pattern, Callable, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Context window sizes for text analysis
NEGATION_CONTEXT_WINDOW = 30  # Characters around keyword to check for negation
KEYWORD_SEARCH_CONTEXT = 100  # Characters after keyword to search for values

# Confidence scores for different extraction methods
class ConfidenceScores:
    """Confidence scores for different extraction methods"""
    PATTERN_MATCH = 0.95
    ENUM_EXACT = 0.90
    ENUM_FUZZY = 0.70
    KEYWORD_MULTIPLE = 0.95  # 3+ keywords match
    KEYWORD_DOUBLE = 0.85    # 2 keywords match
    KEYWORD_SINGLE = 0.75    # 1 keyword match
    BOOLEAN_FALSE = 0.60     # Boolean false default
    BOOLEAN_TRUE_NO_MATCH = 0.50
    LIST_MANY = 0.90         # 3+ items
    LIST_SOME = 0.80         # 1-2 items
    LIST_EMPTY = 0.50
    DATE_ISO = 0.90          # ISO format date
    DATE_OTHER = 0.75
    NUMERIC = 0.90
    DEFAULT = 0.70
    COMPUTED = 1.0           # Computed fields have 100% confidence

# Cache for compiled regex patterns
_compiled_patterns: Dict[str, re.Pattern] = {}

# Common date patterns for extraction
DATE_PATTERNS = [
    # ISO format: 2024-12-25, 2024/12/25
    (r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', '%Y-%m-%d'),
    # US format: 12/25/2024, 12-25-2024
    (r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', '%m-%d-%Y'),
    # US format short year: 12/25/24
    (r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{2})\b', '%m-%d-%y'),
    # Written: December 25, 2024 or Dec 25, 2024
    (r'\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})\b', None),
    # Written: 25 December 2024 or 25 Dec 2024
    (r'\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b', None),
]

# Common datetime patterns (date + time)
DATETIME_PATTERNS = [
    # ISO format with time: 2024-12-25T14:30:00, 2024-12-25 14:30:00
    (r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}[T\s]\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm))?)\b', None),
    # US format with time: 12/25/2024 2:30 PM
    (r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)\b', None),
]


@dataclass
class ExtractionResult:
    """Result of an extraction with confidence score"""
    value: Any
    confidence: float  # 0.0 to 1.0
    source: str  # The matched text
    extractor_type: str

class LLMParser:
    def parse(self, text: str, ontology: Dict, include_confidence: bool = False) -> Dict[str, Any]:
        """
        Parse LLM output using ontology-defined extractors.

        Args:
            text: The LLM output text to parse
            ontology: The ontology containing extractor definitions
            include_confidence: If True, return ExtractionResult objects with confidence scores

        Returns:
            Dictionary of extracted values. If include_confidence is True, values are
            ExtractionResult objects; otherwise they are raw values.
        """
        extracted = {}
        confidence_scores = {}
        text_lower = text.lower()
        extractors = ontology.get('extractors', {})

        # First pass: extract all non-computed fields
        computed_extractors = {}
        for field_name, extractor in extractors.items():
            if extractor.get('type') == 'computed' or extractor.get('computed'):
                computed_extractors[field_name] = extractor
                continue

            result = self._extract_field_with_confidence(text, text_lower, extractor)
            if result is not None:
                if include_confidence:
                    extracted[field_name] = result
                else:
                    extracted[field_name] = result.value
                confidence_scores[field_name] = result.confidence

        # Calculate generic derived fields
        extracted = self._calculate_derived_fields(extracted, text_lower, include_confidence)

        # Second pass: calculate ontology-defined computed fields
        extracted = self._calculate_computed_fields(
            extracted, text_lower, computed_extractors, include_confidence
        )

        # Add metadata if requested
        if include_confidence:
            extracted['_confidence_scores'] = confidence_scores

        return extracted

    def _extract_field_with_confidence(self, text: str, text_lower: str, extractor: Dict) -> Optional[ExtractionResult]:
        """Extract a field and return result with confidence score"""
        extractor_type = extractor.get('type')
        value = self._extract_field(text, text_lower, extractor)

        if value is None:
            return None

        # Calculate confidence based on extraction method and match quality
        confidence = self._calculate_confidence(text, text_lower, extractor, value)

        # Determine source text (the matched portion)
        source = self._find_source_text(text, text_lower, extractor, value)

        return ExtractionResult(
            value=value,
            confidence=confidence,
            source=source,
            extractor_type=extractor_type
        )

    def _calculate_confidence(self, text: str, text_lower: str, extractor: Dict, value: Any) -> float:
        """
        Calculate confidence score for an extraction.

        Factors affecting confidence:
        - Exact pattern match: high confidence
        - Keyword match: medium-high confidence
        - Multiple keywords match: higher confidence
        - Fuzzy/partial match: lower confidence
        - Default value used: low confidence
        """
        extractor_type = extractor.get('type')

        # Pattern-based extractors (high confidence)
        if extractor.get('pattern'):
            return ConfidenceScores.PATTERN_MATCH

        # Enum with exact match
        if extractor_type == 'enum':
            choices = extractor.get('choices', {})
            if value in choices:
                return ConfidenceScores.ENUM_EXACT
            return ConfidenceScores.ENUM_FUZZY

        # Boolean keyword extraction
        if extractor_type == 'boolean':
            keywords = extractor.get('keywords', [])
            # Count how many keywords matched (pre-lowercase for efficiency)
            keywords_lower = [kw.lower() for kw in keywords]
            matches = sum(1 for kw in keywords_lower if kw in text_lower)
            if matches >= 3:
                return ConfidenceScores.KEYWORD_MULTIPLE
            elif matches >= 2:
                return ConfidenceScores.KEYWORD_DOUBLE
            elif matches == 1:
                return ConfidenceScores.KEYWORD_SINGLE
            return ConfidenceScores.BOOLEAN_TRUE_NO_MATCH if value else ConfidenceScores.BOOLEAN_FALSE

        # List extraction
        if extractor_type == 'list' and isinstance(value, list):
            if len(value) >= 3:
                return ConfidenceScores.LIST_MANY
            elif len(value) >= 1:
                return ConfidenceScores.LIST_SOME
            return ConfidenceScores.LIST_EMPTY

        # Date/datetime extraction
        if extractor_type in {'date', 'datetime'}:
            # ISO format dates have higher confidence
            if isinstance(value, str) and re.match(r'\d{4}-\d{2}-\d{2}', value):
                return ConfidenceScores.DATE_ISO
            return ConfidenceScores.DATE_OTHER

        # Numeric types
        if extractor_type in {'int', 'float', 'money', 'percentage'}:
            return ConfidenceScores.NUMERIC

        # Default
        return ConfidenceScores.DEFAULT

    def _find_source_text(self, text: str, text_lower: str, extractor: Dict, value: Any) -> str:
        """Find the source text that was matched"""
        pattern = extractor.get('pattern')
        if pattern:
            compiled = self._get_compiled_pattern(pattern)
            if compiled:
                match = compiled.search(text)
                if match:
                    return match.group(0)

        # For keywords, find the first matching keyword
        keywords = extractor.get('keywords', [])
        for kw in keywords:
            if kw.lower() in text_lower:
                return kw

        # For enum choices
        if extractor.get('type') == 'enum':
            choices = extractor.get('choices', {})
            for choice_value, kws in choices.items():
                if choice_value == value:
                    if isinstance(kws, str):
                        kws = [kws]
                    for kw in kws:
                        if kw.lower() in text_lower:
                            return kw

        return str(value)

    def _extract_field(
        self, text: str, text_lower: str, extractor: Dict[str, Any]
    ) -> Optional[Any]:
        """Extract a single field based on extractor configuration"""
        extractor_type = extractor.get('type')

        if extractor_type == 'boolean':
            negation_words = extractor.get('negation_words', [])
            check_negation = extractor.get('check_negation', True)

            # Check for pattern match (regex-based boolean detection)
            pattern = extractor.get('pattern')
            if pattern:
                compiled = self._get_compiled_pattern(pattern)
                if compiled:
                    match = compiled.search(text)
                    if match:
                        # Check if any negation words are in context
                        if check_negation and negation_words:
                            if self._has_negation_in_context(
                                text_lower, match.start(), match.end(), negation_words
                            ):
                                return False
                        return True
                    return False

            # Check for keyword presence
            keywords = extractor.get('keywords', [])

            # Check if any keyword is present without negation
            for kw in keywords:
                if kw in text_lower:
                    # Only check negation for recommendation-type keywords
                    if check_negation and negation_words:
                        kw_pos = text_lower.find(kw)
                        if self._has_negation_in_context(
                            text_lower, kw_pos, kw_pos + len(kw), negation_words
                        ):
                            continue  # Try next keyword instead of returning False

                    # Found a keyword without negation
                    return True

            return False

        elif extractor_type in ['int', 'float', 'money', 'percentage']:
            # Use regex pattern
            pattern = extractor.get('pattern')
            if not pattern:
                return None

            compiled = self._get_compiled_pattern(pattern)
            if compiled is None:
                return None

            match = compiled.search(text_lower)
            if match and match.groups():
                return self._parse_numeric(match, text, extractor_type)

        elif extractor_type == 'string':
            # Extract string value
            pattern = extractor.get('pattern')
            if pattern:
                compiled = self._get_compiled_pattern(pattern)
                if compiled is None:
                    return None

                match = compiled.search(text_lower)
                if match:
                    return match.group(1) if match.groups() else match.group(0)

        elif extractor_type == 'date':
            # Extract date value
            return self._extract_date(text, extractor)

        elif extractor_type == 'datetime':
            # Extract datetime value
            return self._extract_datetime(text, extractor)

        elif extractor_type == 'list':
            # Extract multiple values into a list
            return self._extract_list(text, text_lower, extractor)

        elif extractor_type == 'enum':
            # Extract from predefined choices
            return self._extract_enum(text_lower, extractor)

        elif extractor_type == 'computed':
            # Computed fields are handled in a second pass after all other extractions
            # Return None here; they're calculated in _calculate_computed_fields
            return None

        return None

    def _get_compiled_pattern(self, pattern: str) -> Optional[Pattern]:
        """Get compiled regex pattern with caching and validation"""
        if pattern in _compiled_patterns:
            return _compiled_patterns[pattern]

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            _compiled_patterns[pattern] = compiled
            return compiled
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            return None

    def _has_negation_in_context(
        self, text_lower: str, start: int, end: int, negation_words: List[str]
    ) -> bool:
        """
        Check if any negation words appear in context around a match.

        Args:
            text_lower: Lowercased text to search
            start: Start position of the match
            end: End position of the match
            negation_words: List of negation words to check for

        Returns:
            True if negation word found in context
        """
        context_start = max(0, start - NEGATION_CONTEXT_WINDOW)
        context_end = min(len(text_lower), end + NEGATION_CONTEXT_WINDOW)
        context = text_lower[context_start:context_end]
        return any(neg in context for neg in negation_words)

    def _parse_numeric(
        self, match: re.Match, original_text: str, value_type: str
    ) -> Optional[Union[int, float]]:
        """Parse numeric values from regex match"""
        value_str = match.group(1).replace(',', '')

        if value_type == 'int':
            return int(value_str)

        elif value_type == 'float':
            return float(value_str)

        elif value_type == 'percentage':
            return float(value_str)

        elif value_type == 'money':
            # Check for k/m/b suffixes
            match_text = original_text[match.start():match.end()].lower()
            multiplier = 1
            if 'k' in match_text:
                multiplier = 1000
            elif 'm' in match_text:
                multiplier = 1000000
            elif 'b' in match_text:
                multiplier = 1000000000

            return float(value_str) * multiplier

        return None

    def _extract_date(self, text: str, extractor: Dict) -> Optional[str]:
        """
        Extract a date from text.

        Returns ISO format string (YYYY-MM-DD) or None.

        Extractor config options:
        - pattern: custom regex pattern (optional)
        - format: expected date format for custom pattern (optional)
        - keywords: context keywords to search near (optional)
        """
        # Try custom pattern first if provided
        custom_pattern = extractor.get('pattern')
        if custom_pattern:
            compiled = self._get_compiled_pattern(custom_pattern)
            if compiled:
                match = compiled.search(text)
                if match:
                    date_str = match.group(1) if match.groups() else match.group(0)
                    return self._normalize_date(date_str, extractor.get('format'))

        # If keywords provided, search near those keywords
        keywords = extractor.get('keywords', [])
        search_text = text
        if keywords:
            # Find text near any keyword
            text_lower = text.lower()
            for keyword in keywords:
                kw_lower = keyword.lower()
                if kw_lower in text_lower:
                    # Get context around keyword
                    pos = text_lower.find(kw_lower)
                    search_text = text[pos:pos + KEYWORD_SEARCH_CONTEXT]
                    break

        # Try all standard date patterns
        for pattern, fmt in DATE_PATTERNS:
            compiled = self._get_compiled_pattern(pattern)
            if compiled:
                match = compiled.search(search_text)
                if match:
                    date_str = match.group(0)
                    normalized = self._normalize_date(date_str, fmt)
                    if normalized:
                        return normalized

        return None

    def _extract_datetime(self, text: str, extractor: Dict) -> Optional[str]:
        """
        Extract a datetime from text.

        Returns ISO format string (YYYY-MM-DDTHH:MM:SS) or None.
        """
        # Try custom pattern first if provided
        custom_pattern = extractor.get('pattern')
        if custom_pattern:
            compiled = self._get_compiled_pattern(custom_pattern)
            if compiled:
                match = compiled.search(text)
                if match:
                    dt_str = match.group(1) if match.groups() else match.group(0)
                    return self._normalize_datetime(dt_str)

        # Try all standard datetime patterns
        for pattern, _ in DATETIME_PATTERNS:
            compiled = self._get_compiled_pattern(pattern)
            if compiled:
                match = compiled.search(text)
                if match:
                    dt_str = match.group(1) if match.groups() else match.group(0)
                    normalized = self._normalize_datetime(dt_str)
                    if normalized:
                        return normalized

        # Fall back to date extraction if no datetime found
        date_result = self._extract_date(text, extractor)
        if date_result:
            return f"{date_result}T00:00:00"

        return None

    def _normalize_date(self, date_str: str, fmt: Optional[str] = None) -> Optional[str]:
        """Normalize a date string to ISO format (YYYY-MM-DD)"""
        date_str = date_str.strip()

        # Try explicit format if provided
        if fmt:
            try:
                # Handle formats with separate groups
                if fmt == '%Y-%m-%d':
                    parts = re.split(r'[-/]', date_str)
                    if len(parts) == 3:
                        return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                elif fmt == '%m-%d-%Y':
                    parts = re.split(r'[-/]', date_str)
                    if len(parts) == 3:
                        return f"{parts[2]}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                elif fmt == '%m-%d-%y':
                    parts = re.split(r'[-/]', date_str)
                    if len(parts) == 3:
                        year = int(parts[2])
                        year = year + 2000 if year < 50 else year + 1900
                        return f"{year}-{int(parts[0]):02d}-{int(parts[1]):02d}"
            except (ValueError, IndexError):
                pass

        # Try common formats using dateutil-style parsing
        formats_to_try = [
            '%Y-%m-%d', '%Y/%m/%d',
            '%m-%d-%Y', '%m/%d/%Y',
            '%m-%d-%y', '%m/%d/%y',
            '%B %d, %Y', '%B %d %Y',
            '%b %d, %Y', '%b %d %Y',
            '%d %B %Y', '%d %b %Y',
        ]

        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return None

    def _normalize_datetime(self, dt_str: str) -> Optional[str]:
        """Normalize a datetime string to ISO format"""
        dt_str = dt_str.strip().replace('T', ' ')

        formats_to_try = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
            '%m-%d-%Y %I:%M %p',
            '%m-%d-%Y %I:%M:%S %p',
            '%m/%d/%Y %I:%M %p',
            '%m/%d/%Y %I:%M:%S %p',
            '%m-%d-%Y %H:%M',
            '%m/%d/%Y %H:%M',
        ]

        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(dt_str, fmt)
                return dt.strftime('%Y-%m-%dT%H:%M:%S')
            except ValueError:
                continue

        return None

    def _extract_list(self, text: str, text_lower: str, extractor: Dict) -> Optional[List[Any]]:
        """
        Extract multiple values into a list.

        Extractor config options:
        - pattern: regex pattern with capture group for each item
        - item_type: type of each item ('string', 'int', 'float')
        - separator: delimiter between items (default: comma)
        - keywords: context keywords to search near (optional)
        """
        pattern = extractor.get('pattern')
        item_type = extractor.get('item_type', 'string')
        separator = extractor.get('separator', r'[,;]\s*')

        results = []

        if pattern:
            compiled = self._get_compiled_pattern(pattern)
            if compiled:
                # Find all matches
                matches = compiled.findall(text if item_type != 'string' else text_lower)
                for match in matches:
                    value = match if isinstance(match, str) else match[0] if match else None
                    if value:
                        converted = self._convert_list_item(value, item_type)
                        if converted is not None:
                            results.append(converted)

        # If no pattern or no results, try keyword-based extraction
        if not results:
            keywords = extractor.get('keywords', [])
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    results.append(keyword)

        return results if results else None

    def _convert_list_item(self, value: str, item_type: str) -> Any:
        """Convert a list item to the specified type"""
        value = value.strip().replace(',', '')
        try:
            if item_type == 'int':
                return int(float(value))
            elif item_type == 'float':
                return float(value)
            else:
                return value
        except (ValueError, TypeError):
            return value if item_type == 'string' else None

    def _extract_enum(self, text_lower: str, extractor: Dict) -> Optional[str]:
        """
        Extract a value from predefined choices.

        Extractor config options:
        - choices: dict mapping choice values to keywords/patterns
          e.g., {"approved": ["approved", "accepted"], "denied": ["denied", "rejected"]}
        - default: default value if no match found (optional)
        """
        choices = extractor.get('choices', {})
        default = extractor.get('default')

        # Check each choice
        for choice_value, keywords in choices.items():
            if isinstance(keywords, str):
                keywords = [keywords]

            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return choice_value

        return default

    def _calculate_computed_fields(
        self,
        extracted: Dict,
        text_lower: str,
        computed_extractors: Dict[str, Dict],
        include_confidence: bool = False
    ) -> Dict:
        """
        Calculate ontology-defined computed fields.

        Computed field extractor config options:
        - formula: dict defining the computation (e.g., {"count_true": ["field1", "field2"]})
        - depends_on: list of field names this computation depends on
        - default: default value if computation fails

        Supported formulas:
        - count_true: count number of true boolean fields
        - sum: sum numeric fields
        - any: true if any field is true
        - all: true if all fields are true
        - formula: arithmetic expression with field references
        """

        def get_value(field: str, default: Any = None) -> Any:
            """Get raw value whether in confidence mode or not"""
            val = extracted.get(field, default)
            if include_confidence and isinstance(val, ExtractionResult):
                return val.value
            return val

        def set_computed(field: str, value: Any):
            """Set a computed field with high confidence"""
            if include_confidence:
                extracted[field] = ExtractionResult(
                    value=value,
                    confidence=ConfidenceScores.COMPUTED,
                    source='computed',
                    extractor_type='computed'
                )
            else:
                extracted[field] = value

        # Topological sort: compute fields with no dependencies first
        # Simple approach: multiple passes until all computed
        computed_names = set(computed_extractors.keys())
        remaining = dict(computed_extractors)
        max_iterations = len(remaining) + 1
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            computed_this_pass = []

            for field_name, extractor in remaining.items():
                formula = extractor.get('formula')
                default = extractor.get('default')

                if not formula:
                    # Simple computed field with no formula - use default
                    if default is not None:
                        set_computed(field_name, default)
                    computed_this_pass.append(field_name)
                    continue

                # Check if dependencies are satisfied (references to other computed fields)
                deps = self._extract_formula_dependencies(formula)
                uncomputed_deps = deps & computed_names - set(extracted.keys())
                if uncomputed_deps:
                    # Dependencies not yet computed, skip for now
                    continue

                try:
                    result = self._evaluate_formula(formula, extracted, get_value)
                    if result is not None:
                        set_computed(field_name, result)
                    elif default is not None:
                        set_computed(field_name, default)
                    computed_this_pass.append(field_name)
                except Exception as e:
                    logger.warning(f"Error computing field {field_name}: {e}")
                    if default is not None:
                        set_computed(field_name, default)
                    computed_this_pass.append(field_name)

            # Remove computed fields from remaining
            for name in computed_this_pass:
                remaining.pop(name, None)

        return extracted

    def _extract_formula_dependencies(self, formula: Any) -> Set[str]:
        """Extract field names referenced in a formula"""
        deps: Set[str] = set()
        if isinstance(formula, str):
            deps.add(formula)
        elif isinstance(formula, dict):
            for key, value in formula.items():
                if isinstance(value, list):
                    for item in value:
                        deps.update(self._extract_formula_dependencies(item))
                else:
                    deps.update(self._extract_formula_dependencies(value))
        return deps

    # ==========================================================================
    # Formula Evaluation - Refactored into smaller methods
    # ==========================================================================

    # Mapping of comparison operators to their functions
    _COMPARISON_OPS: Dict[str, Callable[[Any, Any], bool]] = {
        'gt': operator.gt,
        '>': operator.gt,
        'gte': operator.ge,
        '>=': operator.ge,
        'lt': operator.lt,
        '<': operator.lt,
        'lte': operator.le,
        '<=': operator.le,
    }

    def _normalize_args(self, args: Any) -> List[Any]:
        """Ensure args is always a list"""
        return args if isinstance(args, list) else [args]

    def _resolve_value(
        self, arg: Any, extracted: Dict, get_value: Callable, default: Any = None
    ) -> Any:
        """
        Resolve a formula argument to its actual value.

        Args can be:
        - A dict (nested formula) -> recursively evaluate
        - A string (field reference) -> look up with get_value
        - A literal value -> return as-is
        """
        if isinstance(arg, dict):
            return self._evaluate_formula(arg, extracted, get_value)
        elif isinstance(arg, str):
            return get_value(arg, default) if default is not None else get_value(arg)
        return arg

    def _resolve_args(
        self, args: List[Any], extracted: Dict, get_value: Callable, default: Any = None
    ) -> List[Any]:
        """Resolve a list of formula arguments to their actual values"""
        return [self._resolve_value(a, extracted, get_value, default) for a in args]

    def _eval_comparison(
        self, op: str, args: List, extracted: Dict, get_value: Callable
    ) -> Optional[bool]:
        """Evaluate a comparison operation (gt, gte, lt, lte)"""
        if len(args) != 2:
            return None
        left = self._resolve_value(args[0], extracted, get_value)
        right = self._resolve_value(args[1], extracted, get_value)
        if left is None or right is None:
            return None
        return self._COMPARISON_OPS[op](left, right)

    def _eval_arithmetic(
        self, op: str, args: List, extracted: Dict, get_value: Callable
    ) -> Optional[Union[int, float]]:
        """Evaluate an arithmetic operation (add, mul)"""
        if len(args) < 2:
            return None
        values = self._resolve_args(args, extracted, get_value)
        if not all(v is not None for v in values):
            return None

        if op in ('add', '+'):
            return sum(values)
        elif op in ('mul', '*'):
            result = 1
            for v in values:
                result *= v
            return result
        return None

    def _eval_logical(
        self, op: str, args: Any, extracted: Dict, get_value: Callable
    ) -> Optional[bool]:
        """Evaluate a logical operation (any, all, and, or)"""
        fields = self._normalize_args(args)
        values = self._resolve_args(fields, extracted, get_value, default=False)
        non_null = [v for v in values if v is not None]

        if not non_null:
            return None

        if op in ('any', 'or'):
            return any(non_null)
        elif op in ('all', 'and'):
            return all(non_null)
        return None

    def _eval_counting(
        self, op: str, args: Any, get_value: Callable
    ) -> int:
        """Evaluate a counting operation (count_true, count_fields, sum)"""
        fields = self._normalize_args(args)

        if op == 'count_true':
            return sum(1 for f in fields if get_value(f, False) is True)
        elif op == 'count_fields':
            return sum(1 for f in fields if get_value(f) is not None)
        elif op == 'sum':
            total = 0
            for f in fields:
                val = get_value(f, 0) if isinstance(f, str) else f
                if isinstance(val, (int, float)):
                    total += val
            return total
        return 0

    def _eval_conditional(
        self, args: List, extracted: Dict, get_value: Callable
    ) -> Any:
        """Evaluate a conditional (if-then-else) expression"""
        if len(args) != 3:
            return None

        condition, then_val, else_val = args
        cond_result = self._resolve_value(condition, extracted, get_value)

        if cond_result:
            return self._resolve_value(then_val, extracted, get_value)
        else:
            return self._resolve_value(else_val, extracted, get_value)

    def _eval_not(
        self, args: Any, extracted: Dict, get_value: Callable
    ) -> Optional[bool]:
        """Evaluate a NOT operation"""
        val = self._resolve_value(args, extracted, get_value)
        return not val if val is not None else None

    def _evaluate_formula(self, formula: Dict, extracted: Dict, get_value: Callable) -> Any:
        """
        Evaluate a formula expression.

        Supported operations:
        - count_true: {"count_true": ["field1", "field2", ...]} - count true booleans
        - count_fields: {"count_fields": ["field1", ...]} - count non-null fields
        - sum: {"sum": ["field1", "field2"]} - sum numeric values
        - any: {"any": ["field1", "field2"]} - true if any is true
        - all: {"all": ["field1", "field2"]} - true if all are true
        - gt/gte/lt/lte: comparison operations
        - add/mul: arithmetic operations
        - if: {"if": [condition, then_value, else_value]} - conditional
        - not: {"not": expr} - logical negation
        - and/or: logical operations
        """
        if not isinstance(formula, dict) or len(formula) != 1:
            return None

        op = list(formula.keys())[0]
        args = formula[op]

        # Dispatch to specialized evaluators
        if op in self._COMPARISON_OPS:
            return self._eval_comparison(op, args, extracted, get_value)

        elif op in ('add', '+', 'mul', '*'):
            return self._eval_arithmetic(op, args, extracted, get_value)

        elif op in ('any', 'all', 'and', 'or'):
            return self._eval_logical(op, args, extracted, get_value)

        elif op in ('count_true', 'count_fields', 'sum'):
            return self._eval_counting(op, args, get_value)

        elif op == 'if':
            return self._eval_conditional(args, extracted, get_value)

        elif op == 'not':
            return self._eval_not(args, extracted, get_value)

        return None

    def _calculate_derived_fields(
        self, extracted: Dict[str, Any], text_lower: str, include_confidence: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate fields that depend on other fields or ontology-defined computations.

        NOTE: Domain-specific derived fields (like HIPAA phi_count, risk_score) should
        be defined in the ontology using the 'computed' extractor type, not hardcoded here.
        The fields below are kept for backwards compatibility but should be migrated
        to ontology definitions.
        """

        def get_value(field: str, default: Any = None) -> Any:
            """Get raw value whether in confidence mode or not"""
            val = extracted.get(field, default)
            if include_confidence and isinstance(val, ExtractionResult):
                return val.value
            return val

        def set_derived(field: str, value: Any):
            """Set a derived field with high confidence"""
            if include_confidence:
                extracted[field] = ExtractionResult(
                    value=value,
                    confidence=ConfidenceScores.COMPUTED,
                    source='computed',
                    extractor_type='computed'
                )
            else:
                extracted[field] = value

        # Fee percentage - generic calculation
        fees = get_value('fees')
        loan_amount = get_value('loan_amount')
        if fees is not None and loan_amount is not None and loan_amount > 0:
            set_derived('fee_percentage', (fees / loan_amount) * 100)

        # Word count - useful for response length constraints
        word_count = len(text_lower.split())
        set_derived('word_count', word_count)

        # NOTE: Domain-specific computed fields (like HIPAA's phi_count, has_phi, risk_score)
        # are now defined in the ontology's extractors section using the 'computed' type.
        # See _calculate_computed_fields() for formula evaluation.

        return extracted
