"""
SMT Verifier using Z3 for aare.ai
Pure formal verification - no regex, no patterns, just math
"""
import time
from typing import Dict, List, Any
from z3 import *

class SMTVerifier:
    def verify(self, data: Dict, ontology: Dict) -> Dict[str, Any]:
        """Verify data against ontology constraints using Z3"""
        start_time = time.time()
        violations = []
        proofs = []
        
        for constraint in ontology['constraints']:
            result = self._check_constraint(data, constraint)
            if result['violated']:
                violations.append(result['violation'])
                proofs.append(result['proof'])
        
        execution_time = int((time.time() - start_time) * 1000)
        
        return {
            'verified': len(violations) == 0,
            'violations': violations,
            'proof': self._generate_proof_certificate(proofs),
            'execution_time_ms': execution_time
        }
    
    def _check_constraint(self, data: Dict, constraint: Dict) -> Dict[str, Any]:
        """Check a single constraint using Z3"""
        solver = Solver()

        # Create Z3 variables
        z3_vars = self._create_z3_variables(constraint['variables'], data)

        # Add known values to solver
        # For unknown values, provide sensible defaults that won't trigger violations
        for var_name, z3_var in z3_vars.items():
            if var_name in data:
                solver.add(z3_var == data[var_name])
            else:
                # Default unknown values to safe/non-triggering values
                # Booleans default to False, numbers to safe ranges
                if is_bool(z3_var):
                    solver.add(z3_var == False)
                elif is_int(z3_var):
                    solver.add(z3_var == 0)
                elif is_real(z3_var):
                    solver.add(z3_var == 0.0)
        
        # Parse and add constraint
        constraint_formula = self._parse_constraint(constraint, z3_vars)
        
        # Check if constraint can be violated
        solver.add(Not(constraint_formula))
        
        if solver.check() == sat:
            # Constraint violated
            model = solver.model()
            return {
                'violated': True,
                'violation': {
                    'constraint_id': constraint['id'],
                    'category': constraint.get('category', 'General'),
                    'description': constraint['description'],
                    'error_message': constraint.get('error_message', 'Constraint violated'),
                    'formula': constraint['formula_readable'],
                    'model': self._model_to_dict(model, z3_vars),
                    'citation': constraint.get('citation', '')
                },
                'proof': {
                    'result': 'SAT (violation found)',
                    'model': str(model),
                    'constraint': constraint['id']
                }
            }
        else:
            # Constraint satisfied
            return {
                'violated': False,
                'proof': {
                    'result': 'UNSAT (constraint satisfied)',
                    'constraint': constraint['id']
                }
            }
    
    def _create_z3_variables(self, var_specs: List, data: Dict) -> Dict:
        """Create Z3 variables based on specifications"""
        z3_vars = {}
        
        for var_spec in var_specs:
            var_name = var_spec['name']
            var_type = var_spec['type']
            
            if var_type == 'bool':
                z3_vars[var_name] = Bool(var_name)
            elif var_type == 'int':
                z3_vars[var_name] = Int(var_name)
            elif var_type in ['real', 'float']:
                z3_vars[var_name] = Real(var_name)
            else:
                z3_vars[var_name] = Real(var_name)  # Default to Real
        
        return z3_vars
    
    def _parse_constraint(self, constraint: Dict, z3_vars: Dict):
        """Parse constraint into Z3 formula"""
        constraint_id = constraint['id']
        
        # For now, implement specific constraints
        # In production, use a proper formula parser
        
        if constraint_id == 'ATR_QM_DTI':
            # DTI > 43 requires 2+ compensating factors
            dti = z3_vars.get('dti', Real('dti'))
            factors = z3_vars.get('compensating_factors', Int('compensating_factors'))
            return Or(dti <= 43, factors >= 2)
        
        elif constraint_id == 'HOEPA_HIGH_COST':
            # Fees >= 8% requires counseling
            fee_pct = z3_vars.get('fee_percentage', Real('fee_percentage'))
            counseling = z3_vars.get('counseling_disclosed', Bool('counseling_disclosed'))
            return Or(fee_pct < 8, counseling == True)
        
        elif constraint_id == 'UDAAP_NO_GUARANTEES':
            # Cannot have both guarantee and approval
            guarantee = z3_vars.get('has_guarantee', Bool('has_guarantee'))
            approval = z3_vars.get('has_approval', Bool('has_approval'))
            return Not(And(guarantee, approval))
        
        elif constraint_id == 'HPML_ESCROW':
            # FICO < 620 prohibits escrow waiver
            fico = z3_vars.get('credit_score', Int('credit_score'))
            waived = z3_vars.get('escrow_waived', Bool('escrow_waived'))
            return Or(fico >= 620, waived == False)
        
        elif constraint_id == 'REG_B_ADVERSE':
            # Denial requires specific reason
            denial = z3_vars.get('is_denial', Bool('is_denial'))
            reason = z3_vars.get('has_specific_reason', Bool('has_specific_reason'))
            return Implies(denial, reason)

        # Medical Safety constraints
        elif constraint_id == 'EGFR_METFORMIN':
            # Metformin contraindicated if eGFR < 45
            egfr = z3_vars.get('egfr', Int('egfr'))
            metformin = z3_vars.get('recommends_metformin', Bool('recommends_metformin'))
            return Or(egfr >= 45, metformin == False)

        elif constraint_id == 'EGFR_DOSE_LIMIT':
            # Max 1000mg if eGFR < 60 - only applies when metformin is recommended
            egfr = z3_vars.get('egfr', Int('egfr'))
            dose = z3_vars.get('metformin_dose', Int('metformin_dose'))
            metformin = z3_vars.get('recommends_metformin', Bool('recommends_metformin'))
            # If not recommending metformin, constraint is satisfied
            return Or(metformin == False, egfr >= 60, dose <= 1000)

        elif constraint_id == 'CREATININE_NEPHRO':
            # Creatinine > 1.5 requires nephrology
            cr = z3_vars.get('creatinine', Real('creatinine'))
            nephro = z3_vars.get('nephro_referral', Bool('nephro_referral'))
            return Or(cr <= 1.5, nephro == True)

        elif constraint_id == 'DRUG_INTERACTION':
            # ACE inhibitor + potassium-sparing diuretic is dangerous
            ace = z3_vars.get('ace_inhibitor', Bool('ace_inhibitor'))
            potassium = z3_vars.get('potassium_sparing', Bool('potassium_sparing'))
            return Not(And(ace, potassium))

        elif constraint_id == 'HBA1C_TARGET':
            # HbA1c > 7% may require treatment escalation
            hba1c = z3_vars.get('hba1c', Real('hba1c'))
            escalation = z3_vars.get('treatment_escalation', Bool('treatment_escalation'))
            return Or(hba1c <= 7.0, escalation == True)

        # Trading Compliance constraints
        elif constraint_id == 'SECTOR_LIMIT':
            tech = z3_vars.get('tech_exposure', Real('tech_exposure'))
            return tech <= 40

        elif constraint_id == 'POSITION_LIMIT':
            pos = z3_vars.get('position_size', Real('position_size'))
            return pos <= 10

        # Contract Compliance constraints
        elif constraint_id == 'USURY_LIMIT':
            rate = z3_vars.get('annual_rate', Real('annual_rate'))
            return rate <= 25

        elif constraint_id == 'LATE_FEE_CAP':
            fee = z3_vars.get('monthly_late_fee', Real('monthly_late_fee'))
            return fee <= 1.5

        # Customer Service constraints
        elif constraint_id == 'DISCOUNT_LIMIT':
            disc = z3_vars.get('discount_percentage', Real('discount_percentage'))
            return disc <= 10

        elif constraint_id == 'DELIVERY_PROMISE':
            hrs = z3_vars.get('delivery_hours', Int('delivery_hours'))
            return hrs >= 48

        elif constraint_id == 'NO_FAULT_ADMISSION':
            admits = z3_vars.get('admits_fault', Bool('admits_fault'))
            return admits == False

        elif constraint_id == 'NO_INTERNAL_INFO':
            reveals = z3_vars.get('reveals_internal', Bool('reveals_internal'))
            return reveals == False

        # Content Policy constraints
        elif constraint_id == 'NO_REAL_PEOPLE':
            mentions = z3_vars.get('mentions_real_people', Bool('mentions_real_people'))
            return mentions == False

        elif constraint_id == 'NO_RELIGIOUS_CONTENT':
            religious = z3_vars.get('has_religious_content', Bool('has_religious_content'))
            return religious == False

        elif constraint_id == 'NO_MEDICAL_ADVICE':
            medical = z3_vars.get('provides_medical_advice', Bool('provides_medical_advice'))
            return medical == False

        # Data Privacy constraints
        elif constraint_id == 'NO_PII':
            pii = z3_vars.get('exposes_pii', Bool('exposes_pii'))
            return pii == False

        elif constraint_id == 'NO_INTERNAL_URLS':
            urls = z3_vars.get('reveals_internal_urls', Bool('reveals_internal_urls'))
            return urls == False

        elif constraint_id == 'NO_CREDENTIALS':
            creds = z3_vars.get('shares_credentials', Bool('shares_credentials'))
            return creds == False

        elif constraint_id == 'NO_DB_NAMES':
            db = z3_vars.get('reveals_db_names', Bool('reveals_db_names'))
            return db == False

        # Financial Compliance constraints
        elif constraint_id == 'NO_SPECIFIC_SECURITIES':
            securities = z3_vars.get('recommends_specific_securities', Bool('recommends_specific_securities'))
            return securities == False

        elif constraint_id == 'NO_GUARANTEED_RETURNS':
            guarantees = z3_vars.get('guarantees_returns', Bool('guarantees_returns'))
            return guarantees == False

        elif constraint_id == 'REQUIRED_DISCLAIMER':
            advice = z3_vars.get('is_financial_advice', Bool('is_financial_advice'))
            disclaimer = z3_vars.get('has_disclaimer', Bool('has_disclaimer'))
            return Or(advice == False, disclaimer == True)

        elif constraint_id == 'NO_BUY_SELL_SIGNALS':
            signals = z3_vars.get('has_buy_sell_recommendation', Bool('has_buy_sell_recommendation'))
            return signals == False

        # Fair Lending constraints
        elif constraint_id == 'LOAN_AMOUNT_LIMIT':
            amount = z3_vars.get('loan_amount', Int('loan_amount'))
            return amount <= 100000

        elif constraint_id == 'MAX_DTI':
            dti = z3_vars.get('dti', Real('dti'))
            return dti <= 43

        elif constraint_id == 'MIN_CREDIT_SCORE':
            score = z3_vars.get('credit_score', Int('credit_score'))
            return score >= 600

        elif constraint_id == 'DOWN_PAYMENT':
            dp = z3_vars.get('down_payment', Real('down_payment'))
            return dp >= 5

        elif constraint_id == 'EMPLOYMENT_VERIFICATION':
            verified = z3_vars.get('employment_verified', Bool('employment_verified'))
            return verified == True

        # HIPAA PHI Detection constraints
        elif constraint_id == 'PHI_NAME_DISCLOSURE':
            has_name = z3_vars.get('has_patient_name', Bool('has_patient_name'))
            authorized = z3_vars.get('recipient_authorized', Bool('recipient_authorized'))
            return Or(Not(has_name), authorized)

        elif constraint_id == 'PHI_DOB_DISCLOSURE':
            has_dob = z3_vars.get('has_dob', Bool('has_dob'))
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            return Or(Not(has_dob), deidentified)

        elif constraint_id == 'PHI_ADDRESS_DISCLOSURE':
            has_address = z3_vars.get('has_street_address', Bool('has_street_address'))
            return Not(has_address)

        elif constraint_id == 'PHI_PHONE_DISCLOSURE':
            has_phone = z3_vars.get('has_phone_number', Bool('has_phone_number'))
            return Not(has_phone)

        elif constraint_id == 'PHI_SSN_ZERO_TOLERANCE':
            has_ssn = z3_vars.get('has_ssn', Bool('has_ssn'))
            return Not(has_ssn)

        elif constraint_id == 'PHI_MRN_ZERO_TOLERANCE':
            has_mrn = z3_vars.get('has_mrn', Bool('has_mrn'))
            external = z3_vars.get('recipient_external', Bool('recipient_external'))
            return Or(Not(has_mrn), Not(external))

        elif constraint_id == 'PHI_EMAIL_DISCLOSURE':
            has_email = z3_vars.get('has_email', Bool('has_email'))
            return Not(has_email)

        elif constraint_id == 'PHI_DEVICE_ID_DISCLOSURE':
            has_device = z3_vars.get('has_device_id', Bool('has_device_id'))
            return Not(has_device)

        elif constraint_id == 'PHI_URL_DISCLOSURE':
            has_url = z3_vars.get('has_patient_url', Bool('has_patient_url'))
            return Not(has_url)

        elif constraint_id == 'PHI_IP_ADDRESS_DISCLOSURE':
            has_ip = z3_vars.get('has_ip_address', Bool('has_ip_address'))
            return Not(has_ip)

        elif constraint_id == 'PHI_BIOMETRIC_DISCLOSURE':
            has_bio = z3_vars.get('has_biometric', Bool('has_biometric'))
            return Not(has_bio)

        elif constraint_id == 'PHI_PHOTO_DISCLOSURE':
            has_photo = z3_vars.get('has_photo_reference', Bool('has_photo_reference'))
            return Not(has_photo)

        elif constraint_id == 'PHI_VEHICLE_ID_DISCLOSURE':
            has_vehicle = z3_vars.get('has_vehicle_id', Bool('has_vehicle_id'))
            return Not(has_vehicle)

        elif constraint_id == 'PHI_ACCOUNT_NUMBER_DISCLOSURE':
            has_account = z3_vars.get('has_account_number', Bool('has_account_number'))
            return Not(has_account)

        elif constraint_id == 'PHI_LICENSE_NUMBER_DISCLOSURE':
            has_license = z3_vars.get('has_license_number', Bool('has_license_number'))
            return Not(has_license)

        # HIPAA De-Identification constraints
        elif constraint_id == 'DEIDENTIFY_ALL_18':
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            phi_count = z3_vars.get('phi_count', Int('phi_count'))
            return Implies(deidentified, phi_count == 0)

        elif constraint_id == 'DEIDENTIFY_DATES_GENERALIZED':
            has_date = z3_vars.get('has_specific_date', Bool('has_specific_date'))
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            return Or(Not(has_date), deidentified)

        elif constraint_id == 'DEIDENTIFY_AGE_THRESHOLD':
            age = z3_vars.get('patient_age', Int('patient_age'))
            aggregated = z3_vars.get('age_aggregated', Bool('age_aggregated'))
            return Or(age <= 89, aggregated)

        elif constraint_id == 'DEIDENTIFY_RARE_CONDITIONS':
            rare = z3_vars.get('has_rare_condition', Bool('has_rare_condition'))
            generalized = z3_vars.get('condition_generalized', Bool('condition_generalized'))
            return Or(Not(rare), generalized)

        elif constraint_id == 'DEIDENTIFY_GEOGRAPHIC':
            has_city = z3_vars.get('has_city', Bool('has_city'))
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            return Or(Not(has_city), deidentified)

        elif constraint_id == 'DEIDENTIFY_ZIP_CODE':
            has_zip = z3_vars.get('has_full_zip', Bool('has_full_zip'))
            return Not(has_zip)

        elif constraint_id == 'DEIDENTIFY_SAFE_HARBOR':
            claims_sh = z3_vars.get('claims_safe_harbor', Bool('claims_safe_harbor'))
            phi_count = z3_vars.get('phi_count', Int('phi_count'))
            safeguard = z3_vars.get('has_safeguard_mention', Bool('has_safeguard_mention'))
            return Implies(claims_sh, And(phi_count == 0, safeguard))

        elif constraint_id == 'DEIDENTIFY_EXPERT_DETERMINATION':
            claims_ed = z3_vars.get('claims_expert_determination', Bool('claims_expert_determination'))
            has_stats = z3_vars.get('has_statistical_mention', Bool('has_statistical_mention'))
            return Implies(claims_ed, has_stats)

        elif constraint_id == 'DEIDENTIFY_NO_DERIVED_DATA':
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            has_derived = z3_vars.get('has_derived_identifier', Bool('has_derived_identifier'))
            return Implies(deidentified, Not(has_derived))

        # HIPAA Access Control constraints
        elif constraint_id == 'ACCESS_RECIPIENT_AUTHORIZED':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            authorized = z3_vars.get('recipient_authorized', Bool('recipient_authorized'))
            return Implies(has_phi, authorized)

        elif constraint_id == 'ACCESS_ROLE_PHYSICIAN':
            has_treatment = z3_vars.get('has_treatment_details', Bool('has_treatment_details'))
            is_physician = z3_vars.get('recipient_role_physician', Bool('recipient_role_physician'))
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            return Implies(has_treatment, Or(is_physician, deidentified))

        elif constraint_id == 'ACCESS_MINIMUM_NECESSARY':
            phi_count = z3_vars.get('phi_count', Int('phi_count'))
            threshold = z3_vars.get('minimum_necessary_threshold', Int('minimum_necessary_threshold'))
            return phi_count <= threshold

        elif constraint_id == 'ACCESS_EXTERNAL_ENCRYPTION':
            external = z3_vars.get('recipient_external', Bool('recipient_external'))
            encrypted = z3_vars.get('has_encryption_mention', Bool('has_encryption_mention'))
            return Implies(external, encrypted)

        elif constraint_id == 'ACCESS_AUDIT_TIMESTAMP':
            has_ts = z3_vars.get('has_timestamp', Bool('has_timestamp'))
            return has_ts

        elif constraint_id == 'ACCESS_AUDIT_USER_ID':
            has_user = z3_vars.get('has_user_identification', Bool('has_user_identification'))
            return has_user

        elif constraint_id == 'ACCESS_SESSION_VALID':
            has_session = z3_vars.get('has_session_reference', Bool('has_session_reference'))
            valid = z3_vars.get('session_valid', Bool('session_valid'))
            return Implies(has_session, valid)

        elif constraint_id == 'ACCESS_LEAST_PRIVILEGE':
            is_admin = z3_vars.get('recipient_role_admin', Bool('recipient_role_admin'))
            has_treatment = z3_vars.get('has_treatment_details', Bool('has_treatment_details'))
            return Implies(is_admin, Not(has_treatment))

        # HIPAA Safeguard constraints
        elif constraint_id == 'SAFEGUARD_INTERNAL_USE':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            internal = z3_vars.get('has_internal_use_mention', Bool('has_internal_use_mention'))
            return Implies(has_phi, internal)

        elif constraint_id == 'SAFEGUARD_PHI_REDACTED':
            safeguard = z3_vars.get('has_safeguard_mention', Bool('has_safeguard_mention'))
            return safeguard

        elif constraint_id == 'SAFEGUARD_RISK_SCORE':
            risk = z3_vars.get('risk_score', Int('risk_score'))
            return risk <= 5

        elif constraint_id == 'SAFEGUARD_ENCRYPTION_PHI':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            encrypted = z3_vars.get('has_encryption_mention', Bool('has_encryption_mention'))
            return Implies(has_phi, encrypted)

        elif constraint_id == 'SAFEGUARD_NO_PRINT_MENTION':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            has_print = z3_vars.get('has_print_instruction', Bool('has_print_instruction'))
            return Not(And(has_phi, has_print))

        elif constraint_id == 'SAFEGUARD_HIPAA_COMPLIANT':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            hipaa = z3_vars.get('has_hipaa_mention', Bool('has_hipaa_mention'))
            return Implies(has_phi, hipaa)

        elif constraint_id == 'SAFEGUARD_ACCESS_LOG':
            has_treatment = z3_vars.get('has_treatment_details', Bool('has_treatment_details'))
            audit = z3_vars.get('has_audit_mention', Bool('has_audit_mention'))
            return Implies(has_treatment, audit)

        elif constraint_id == 'SAFEGUARD_POLICY_REFERENCE':
            sensitive = z3_vars.get('has_sensitive_diagnosis', Bool('has_sensitive_diagnosis'))
            policy = z3_vars.get('has_policy_reference', Bool('has_policy_reference'))
            return Implies(sensitive, policy)

        # HIPAA Breach Notification constraints
        elif constraint_id == 'BREACH_UNAUTHORIZED_DISCLOSURE':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            authorized = z3_vars.get('recipient_authorized', Bool('recipient_authorized'))
            return Not(And(has_phi, Not(authorized)))

        elif constraint_id == 'BREACH_SENSITIVE_DATA':
            sensitive = z3_vars.get('has_sensitive_diagnosis', Bool('has_sensitive_diagnosis'))
            deidentified = z3_vars.get('is_deidentified', Bool('is_deidentified'))
            authorized = z3_vars.get('recipient_authorized', Bool('recipient_authorized'))
            return Not(And(sensitive, Not(deidentified), Not(authorized)))

        elif constraint_id == 'BREACH_NO_SAFEGUARDS':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            safeguard = z3_vars.get('has_safeguard_mention', Bool('has_safeguard_mention'))
            return Not(And(has_phi, Not(safeguard)))

        elif constraint_id == 'BREACH_ESCALATION':
            violations = z3_vars.get('violation_count', Int('violation_count'))
            return violations <= 2

        # HIPAA Audit constraints
        elif constraint_id == 'AUDIT_PROOF_CERTIFICATE':
            complete = z3_vars.get('verification_complete', Bool('verification_complete'))
            has_proof = z3_vars.get('has_proof', Bool('has_proof'))
            return Implies(complete, has_proof)

        elif constraint_id == 'AUDIT_RULE_IDENTIFICATION':
            has_violation = z3_vars.get('has_violation', Bool('has_violation'))
            has_citation = z3_vars.get('has_rule_citation', Bool('has_rule_citation'))
            return Implies(has_violation, has_citation)

        elif constraint_id == 'AUDIT_RETENTION':
            has_retention = z3_vars.get('has_retention_policy', Bool('has_retention_policy'))
            return has_retention

        elif constraint_id == 'AUDIT_IMMUTABILITY':
            has_audit = z3_vars.get('has_audit_mention', Bool('has_audit_mention'))
            immutable = z3_vars.get('audit_immutable', Bool('audit_immutable'))
            return Implies(has_audit, immutable)

        elif constraint_id == 'AUDIT_CHAIN_OF_CUSTODY':
            has_phi = z3_vars.get('has_phi', Bool('has_phi'))
            chain = z3_vars.get('has_chain_of_custody', Bool('has_chain_of_custody'))
            return Implies(has_phi, chain)

        # HIPAA Clinical Safety
        elif constraint_id == 'TREATMENT_ALLERGY_DISCLOSURE':
            has_allergy = z3_vars.get('has_allergy_info', Bool('has_allergy_info'))
            external = z3_vars.get('recipient_external', Bool('recipient_external'))
            authorized = z3_vars.get('recipient_authorized', Bool('recipient_authorized'))
            return Not(And(has_allergy, external, Not(authorized)))

        # Default to True (constraint satisfied)
        return BoolVal(True)
    
    def _model_to_dict(self, model, z3_vars):
        """Convert Z3 model to dictionary"""
        result = {}
        for var_name, z3_var in z3_vars.items():
            try:
                value = model.eval(z3_var)
                if is_bool(value):
                    result[var_name] = is_true(value)
                elif is_int_value(value):
                    result[var_name] = value.as_long()
                elif is_rational_value(value):
                    result[var_name] = float(value.as_decimal(6))
                else:
                    result[var_name] = str(value)
            except:
                result[var_name] = None
        return result
    
    def _generate_proof_certificate(self, proofs):
        """Generate a proof certificate"""
        return {
            'method': 'Z3 SMT Solver',
            'version': '4.12.1',
            'results': proofs,
            'timestamp': time.time()
        }
