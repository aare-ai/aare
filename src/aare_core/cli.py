"""
aare-core CLI - Command-line interface for LLM compliance verification

Usage:
    aare-verify --input "text" --ontology mortgage-compliance-v1
    aare-verify --file output.txt --ontology hipaa-v1
    aare-ontologies  # List available ontologies
    aare-serve       # Start HTTP server (requires flask)
"""
import argparse
import json
import sys
import uuid
from datetime import datetime

from .ontology_loader import OntologyLoader
from .llm_parser import LLMParser
from .smt_verifier import SMTVerifier


def verify_cli():
    """CLI entry point for verification"""
    parser = argparse.ArgumentParser(
        description="Verify LLM output against compliance constraints using Z3 SMT solver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aare-verify --input "DTI is 35%, credit score 720" --ontology mortgage-compliance-v1
  aare-verify --file response.txt --ontology hipaa-v1
  aare-verify --input "..." --ontology ./custom-rules.json
  echo "text" | aare-verify --ontology fair-lending-v1
        """
    )
    parser.add_argument(
        "--input", "-i",
        help="LLM output text to verify"
    )
    parser.add_argument(
        "--file", "-f",
        help="File containing LLM output to verify"
    )
    parser.add_argument(
        "--ontology", "-o",
        default="example",
        help="Ontology name (bundled) or path to JSON file (default: example)"
    )
    parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="Output compact human-readable summary instead of JSON"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output pass/fail exit code"
    )

    args = parser.parse_args()

    # Get input text
    if args.input:
        llm_output = args.input
    elif args.file:
        try:
            with open(args.file, "r") as f:
                llm_output = f.read()
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(2)
        except PermissionError:
            print(f"Error: Permission denied reading file: {args.file}", file=sys.stderr)
            sys.exit(2)
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(2)
    elif not sys.stdin.isatty():
        llm_output = sys.stdin.read()
    else:
        parser.print_help()
        print("\nError: No input provided. Use --input, --file, or pipe text.", file=sys.stderr)
        sys.exit(2)

    # Load ontology
    loader = OntologyLoader()

    # Check if ontology is a file path
    if args.ontology.endswith(".json"):
        try:
            with open(args.ontology, "r") as f:
                ontology = json.load(f)
        except FileNotFoundError:
            print(f"Error: Ontology file not found: {args.ontology}", file=sys.stderr)
            sys.exit(2)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in ontology file: {e}", file=sys.stderr)
            sys.exit(2)
        except OSError as e:
            print(f"Error loading ontology file: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        ontology = loader.load(args.ontology)

    # Parse and verify
    llm_parser = LLMParser()
    verifier = SMTVerifier()

    extracted_data = llm_parser.parse(llm_output, ontology)
    result = verifier.verify(extracted_data, ontology)

    # Output
    if args.quiet:
        sys.exit(0 if result["verified"] else 1)

    if args.compact:
        # Compact human-readable output
        if result["verified"]:
            print(f"✓ VERIFIED - All {len(ontology['constraints'])} constraints passed")
            print(f"  Ontology: {ontology['name']} v{ontology['version']}")
        else:
            print(f"✗ FAILED - {len(result['violations'])} violation(s)")
            print(f"  Ontology: {ontology['name']} v{ontology['version']}")
            print()
            for v in result["violations"]:
                print(f"  [{v['constraint_id']}] {v['error_message']}")
                if v.get("citation"):
                    print(f"    Citation: {v['citation']}")
    else:
        # Full JSON output (default)
        output = {
            "verified": result["verified"],
            "violations": result["violations"],
            "parsed_data": extracted_data,
            "ontology": {
                "name": ontology["name"],
                "version": ontology["version"],
                "constraints_checked": len(ontology["constraints"])
            },
            "proof": result["proof"],
            "verification_id": str(uuid.uuid4()),
            "execution_time_ms": result["execution_time_ms"],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        print(json.dumps(output, indent=2))

    sys.exit(0 if result["verified"] else 1)


def list_ontologies_cli():
    """CLI entry point to list available ontologies"""
    parser = argparse.ArgumentParser(
        description="List available ontologies for aare-verify"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    loader = OntologyLoader()
    ontologies = loader.list_available()

    if args.json:
        print(json.dumps({"ontologies": ontologies}, indent=2))
    else:
        print("Available ontologies:")
        print()
        for name in ontologies:
            onto = loader.load(name)
            desc = onto.get("description", "")[:60]
            constraints = len(onto.get("constraints", []))
            print(f"  {name:<30} ({constraints} constraints)")
            if desc:
                print(f"    {desc}")


def serve_cli():
    """CLI entry point to start HTTP server"""
    try:
        from flask import Flask
    except ImportError:
        print("Error: Flask not installed. Install with:", file=sys.stderr)
        print('  pip install "aare-core[server]"', file=sys.stderr)
        print("  # or", file=sys.stderr)
        print("  pip install flask gunicorn", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Start aare.ai verification HTTP server"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)"
    )
    parser.add_argument(
        "--host", "-H",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug mode"
    )

    args = parser.parse_args()

    # Import and run server
    from .server import create_app
    app = create_app()

    print(f"Starting aare.ai verification server on http://{args.host}:{args.port}")
    print("Endpoints:")
    print("  POST /verify  - Verify LLM output")
    print("  GET  /ontologies - List ontologies")
    print("  GET  /health  - Health check")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    verify_cli()
