"""
SMT Verifier using Z3 for aare.ai
Pure formal verification - no regex, no patterns, just math
"""
import time
from typing import Dict, List, Any
from z3 import *
from .formula_compiler import FormulaCompiler


class SMTVerifier:
    def __init__(self):
        self.compiler = FormulaCompiler()

    def verify(self, data: Dict, ontology: Dict) -> Dict[str, Any]:
        """Verify data against ontology constraints using Z3"""
        start_time = time.time()
        violations = []
        proofs = []
        all_missing_vars = set()

        for constraint in ontology['constraints']:
            result = self._check_constraint(data, constraint)
            if result['violated']:
                violations.append(result['violation'])
                proofs.append(result['proof'])
            # Track missing variables across all constraints
            all_missing_vars.update(result.get('missing_vars', []))

        execution_time = int((time.time() - start_time) * 1000)

        response = {
            'verified': len(violations) == 0,
            'violations': violations,
            'proof': self._generate_proof_certificate(proofs),
            'execution_time_ms': execution_time
        }

        # Add warnings for missing variables (helps auditors understand verification scope)
        if all_missing_vars:
            response['warnings'] = [f"Variables defaulted (not found in input): {sorted(all_missing_vars)}"]

        return response

    def _check_constraint(self, data: Dict, constraint: Dict) -> Dict[str, Any]:
        """Check a single constraint using Z3"""
        solver = Solver()

        # Create Z3 variables
        z3_vars = self._create_z3_variables(constraint['variables'], data)

        # Track missing variables for warnings
        missing_vars = []

        # Add known values to solver
        # For unknown values, provide sensible defaults that won't trigger violations
        for var_name, z3_var in z3_vars.items():
            if var_name in data:
                solver.add(z3_var == data[var_name])
            else:
                missing_vars.append(var_name)
                # Default unknown values to safe/non-triggering values
                # Booleans default to False, numbers to safe ranges
                if is_bool(z3_var):
                    solver.add(z3_var == False)
                elif is_int(z3_var):
                    solver.add(z3_var == 0)
                elif is_real(z3_var):
                    solver.add(z3_var == 0.0)

        # Compile the formula from JSON structure
        if 'formula' not in constraint:
            raise ValueError(f"Constraint {constraint['id']} missing 'formula' field. All constraints must have structured formulas.")

        constraint_formula = self.compiler.compile(constraint['formula'], z3_vars)

        # Check if constraint can be violated
        solver.add(Not(constraint_formula))

        if solver.check() == sat:
            # Constraint violated
            model = solver.model()
            return {
                'violated': True,
                'missing_vars': missing_vars,
                'violation': {
                    'constraint_id': constraint['id'],
                    'category': constraint.get('category', 'General'),
                    'description': constraint['description'],
                    'error_message': constraint.get('error_message', 'Constraint violated'),
                    'formula': constraint.get('formula_readable', str(constraint.get('formula', ''))),
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
                'missing_vars': missing_vars,
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
