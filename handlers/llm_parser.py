"""
LLM output parser for aare.ai
Extracts structured data from unstructured LLM text
"""
import re
from typing import Dict, Any

class LLMParser:
    def parse(self, text: str, ontology: Dict) -> Dict[str, Any]:
        """Parse LLM output using ontology-defined extractors"""
        extracted = {}
        text_lower = text.lower()
        extractors = ontology.get('extractors', {})
        
        for field_name, extractor in extractors.items():
            value = self._extract_field(text, text_lower, extractor)
            if value is not None:
                extracted[field_name] = value
        
        # Calculate derived fields
        extracted = self._calculate_derived_fields(extracted, text_lower)
        
        return extracted
    
    def _extract_field(self, text, text_lower, extractor):
        """Extract a single field based on extractor configuration"""
        extractor_type = extractor.get('type')

        if extractor_type == 'boolean':
            # Check for keyword presence
            keywords = extractor.get('keywords', [])
            negation_words = extractor.get('negation_words', [])
            # Some keywords should check for negation, others shouldn't
            check_negation = extractor.get('check_negation', True)

            # Check if any keyword is present without negation
            for kw in keywords:
                if kw in text_lower:
                    # Only check negation for recommendation-type keywords
                    if check_negation and negation_words:
                        # Check for negation context around the keyword
                        kw_pos = text_lower.find(kw)
                        # Look at surrounding context (15 chars before keyword only)
                        # This prevents unrelated "no" words from triggering false negatives
                        context_start = max(0, kw_pos - 15)
                        context_end = kw_pos + len(kw)
                        context = text_lower[context_start:context_end]

                        # Only check specific negation words from the extractor config
                        if any(neg in context for neg in negation_words):
                            continue  # Try next keyword instead of returning False

                    # Found a keyword without negation
                    return True

            return False
        
        elif extractor_type in ['int', 'float', 'money', 'percentage']:
            # Use regex pattern
            pattern = extractor.get('pattern')
            if not pattern:
                return None
            
            match = re.search(pattern, text_lower)
            if match:
                return self._parse_numeric(match, text, extractor_type)
        
        elif extractor_type == 'string':
            # Extract string value
            pattern = extractor.get('pattern')
            if pattern:
                match = re.search(pattern, text_lower)
                if match:
                    return match.group(1) if match.groups() else match.group(0)
        
        return None
    
    def _parse_numeric(self, match, original_text, value_type):
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
    
    def _calculate_derived_fields(self, extracted, text_lower):
        """Calculate fields that depend on other fields"""
        # Fee percentage
        if 'fees' in extracted and 'loan_amount' in extracted:
            if extracted['loan_amount'] > 0:
                extracted['fee_percentage'] = (extracted['fees'] / extracted['loan_amount']) * 100

        # Compensating factors (simple heuristic)
        if 'compensating' in text_lower:
            if 'two' in text_lower or 'multiple' in text_lower:
                extracted['compensating_factors'] = 2
            elif 'one' in text_lower:
                extracted['compensating_factors'] = 1
            else:
                extracted['compensating_factors'] = 1
        else:
            extracted['compensating_factors'] = 0

        # HIPAA computed fields
        # Count PHI elements detected
        phi_fields = [
            'has_patient_name', 'has_dob', 'has_street_address', 'has_phone_number',
            'has_ssn', 'has_mrn', 'has_email', 'has_full_zip', 'has_city',
            'has_device_id', 'has_ip_address', 'has_biometric', 'has_photo_reference',
            'has_vehicle_id', 'has_account_number', 'has_license_number'
        ]
        phi_count = sum(1 for f in phi_fields if extracted.get(f, False))
        extracted['phi_count'] = phi_count

        # has_phi is true if any PHI element is present
        extracted['has_phi'] = phi_count > 0

        # Calculate risk score: (PHI_Count * 2) + (sensitive_diagnosis * 3)
        risk_score = phi_count * 2
        if extracted.get('has_sensitive_diagnosis', False):
            risk_score += 3
        if extracted.get('has_treatment_details', False) and not extracted.get('is_deidentified', False):
            risk_score += 2
        extracted['risk_score'] = risk_score

        # Set default threshold for minimum necessary
        extracted['minimum_necessary_threshold'] = 3

        # Audit fields - assume system provides these
        extracted['verification_complete'] = True
        extracted['has_proof'] = True
        extracted['has_rule_citation'] = True
        extracted['has_retention_policy'] = True
        extracted['audit_immutable'] = True
        extracted['has_chain_of_custody'] = True
        extracted['session_valid'] = True
        extracted['violation_count'] = 0  # Will be updated after verification

        return extracted
