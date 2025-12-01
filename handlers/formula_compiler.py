"""
Formula Compiler for aare.ai
Compiles structured JSON formulas into Z3 expressions

Supported operators:
- Logical: and, or, not, implies, ite (if-then-else)
- Comparison: ==, !=, <, <=, >, >=
- Arithmetic: +, -, *, /, min, max
- Constants: true, false

Example formula:
{
  "or": [
    {"<=": ["dti", 43]},
    {">=": ["compensating_factors", 2]}
  ]
}
"""
from typing import Dict, Any, Union
from z3 import And, Or, Not, Implies, If, Bool, Int, Real, BoolVal, RealVal, is_bool, is_int, is_real

# All recognized operators
OPERATORS = {
    "and", "or", "not", "implies", "ite", "if",
    "==", "!=", "<", "<=", ">", ">=",
    "+", "-", "*", "/", "min", "max",
    "const", "var"
}


class FormulaCompiler:
    """Compiles JSON formula structures into Z3 expressions"""

    def compile(self, formula: Dict, z3_vars: Dict) -> Any:
        """
        Compile a JSON formula into a Z3 expression.

        Args:
            formula: A dict representing the formula structure
            z3_vars: Dict mapping variable names to Z3 variables

        Returns:
            A Z3 expression
        """
        if formula is None:
            return BoolVal(True)

        # Handle non-dict values (constants passed directly)
        if not isinstance(formula, dict):
            return formula

        # Validate: only one operator per formula dict
        ops_in_formula = [k for k in formula.keys() if k in OPERATORS]
        if len(ops_in_formula) > 1:
            raise ValueError(f"Formula has multiple operators: {ops_in_formula}. Use one operator per dict.")

        # Logical operators
        if "and" in formula:
            operands = [self.compile(op, z3_vars) for op in formula["and"]]
            return And(*operands)

        if "or" in formula:
            operands = [self.compile(op, z3_vars) for op in formula["or"]]
            return Or(*operands)

        if "not" in formula:
            return Not(self.compile(formula["not"], z3_vars))

        if "implies" in formula:
            args = formula["implies"]
            if len(args) != 2:
                raise ValueError("implies requires exactly 2 arguments")
            return Implies(self.compile(args[0], z3_vars),
                          self.compile(args[1], z3_vars))

        # If-then-else (ite)
        if "ite" in formula or "if" in formula:
            args = formula.get("ite") or formula.get("if")
            if len(args) != 3:
                raise ValueError("ite/if requires exactly 3 arguments: [condition, then, else]")
            cond = self.compile(args[0], z3_vars)
            then_expr = self.compile(args[1], z3_vars)
            else_expr = self.compile(args[2], z3_vars)
            return If(cond, then_expr, else_expr)

        # Comparison operators
        if "==" in formula:
            left, right = self._resolve_operands(formula["=="], z3_vars)
            return left == right

        if "!=" in formula:
            left, right = self._resolve_operands(formula["!="], z3_vars)
            return left != right

        if "<" in formula:
            left, right = self._resolve_operands(formula["<"], z3_vars)
            return left < right

        if "<=" in formula:
            left, right = self._resolve_operands(formula["<="], z3_vars)
            return left <= right

        if ">" in formula:
            left, right = self._resolve_operands(formula[">"], z3_vars)
            return left > right

        if ">=" in formula:
            left, right = self._resolve_operands(formula[">="], z3_vars)
            return left >= right

        # Arithmetic operators (return numeric Z3 expressions)
        if "+" in formula:
            left, right = self._resolve_operands(formula["+"], z3_vars)
            return left + right

        if "-" in formula:
            left, right = self._resolve_operands(formula["-"], z3_vars)
            return left - right

        if "*" in formula:
            left, right = self._resolve_operands(formula["*"], z3_vars)
            return left * right

        if "/" in formula:
            left, right = self._resolve_operands(formula["/"], z3_vars)
            return left / right

        # Min/max operators (useful for "fee capped at lesser of $500 or 3%")
        if "min" in formula:
            left, right = self._resolve_operands(formula["min"], z3_vars)
            return If(left <= right, left, right)

        if "max" in formula:
            left, right = self._resolve_operands(formula["max"], z3_vars)
            return If(left >= right, left, right)

        # Boolean constants
        if "const" in formula:
            val = formula["const"]
            if val is True or val == "true":
                return BoolVal(True)
            if val is False or val == "false":
                return BoolVal(False)
            # Numeric constant - return as-is for use in comparisons
            return val

        # Variable reference (shorthand: {"var": "name"})
        if "var" in formula:
            var_name = formula["var"]
            if var_name not in z3_vars:
                raise ValueError(f"Unknown variable: {var_name}")
            return z3_vars[var_name]

        raise ValueError(f"Unknown formula structure: {formula}")

    def _resolve_operands(self, args: list, z3_vars: Dict) -> tuple:
        """
        Resolve a pair of operands for binary operators.

        Operands can be:
        - Variable names (strings) -> look up in z3_vars
        - Numeric constants (int/float) -> use directly
        - Boolean constants (True/False) -> use directly
        - Nested formulas (dicts) -> compile recursively
        """
        if len(args) != 2:
            raise ValueError(f"Binary operator requires exactly 2 arguments, got {len(args)}")

        left = self._resolve_operand(args[0], z3_vars)
        right = self._resolve_operand(args[1], z3_vars)
        return left, right

    def _resolve_operand(self, operand: Union[str, int, float, bool, Dict], z3_vars: Dict) -> Any:
        """Resolve a single operand to a Z3 expression or constant."""
        # String -> variable name lookup
        if isinstance(operand, str):
            if operand not in z3_vars:
                raise ValueError(f"Unknown variable: {operand}")
            return z3_vars[operand]

        # Numeric or boolean constant -> use directly
        if isinstance(operand, (int, float, bool)):
            return operand

        # Nested formula -> compile recursively
        if isinstance(operand, dict):
            return self.compile(operand, z3_vars)

        raise ValueError(f"Invalid operand type: {type(operand)}")
