# aare.ai Rule Authoring Guide

A comprehensive guide to writing compliance rules (ontologies) for the aare.ai `/verify` API.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core Concepts](#core-concepts)
3. [Ontology Structure](#ontology-structure)
4. [Writing Constraints](#writing-constraints)
5. [Formula Syntax Reference](#formula-syntax-reference)
6. [Writing Extractors](#writing-extractors)
7. [Testing Your Rules](#testing-your-rules)
8. [Best Practices](#best-practices)
9. [Complete Examples](#complete-examples)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### What is an Ontology?

An **ontology** is a JSON file that defines:
- **Constraints**: Logical rules that LLM outputs must satisfy
- **Extractors**: Patterns to extract structured data from unstructured text
- **Variables**: Data types used in constraints

### Your First Ontology

```json
{
  "name": "my-first-ontology",
  "version": "1.0.0",
  "description": "A simple ontology to verify loan amounts",
  "constraints": [
    {
      "id": "MAX_LOAN",
      "category": "Lending",
      "description": "Maximum loan amount is $100,000",
      "formula_readable": "loan_amount <= 100000",
      "formula": {"<=": ["loan_amount", 100000]},
      "variables": [
        {"name": "loan_amount", "type": "int"}
      ],
      "error_message": "Loan amount exceeds $100,000 maximum",
      "citation": "Internal Policy"
    }
  ],
  "extractors": {
    "loan_amount": {
      "type": "int",
      "pattern": "\\$([\\d,]+)"
    }
  }
}
```

### Test It

```bash
# Using the CLI
aare-verify "Approved loan for $75,000" --ontology my-first-ontology

# Using curl
curl -X POST https://api.aare.ai/verify \
  -H "Content-Type: application/json" \
  -d '{"llm_output": "Approved loan for $75,000", "ontology": "my-first-ontology"}'
```

---

## Core Concepts

### How Verification Works

```
LLM Output (text)
    |
    v
+-------------------+
| 1. EXTRACT        |  Extractors pull structured data
|    (LLMParser)    |  from unstructured text
+-------------------+
    |
    v
+-------------------+
| 2. COMPILE        |  JSON formulas compile to Z3
|    (FormulaCompiler) |  mathematical expressions
+-------------------+
    |
    v
+-------------------+
| 3. VERIFY         |  Z3 theorem prover checks
|    (SMTVerifier)  |  all constraints
+-------------------+
    |
    v
Result: verified=true/false + violations + proof certificate
```

### The Three Components

| Component | Purpose | Example |
|-----------|---------|---------|
| **Constraints** | Define what must be true | `dti <= 43` |
| **Variables** | Declare data types | `{"name": "dti", "type": "real"}` |
| **Extractors** | Pull values from text | Regex pattern to find DTI |

---

## Ontology Structure

### Required Fields

```json
{
  "name": "ontology-name",
  "version": "1.0.0",
  "description": "What this ontology verifies",
  "constraints": [...],
  "extractors": {...}
}
```

### Complete Schema

```json
{
  "name": "string (required)",
  "version": "string (required, semver)",
  "description": "string (required)",
  "constraints": [
    {
      "id": "string (required, unique)",
      "category": "string (optional, for grouping)",
      "description": "string (required)",
      "formula_readable": "string (optional, human-readable)",
      "formula": "object (required, JSON formula)",
      "variables": [
        {
          "name": "string (required)",
          "type": "bool | int | real (required)"
        }
      ],
      "error_message": "string (required)",
      "citation": "string (optional, regulation reference)"
    }
  ],
  "extractors": {
    "variable_name": {
      "type": "string (required)",
      "pattern": "string (regex, optional)",
      "keywords": ["array", "optional"],
      "...": "other type-specific options"
    }
  }
}
```

---

## Writing Constraints

### Anatomy of a Constraint

```json
{
  "id": "UNIQUE_IDENTIFIER",
  "category": "Category Name",
  "description": "Human-readable explanation",
  "formula_readable": "x <= 100",
  "formula": {"<=": ["x", 100]},
  "variables": [
    {"name": "x", "type": "int"}
  ],
  "error_message": "Shown when constraint fails",
  "citation": "Regulation or policy reference"
}
```

### Variable Types

| Type | Z3 Type | Use For | Example Values |
|------|---------|---------|----------------|
| `bool` | `Bool` | True/false flags | `true`, `false` |
| `int` | `Int` | Whole numbers | `600`, `100000` |
| `real` | `Real` | Decimal numbers | `43.5`, `0.05` |

### Simple Constraints

**Numeric comparison:**
```json
{
  "id": "MIN_CREDIT_SCORE",
  "formula": {">=": ["credit_score", 600]},
  "variables": [{"name": "credit_score", "type": "int"}],
  "error_message": "Credit score below 600 minimum"
}
```

**Boolean check:**
```json
{
  "id": "EMPLOYMENT_REQUIRED",
  "formula": {"==": ["employment_verified", true]},
  "variables": [{"name": "employment_verified", "type": "bool"}],
  "error_message": "Employment verification required"
}
```

**Negative check (must be false):**
```json
{
  "id": "NO_GUARANTEES",
  "formula": {"==": ["has_guarantee", false]},
  "variables": [{"name": "has_guarantee", "type": "bool"}],
  "error_message": "Cannot use guarantee language"
}
```

### Compound Constraints

**AND - all conditions must be true:**
```json
{
  "formula": {
    "and": [
      {">=": ["credit_score", 600]},
      {"<=": ["dti", 43]}
    ]
  }
}
```

**OR - at least one condition must be true:**
```json
{
  "formula": {
    "or": [
      {"<=": ["dti", 43]},
      {">=": ["compensating_factors", 2]}
    ]
  }
}
```

**NOT - negate a condition:**
```json
{
  "formula": {
    "not": {"==": ["is_interest_only", true]}
  }
}
```

### Conditional Constraints

**IMPLIES - if A then B:**
```json
{
  "id": "DENIAL_REASON_REQUIRED",
  "description": "If denied, must provide specific reason",
  "formula": {
    "implies": [
      {"==": ["is_denial", true]},
      {"==": ["has_specific_reason", true]}
    ]
  },
  "variables": [
    {"name": "is_denial", "type": "bool"},
    {"name": "has_specific_reason", "type": "bool"}
  ]
}
```

**IF-THEN-ELSE (ite):**
```json
{
  "formula": {
    "ite": [
      {"==": ["is_high_cost", true]},
      {"==": ["counseling_disclosed", true]},
      {"const": true}
    ]
  }
}
```

---

## Formula Syntax Reference

### Operators

| Category | Operators | Example |
|----------|-----------|---------|
| **Logical** | `and`, `or`, `not`, `implies`, `ite` | `{"and": [A, B]}` |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` | `{"<=": ["x", 100]}` |
| **Arithmetic** | `+`, `-`, `*`, `/`, `min`, `max` | `{"+": ["a", "b"]}` |
| **Constants** | `true`, `false`, numbers | `{"const": true}` |

### Logical Operators

```json
// AND - all must be true
{"and": [condition1, condition2, ...]}

// OR - at least one must be true
{"or": [condition1, condition2, ...]}

// NOT - negation
{"not": condition}

// IMPLIES - if A then B (A → B)
{"implies": [A, B]}

// ITE - if-then-else
{"ite": [condition, then_value, else_value]}
// Also accepted: {"if": [condition, then_value, else_value]}
```

### Comparison Operators

```json
{"==": ["variable", value]}   // equals
{"!=": ["variable", value]}   // not equals
{"<": ["variable", value]}    // less than
{"<=": ["variable", value]}   // less than or equal
{">": ["variable", value]}    // greater than
{">=": ["variable", value]}   // greater than or equal
```

### Arithmetic Operators

```json
{"+": ["a", "b"]}             // addition
{"-": ["a", "b"]}             // subtraction
{"*": ["a", "b"]}             // multiplication
{"/": ["a", "b"]}             // division
{"min": ["a", "b"]}           // minimum of two values
{"max": ["a", "b"]}           // maximum of two values
```

### Nesting Formulas

Formulas can be nested to any depth:

```json
{
  "formula": {
    "or": [
      {"<=": ["dti", 43]},
      {
        "and": [
          {"<=": ["dti", 50]},
          {">=": ["compensating_factors", 2]},
          {">=": ["credit_score", 720]}
        ]
      }
    ]
  }
}
```

---

## Writing Extractors

Extractors pull structured data from unstructured LLM output text.

### Extractor Types

| Type | Purpose | Key Options |
|------|---------|-------------|
| `int` | Integer extraction | `pattern` (regex) |
| `float` | Decimal extraction | `pattern` (regex) |
| `money` | Currency with k/m/b | `pattern` (regex) |
| `percentage` | Percentage values | `pattern` (regex) |
| `boolean` | True/false from keywords | `keywords`, `negation_words` |
| `string` | Text extraction | `pattern` (regex) |
| `date` | Date extraction | `pattern`, `keywords` |
| `datetime` | Date + time | `pattern` |
| `list` | Multiple values | `pattern`, `item_type` |
| `enum` | Predefined choices | `choices` |
| `computed` | Derived from other fields | `formula` |

### Numeric Extractors

**Integer:**
```json
"credit_score": {
  "type": "int",
  "pattern": "(?:credit\\s*(?:score)?|fico|score)\\s*(?:is|of|:)?\\s*(\\d{3})"
}
```

**Float:**
```json
"dti": {
  "type": "float",
  "pattern": "(?:debt-to-income|dti)(?:\\s*ratio)?\\s*(?:is|of|:)?\\s*([\\d.]+)\\s*%?"
}
```

**Money (handles k/m/b suffixes):**
```json
"loan_amount": {
  "type": "money",
  "pattern": "\\$([\\d,]+)(?:k|K|m|M)?"
}
```
- `$500k` → 500000
- `$1.5m` → 1500000

### Boolean Extractors

**Keyword-based:**
```json
"employment_verified": {
  "type": "boolean",
  "keywords": ["employed", "software engineer", "income verified", "employment confirmed"]
}
```

**With negation handling:**
```json
"has_documentation": {
  "type": "boolean",
  "keywords": ["documentation", "paperwork", "documents", "documented"],
  "negation_words": ["no paperwork", "no documentation", "without documentation"],
  "check_negation": true
}
```

### Enum Extractors

```json
"decision": {
  "type": "enum",
  "choices": {
    "approved": ["approved", "accepted", "granted", "recommend approval"],
    "denied": ["denied", "rejected", "declined", "cannot approve"],
    "pending": ["pending", "under review", "needs more info"]
  },
  "default": "pending"
}
```

### Date Extractors

```json
"application_date": {
  "type": "date",
  "keywords": ["applied on", "application date", "submitted"]
}
```

Supported formats:
- ISO: `2024-12-25`, `2024/12/25`
- US: `12/25/2024`, `12-25-2024`
- Written: `December 25, 2024`, `25 Dec 2024`

### List Extractors

```json
"violations_found": {
  "type": "list",
  "pattern": "violation:\\s*([^,\\n]+)",
  "item_type": "string"
}
```

### Computed Extractors

Derive values from other extracted fields:

```json
"phi_count": {
  "type": "computed",
  "formula": {
    "count_true": ["has_ssn", "has_dob", "has_mrn", "has_phone", "has_email"]
  }
}
```

**Supported computed formulas:**
- `count_true` - Count true booleans
- `count_fields` - Count non-null fields
- `sum` - Sum numeric fields
- `any` - True if any is true
- `all` - True if all are true
- `gt`, `gte`, `lt`, `lte` - Comparisons
- `add`, `mul` - Arithmetic
- `if` - Conditional
- `not`, `and`, `or` - Logical

### Regex Pattern Tips

1. **Use capture groups** - The first `()` group is extracted:
   ```json
   "pattern": "score\\s*(?:is|:)?\\s*(\\d{3})"
   ```

2. **Case insensitive** - Patterns are automatically case-insensitive

3. **Optional parts** - Use `(?:...)?` for optional matches:
   ```json
   "pattern": "(?:credit\\s*)?score\\s*(?:is)?\\s*(\\d{3})"
   ```

4. **Multiple keywords** - Use `|` for alternatives in the pattern:
   ```json
   "pattern": "(?:dti|debt-to-income|d\\/i)\\s*:?\\s*([\\d.]+)"
   ```

---

## Testing Your Rules

### CLI Testing

```bash
# Test against a string
aare-verify "Credit score is 720, DTI 35%" --ontology my-ontology

# Test against a file
aare-verify --file response.txt --ontology my-ontology

# List available ontologies
aare-ontologies
```

### HTTP API Testing

```bash
curl -X POST http://localhost:8080/verify \
  -H "Content-Type: application/json" \
  -d '{
    "llm_output": "Approved for $75,000. Credit score: 720, DTI: 35%",
    "ontology": "my-ontology"
  }'
```

### Understanding Results

**Successful verification:**
```json
{
  "verified": true,
  "violations": [],
  "parsed_data": {
    "loan_amount": 75000,
    "credit_score": 720,
    "dti": 35
  },
  "proof": {
    "method": "Z3 SMT Solver",
    "version": "4.12.1"
  },
  "verification_id": "a3d8c1f2-5b7e-4a9d-8c6f-1e2b3a4d5c6e",
  "execution_time_ms": 12
}
```

**Failed verification:**
```json
{
  "verified": false,
  "violations": [
    {
      "constraint_id": "MAX_DTI",
      "error_message": "DTI exceeds 43% maximum",
      "formula": {"<=": ["dti", 43]},
      "citation": "12 CFR § 1026.43(c)"
    }
  ],
  "parsed_data": {
    "dti": 48
  }
}
```

### Checking Warnings

If a variable wasn't found in the text, it appears in warnings:
```json
{
  "warnings": ["Variables defaulted (not found in input): ['down_payment']"]
}
```

---

## Best Practices

### Naming Conventions

- **Ontology name**: `domain-purpose-v1` (e.g., `fair-lending-v1`)
- **Constraint IDs**: `CATEGORY_DESCRIPTION` (e.g., `ATR_QM_DTI`)
- **Variable names**: `snake_case` (e.g., `credit_score`)

### Constraint Design

1. **One rule per constraint** - Keep constraints atomic
2. **Clear error messages** - User should understand what failed
3. **Include citations** - Reference regulations or policies
4. **Use categories** - Group related constraints

### Extractor Design

1. **Test with variations** - LLMs phrase things differently
2. **Handle common formats** - Credit score: 720, FICO 720, score of 720
3. **Use negation carefully** - Only when needed for boolean accuracy
4. **Provide defaults for optionals** - Use computed fields for derived values

### Performance Tips

- Keep formulas shallow when possible (fewer nested levels)
- Limit ontologies to ~50 constraints for best performance
- Use specific regex patterns rather than greedy ones

---

## Complete Examples

### Fair Lending Ontology

```json
{
  "name": "fair-lending-v1",
  "version": "1.0.0",
  "description": "Fair lending and loan approval compliance",
  "constraints": [
    {
      "id": "LOAN_AMOUNT_LIMIT",
      "category": "Approval Authority",
      "description": "Maximum loan amount without additional approval",
      "formula_readable": "loan_amount <= 100000",
      "formula": {"<=": ["loan_amount", 100000]},
      "variables": [{"name": "loan_amount", "type": "int"}],
      "error_message": "Loan amount exceeds $100k threshold - requires additional approval",
      "citation": "Lending Policy"
    },
    {
      "id": "MIN_CREDIT_SCORE",
      "category": "Creditworthiness",
      "description": "Minimum credit score requirement",
      "formula_readable": "credit_score >= 600",
      "formula": {">=": ["credit_score", 600]},
      "variables": [{"name": "credit_score", "type": "int"}],
      "error_message": "Credit score below 600 minimum",
      "citation": "Underwriting Guidelines"
    },
    {
      "id": "MAX_DTI",
      "category": "Debt Capacity",
      "description": "Maximum debt-to-income ratio",
      "formula_readable": "dti <= 43",
      "formula": {"<=": ["dti", 43]},
      "variables": [{"name": "dti", "type": "real"}],
      "error_message": "DTI exceeds 43% maximum",
      "citation": "12 CFR § 1026.43(c)"
    },
    {
      "id": "DOWN_PAYMENT",
      "category": "Equity",
      "description": "Minimum down payment requirement",
      "formula": {
        "or": [
          {"==": ["has_down_payment", false]},
          {">=": ["down_payment", 5]}
        ]
      },
      "variables": [
        {"name": "has_down_payment", "type": "bool"},
        {"name": "down_payment", "type": "real"}
      ],
      "error_message": "Down payment below 5% minimum",
      "citation": "Lending Policy"
    },
    {
      "id": "EMPLOYMENT_VERIFICATION",
      "category": "Income",
      "description": "Employment must be verified",
      "formula": {"==": ["employment_verified", true]},
      "variables": [{"name": "employment_verified", "type": "bool"}],
      "error_message": "Employment verification required",
      "citation": "Underwriting Standards"
    }
  ],
  "extractors": {
    "loan_amount": {
      "type": "int",
      "pattern": "\\$([\\d,]+)(?:k|K)?"
    },
    "credit_score": {
      "type": "int",
      "pattern": "(?:credit\\s*(?:score)?|fico|score|cs=)\\s*(?:is|of|:)?\\s*(\\d{3})"
    },
    "dti": {
      "type": "float",
      "pattern": "(?:debt-to-income|dti)(?:\\s*ratio)?\\s*(?:is|of|:)?\\s*(?:calculated\\s+at\\s+)?([\\d.]+)\\s*%?"
    },
    "down_payment": {
      "type": "float",
      "pattern": "(?:down payment|dp)(?:[:\\s]+|\\s+of\\s+)(\\d+(?:\\.\\d+)?)%?"
    },
    "has_down_payment": {
      "type": "boolean",
      "keywords": ["down payment", "down-payment", "downpayment"]
    },
    "employment_verified": {
      "type": "boolean",
      "keywords": ["employed", "software engineer", "income", "verified", "meets all criteria"]
    }
  }
}
```

### Content Policy Ontology

```json
{
  "name": "content-policy-v1",
  "version": "1.0.0",
  "description": "Content moderation guardrails",
  "constraints": [
    {
      "id": "NO_REAL_PEOPLE",
      "category": "Privacy",
      "description": "Cannot make claims about real people",
      "formula": {"==": ["mentions_real_person", false]},
      "variables": [{"name": "mentions_real_person", "type": "bool"}],
      "error_message": "Cannot make claims about identified individuals"
    },
    {
      "id": "NO_MEDICAL_ADVICE",
      "category": "Safety",
      "description": "Cannot provide medical diagnoses or treatment",
      "formula": {"==": ["gives_medical_advice", false]},
      "variables": [{"name": "gives_medical_advice", "type": "bool"}],
      "error_message": "Cannot provide medical advice - recommend consulting healthcare provider"
    },
    {
      "id": "DISCLAIMER_REQUIRED",
      "category": "Compliance",
      "description": "Must include appropriate disclaimers",
      "formula": {
        "implies": [
          {"==": ["discusses_financial_topics", true]},
          {"==": ["has_disclaimer", true]}
        ]
      },
      "variables": [
        {"name": "discusses_financial_topics", "type": "bool"},
        {"name": "has_disclaimer", "type": "bool"}
      ],
      "error_message": "Financial discussions require disclaimer"
    }
  ],
  "extractors": {
    "mentions_real_person": {
      "type": "boolean",
      "keywords": ["is guilty", "committed crime", "is responsible for"],
      "pattern": "(?:Mr\\.|Mrs\\.|Dr\\.|President)\\s+[A-Z][a-z]+\\s+(?:is|was|has)"
    },
    "gives_medical_advice": {
      "type": "boolean",
      "keywords": ["you should take", "prescribe", "diagnosis is", "treatment plan"]
    },
    "discusses_financial_topics": {
      "type": "boolean",
      "keywords": ["invest", "stock", "bond", "portfolio", "retirement", "401k"]
    },
    "has_disclaimer": {
      "type": "boolean",
      "keywords": ["not financial advice", "consult a professional", "for informational purposes"]
    }
  }
}
```

---

## Troubleshooting

### Common Issues

#### "Variable not found in input"

**Problem:** Extractor couldn't find the value in the text.

**Solutions:**
1. Check your regex pattern matches the actual text
2. Add more keyword variations
3. Test the pattern against sample text

#### "Formula validation error"

**Problem:** Invalid formula structure.

**Check:**
- Operators are spelled correctly
- Arrays have correct number of elements (binary ops need 2)
- Variable names match between formula and variables array

#### "Unknown variable: X"

**Problem:** Variable in formula not declared.

**Fix:** Add the variable to the `variables` array:
```json
"variables": [{"name": "X", "type": "int"}]
```

#### Extraction Returning Wrong Value

**Debug steps:**
1. Check `parsed_data` in response to see extracted values
2. Test regex pattern in isolation
3. Add more specific patterns or context keywords

### Debugging Tips

1. **Use the API's parsed_data** - Shows exactly what was extracted
2. **Test incrementally** - Add one constraint at a time
3. **Check case sensitivity** - Patterns are case-insensitive by default
4. **Verify regex groups** - First capture group `()` is extracted

---

## Additional Resources

- [aare-core README](../README.md) - Full technical documentation
- [Bundled Ontologies](../src/aare_core/ontologies/) - Production examples
- [Z3 Documentation](https://microsoft.github.io/z3guide/) - Z3 theorem prover

---

## Support

- GitHub Issues: [github.com/aare-ai](https://github.com/aare-ai)
- Email: info@aare.ai
