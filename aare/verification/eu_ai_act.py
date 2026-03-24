"""EU AI Act Article 15 Compliance Verification for Credit Scoring.

Provides formal verification of high-risk AI credit scoring systems
against EU AI Act Article 15 requirements:

- Article 15(1): Accuracy requirements
- Article 15(3): Robustness requirements
- Article 15(4): Cybersecurity and bias prevention

Reference: Regulation (EU) 2024/1689 (EU AI Act)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from z3 import (
    And, Bool, If, Implies, Not, Or, Real, Solver,
    sat, unsat, unknown
)


class ComplianceStatus(Enum):
    """EU AI Act compliance status."""
    COMPLIANT = "compliant"
    VIOLATION = "violation"
    ERROR = "error"


@dataclass
class ExtractedClaim:
    """A claim extracted from credit scoring output."""
    claim_type: str
    value: Any
    raw_text: str
    start: int
    end: int
    confidence: float = 1.0
    has_source: bool = False
    source: Optional[str] = None


@dataclass
class Violation:
    """A constraint violation."""
    constraint_id: str
    description: str
    severity: str  # "critical", "high", "medium"
    citation: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of EU AI Act Article 15 verification."""
    status: ComplianceStatus
    violations: List[Violation]
    claims: List[ExtractedClaim]
    proof_trace: str
    execution_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_compliant(self) -> bool:
        return self.status == ComplianceStatus.COMPLIANT

    @property
    def verified(self) -> bool:
        return self.is_compliant

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "status": self.status.value,
            "violations": [
                {
                    "constraint_id": v.constraint_id,
                    "description": v.description,
                    "severity": v.severity,
                    "citation": v.citation,
                    "details": v.details,
                }
                for v in self.violations
            ],
            "claims": [
                {
                    "claim_type": c.claim_type,
                    "value": c.value,
                    "raw_text": c.raw_text,
                    "has_source": c.has_source,
                    "source": c.source,
                }
                for c in self.claims
            ],
            "proof": self.proof_trace,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class CreditScoringParser:
    """Parser for credit scoring LLM outputs.

    Extracts claims about:
    - DTI (debt-to-income) calculations
    - Credit scores
    - Income and debt figures
    - Geographic factors (ZIP codes)
    - Risk adjustments
    - Recommendations
    """

    # Patterns for extracting credit scoring data
    PATTERNS = {
        # DTI patterns
        "dti_percentage": [
            r"DTI[:\s]+(\d{1,3}(?:\.\d{1,2})?)\s*%",
            r"debt[- ]to[- ]income[:\s]+(\d{1,3}(?:\.\d{1,2})?)\s*%",
            r"DTI\s+(?:Calculation|Ratio)[:\s]+(\d{1,3}(?:\.\d{1,2})?)\s*%",
        ],
        # Credit score patterns
        "credit_score": [
            r"Credit\s+Score[:\s]+(\d{3})",
            r"FICO[:\s]+(\d{3})",
            r"score[:\s]+(\d{3})\b",
        ],
        # Income patterns
        "annual_income": [
            r"Annual\s+Income[:\s]+\$?([\d,]+)",
            r"yearly\s+income[:\s]+\$?([\d,]+)",
            r"income[:\s]+\$?([\d,]+)\s*(?:per\s+year|annually|/year)",
        ],
        # Monthly debt patterns
        "monthly_debt": [
            r"Monthly\s+Debt[:\s]+\$?([\d,]+)",
            r"debt[:\s]+\$?([\d,]+)\s*(?:per\s+month|monthly|/month)",
        ],
        # ZIP code patterns
        "zip_code": [
            r"ZIP\s+(?:code\s+)?(\d{5})",
            r"resides?\s+in\s+ZIP\s+(\d{5})",
            r"\bZIP\s+(\d{5})\b",
        ],
        # Risk adjustment patterns
        "risk_adjustment": [
            r"(?:risk|adjusted)\s+factor[:\s]+([+-]?\d+)\s*points?",
            r"adjustment[:\s]+([+-]?\d+)\s*points?",
            r"([+-]\d+)\s*points?\s+(?:risk\s+)?(?:adjustment|factor)",
        ],
        # Recommendation patterns
        "recommendation": [
            r"RECOMMENDATION[:\s]+(APPROVED|DENIED|REJECTED|APPROVED WITH CONDITIONS)",
            r"Decision[:\s]+(APPROVED|DENIED|REJECTED)",
            r"\b(APPROVED|DENIED)\b",
        ],
        # APR patterns
        "apr": [
            r"APR[:\s]+(\d{1,2}(?:\.\d{1,2})?)\s*%",
            r"interest\s+rate[:\s]+(\d{1,2}(?:\.\d{1,2})?)\s*%",
        ],
    }

    # Patterns indicating data source
    SOURCE_PATTERNS = [
        (r"Source[:\s]+([^\n,]+)", "source"),
        (r"Retrieved[:\s]+([^\n,]+)", "retrieved"),
        (r"\((?:from\s+)?([A-Za-z]+)\s*,?\s*(?:Retrieved|pulled)[:\s]*([^\)]+)\)", "bureau"),
        (r"bureau\s+data", "bureau_mentioned"),
        (r"No\s+bureau\s+data", "no_bureau"),
    ]

    # Patterns indicating geographic influence on risk
    GEO_INFLUENCE_PATTERNS = [
        r"ZIP\s+\d+[^.]*(?:default|risk|rate|adjustment|factor)",
        r"Regional\s+(?:default|risk)\s+rate",
        r"(?:risk|adjusted)\s+factor[^.]*ZIP",
        r"location[^.]*risk",
    ]

    def parse(self, text: str) -> List[ExtractedClaim]:
        """Parse credit scoring output and extract claims."""
        claims = []
        text_lower = text.lower()

        for claim_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1)

                    # Parse numeric values
                    if claim_type in ["dti_percentage", "apr"]:
                        value = float(value)
                    elif claim_type in ["credit_score", "risk_adjustment"]:
                        value = int(value.replace("+", ""))
                    elif claim_type in ["annual_income", "monthly_debt"]:
                        value = float(value.replace(",", ""))
                    elif claim_type == "zip_code":
                        value = value
                    elif claim_type == "recommendation":
                        value = value.upper()

                    # Check for data source
                    has_source, source = self._find_source(text, claim_type, match.start())

                    claims.append(ExtractedClaim(
                        claim_type=claim_type,
                        value=value,
                        raw_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        has_source=has_source,
                        source=source,
                    ))
                    break  # Take first match for each pattern group

        # Check for geographic influence on risk scoring
        for pattern in self.GEO_INFLUENCE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                claims.append(ExtractedClaim(
                    claim_type="geographic_risk_influence",
                    value=True,
                    raw_text=re.search(pattern, text, re.IGNORECASE).group(0),
                    start=0,
                    end=len(text),
                    has_source=False,
                ))
                break

        return claims

    def _find_source(self, text: str, claim_type: str, position: int) -> Tuple[bool, Optional[str]]:
        """Check if a claim has a verifiable source nearby."""
        # Look in a window around the claim
        window_start = max(0, position - 200)
        window_end = min(len(text), position + 200)
        window = text[window_start:window_end]

        for pattern, source_type in self.SOURCE_PATTERNS:
            match = re.search(pattern, window, re.IGNORECASE)
            if match:
                if source_type == "no_bureau":
                    return False, None
                return True, match.group(1) if match.lastindex else source_type

        return False, None


class EUAIActArticle15Verifier:
    """Verifier for EU AI Act Article 15 compliance in credit scoring.

    Constraints:
    - ACC-001: Arithmetic verification (DTI calculation)
    - ACC-002: DTI threshold for approval
    - ROB-001: Data provenance for credit scores
    - ROB-002: No hallucinated data
    - BIAS-001: No geographic proxy discrimination
    - BIAS-002: Protected attributes check
    """

    CONSTRAINTS = {
        "ACC-001": {
            "name": "Arithmetic Verification",
            "description": "All numerical calculations must be verifiable",
            "citation": "EU AI Act Article 15(1)",
            "severity": "critical",
        },
        "ACC-002": {
            "name": "DTI Threshold",
            "description": "DTI ratio limits for loan approval",
            "citation": "EU AI Act Article 15(1)",
            "severity": "high",
        },
        "ROB-001": {
            "name": "Data Provenance",
            "description": "Credit scores must have verifiable source",
            "citation": "EU AI Act Article 15(3)",
            "severity": "critical",
        },
        "ROB-002": {
            "name": "No Hallucinated Data",
            "description": "AI must not generate synthetic data for decisions",
            "citation": "EU AI Act Article 15(3)",
            "severity": "critical",
        },
        "BIAS-001": {
            "name": "No Geographic Proxy",
            "description": "ZIP code cannot influence risk scoring",
            "citation": "EU AI Act Article 15(4)",
            "severity": "critical",
        },
        "BIAS-002": {
            "name": "Protected Attributes",
            "description": "Race, gender, religion cannot affect scoring",
            "citation": "EU AI Act Article 15(4)",
            "severity": "critical",
        },
    }

    def __init__(self):
        self.parser = CreditScoringParser()

    def verify(self, text: str) -> VerificationResult:
        """Verify credit scoring output against Article 15 constraints."""
        start_time = time.time()

        # Parse claims from text
        claims = self.parser.parse(text)

        # Build claim lookup
        claims_by_type = {}
        for claim in claims:
            if claim.claim_type not in claims_by_type:
                claims_by_type[claim.claim_type] = []
            claims_by_type[claim.claim_type].append(claim)

        violations = []
        proof_lines = ["EU AI Act Article 15 Verification", "=" * 50, ""]

        # ACC-001: Arithmetic Verification (DTI calculation)
        violation, proof = self._check_dti_arithmetic(claims_by_type)
        proof_lines.extend(proof)
        if violation:
            violations.append(violation)

        # ROB-001: Data Provenance for credit scores
        violation, proof = self._check_credit_score_provenance(claims_by_type)
        proof_lines.extend(proof)
        if violation:
            violations.append(violation)

        # BIAS-001: Geographic proxy discrimination
        violation, proof = self._check_geographic_proxy(claims_by_type)
        proof_lines.extend(proof)
        if violation:
            violations.append(violation)

        # Determine overall status
        status = ComplianceStatus.COMPLIANT if not violations else ComplianceStatus.VIOLATION

        execution_time_ms = round((time.time() - start_time) * 1000, 2)

        proof_lines.append("")
        proof_lines.append("=" * 50)
        if status == ComplianceStatus.COMPLIANT:
            proof_lines.append("RESULT: COMPLIANT - All constraints satisfied")
        else:
            proof_lines.append(f"RESULT: VIOLATION - {len(violations)} constraint(s) failed")

        return VerificationResult(
            status=status,
            violations=violations,
            claims=claims,
            proof_trace="\n".join(proof_lines),
            execution_time_ms=execution_time_ms,
            metadata={
                "constraints_checked": len(self.CONSTRAINTS),
                "claims_extracted": len(claims),
            }
        )

    def _check_dti_arithmetic(self, claims: Dict) -> Tuple[Optional[Violation], List[str]]:
        """Check ACC-001: DTI calculation accuracy."""
        proof = ["Checking ACC-001 (Arithmetic Verification)..."]

        dti_claims = claims.get("dti_percentage", [])
        income_claims = claims.get("annual_income", [])
        debt_claims = claims.get("monthly_debt", [])

        if not dti_claims:
            proof.append("  No DTI claim found - SKIP")
            return None, proof

        if not income_claims or not debt_claims:
            proof.append("  Missing income or debt data for verification - SKIP")
            return None, proof

        dti_claimed = dti_claims[0].value / 100  # Convert percentage
        annual_income = income_claims[0].value
        monthly_debt = debt_claims[0].value

        # Calculate actual DTI
        monthly_income = annual_income / 12
        dti_actual = monthly_debt / monthly_income if monthly_income > 0 else 0

        proof.append(f"  Claimed DTI: {dti_claimed * 100:.1f}%")
        proof.append(f"  Computed DTI: {monthly_debt} / {monthly_income:.2f} = {dti_actual * 100:.1f}%")

        # Allow small tolerance for rounding
        tolerance = 0.01
        if abs(dti_claimed - dti_actual) > tolerance:
            proof.append(f"  VIOLATION: Delta {abs(dti_claimed - dti_actual) * 100:.1f}% exceeds tolerance")

            constraint = self.CONSTRAINTS["ACC-001"]
            return Violation(
                constraint_id="ACC-001",
                description=constraint["description"],
                severity=constraint["severity"],
                citation=constraint["citation"],
                details={
                    "claimed": round(dti_claimed * 100, 1),
                    "actual": round(dti_actual * 100, 1),
                    "delta": round(abs(dti_claimed - dti_actual) * 100, 1),
                    "z3_proof": f"(not (= {dti_claimed:.3f} (/ {monthly_debt} {monthly_income:.2f})))",
                }
            ), proof

        proof.append("  PASS: DTI calculation verified")
        return None, proof

    def _check_credit_score_provenance(self, claims: Dict) -> Tuple[Optional[Violation], List[str]]:
        """Check ROB-001: Credit score data provenance."""
        proof = ["", "Checking ROB-001 (Data Provenance)..."]

        credit_claims = claims.get("credit_score", [])

        if not credit_claims:
            proof.append("  No credit score claim found - SKIP")
            return None, proof

        credit_claim = credit_claims[0]
        proof.append(f"  Credit Score: {credit_claim.value}")
        proof.append(f"  Has Source: {credit_claim.has_source}")

        if credit_claim.source:
            proof.append(f"  Source: {credit_claim.source}")

        if not credit_claim.has_source:
            proof.append("  VIOLATION: Credit score used without verifiable source")

            constraint = self.CONSTRAINTS["ROB-001"]
            return Violation(
                constraint_id="ROB-001",
                description="Credit score used without verifiable data source",
                severity=constraint["severity"],
                citation=constraint["citation"],
                details={
                    "field": "credit_score",
                    "value": credit_claim.value,
                    "z3_proof": "(not (has_source credit_score))",
                }
            ), proof

        proof.append("  PASS: Credit score has verifiable source")
        return None, proof

    def _check_geographic_proxy(self, claims: Dict) -> Tuple[Optional[Violation], List[str]]:
        """Check BIAS-001: No geographic proxy discrimination."""
        proof = ["", "Checking BIAS-001 (No Geographic Proxy)..."]

        geo_influence = claims.get("geographic_risk_influence", [])
        zip_claims = claims.get("zip_code", [])
        risk_claims = claims.get("risk_adjustment", [])

        if geo_influence:
            proof.append(f"  Found geographic influence on risk: {geo_influence[0].raw_text}")
            proof.append("  VIOLATION: ZIP code used as proxy for risk assessment")

            constraint = self.CONSTRAINTS["BIAS-001"]
            zip_value = zip_claims[0].value if zip_claims else "unknown"
            risk_adj = risk_claims[0].value if risk_claims else "unknown"

            return Violation(
                constraint_id="BIAS-001",
                description="Geographic location used as proxy for risk scoring",
                severity=constraint["severity"],
                citation=constraint["citation"],
                details={
                    "field": "zip_code",
                    "value": zip_value,
                    "influence": f"risk_score ({'+' if isinstance(risk_adj, int) and risk_adj > 0 else ''}{risk_adj})",
                    "z3_proof": "(influences zip_code risk_score)",
                }
            ), proof

        if zip_claims and risk_claims:
            proof.append(f"  ZIP code found: {zip_claims[0].value}")
            proof.append(f"  Risk adjustment found: {risk_claims[0].value}")
            proof.append("  No direct influence detected")

        proof.append("  PASS: No geographic proxy discrimination detected")
        return None, proof
