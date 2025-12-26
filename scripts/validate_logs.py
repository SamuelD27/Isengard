#!/usr/bin/env python3
"""
Isengard Log Validation Script

Validates log files against the logging specification:
- Schema compliance (required fields)
- JSON validity
- Timestamp format
- Level values
- Redaction (no secrets)
- Structure (latest/archive layout)

Usage:
    python scripts/validate_logs.py
    python scripts/validate_logs.py --service api
    python scripts/validate_logs.py --strict
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class ValidationResult(NamedTuple):
    """Result of validating a single log entry."""
    valid: bool
    warnings: list[str]
    errors: list[str]
    line_number: int
    raw_line: str


class LogValidator:
    """Validates log files against specification."""

    # Required fields per spec
    REQUIRED_FIELDS = {"timestamp", "level", "service", "logger", "message"}

    # Valid log levels
    VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    # Secret patterns that should be redacted
    SECRET_PATTERNS = [
        re.compile(r"hf_[A-Za-z0-9]{10,}"),  # HuggingFace tokens
        re.compile(r"sk-[A-Za-z0-9]{10,}"),  # OpenAI API keys
        re.compile(r"ghp_[A-Za-z0-9]{10,}"),  # GitHub tokens
        re.compile(r"rpa_[A-Za-z0-9]{10,}"),  # RunPod keys
        re.compile(r"/Users/[a-zA-Z0-9]+/"),  # macOS home paths (unredacted)
        re.compile(r"/home/[a-zA-Z0-9]+/"),  # Linux home paths (unredacted)
    ]

    # ISO 8601 timestamp pattern
    TIMESTAMP_PATTERN = re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$"
    )

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.stats = {
            "files_checked": 0,
            "entries_checked": 0,
            "entries_valid": 0,
            "entries_warning": 0,
            "entries_error": 0,
        }

    def validate_entry(self, line: str, line_number: int) -> ValidationResult:
        """Validate a single log entry."""
        warnings = []
        errors = []

        # Parse JSON
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                warnings=[],
                errors=[f"Invalid JSON: {e}"],
                line_number=line_number,
                raw_line=line[:100],
            )

        # Check required fields
        missing = self.REQUIRED_FIELDS - set(entry.keys())
        if missing:
            errors.append(f"Missing required fields: {missing}")

        # Validate timestamp format
        if "timestamp" in entry:
            ts = entry["timestamp"]
            if not self.TIMESTAMP_PATTERN.match(ts):
                warnings.append(f"Timestamp format may be non-standard: {ts}")
            else:
                # Try to parse it
                try:
                    # Handle both with and without milliseconds
                    ts_clean = ts.replace("Z", "+00:00")
                    if "." not in ts_clean:
                        ts_clean = ts_clean.replace("+00:00", ".000+00:00")
                    datetime.fromisoformat(ts_clean)
                except ValueError:
                    warnings.append(f"Timestamp not parseable: {ts}")

        # Validate level
        if "level" in entry:
            if entry["level"] not in self.VALID_LEVELS:
                errors.append(f"Invalid log level: {entry['level']}")

        # Check for unredacted secrets
        line_str = json.dumps(entry)
        for pattern in self.SECRET_PATTERNS:
            if pattern.search(line_str):
                errors.append(f"Potential unredacted secret found matching: {pattern.pattern}")

        # Check correlation_id format when present
        if "correlation_id" in entry:
            cid = entry["correlation_id"]
            if not (cid.startswith("req-") or cid.startswith("test-")):
                warnings.append(f"Correlation ID format unusual: {cid}")

        # Check event type when present
        if "event" in entry:
            event = entry["event"]
            if "." not in event:
                warnings.append(f"Event type should use dot notation: {event}")

        valid = len(errors) == 0
        if self.strict:
            valid = valid and len(warnings) == 0

        return ValidationResult(
            valid=valid,
            warnings=warnings,
            errors=errors,
            line_number=line_number,
            raw_line=line[:100],
        )

    def validate_file(self, file_path: Path) -> list[ValidationResult]:
        """Validate all entries in a log file."""
        results = []
        self.stats["files_checked"] += 1

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    self.stats["entries_checked"] += 1
                    result = self.validate_entry(line, line_number)
                    results.append(result)

                    if result.valid:
                        self.stats["entries_valid"] += 1
                    if result.warnings:
                        self.stats["entries_warning"] += 1
                    if result.errors:
                        self.stats["entries_error"] += 1

        except Exception as e:
            results.append(ValidationResult(
                valid=False,
                warnings=[],
                errors=[f"Failed to read file: {e}"],
                line_number=0,
                raw_line=str(file_path),
            ))

        return results

    def validate_directory_structure(self, log_dir: Path) -> list[str]:
        """Validate log directory structure."""
        issues = []

        if not log_dir.exists():
            issues.append(f"Log directory does not exist: {log_dir}")
            return issues

        # Check for expected service directories
        expected_services = ["api", "worker", "web"]
        found_services = []

        for service in expected_services:
            service_dir = log_dir / service
            if service_dir.exists():
                found_services.append(service)

                # Check for latest/archive structure
                latest_dir = service_dir / "latest"
                archive_dir = service_dir / "archive"

                if not latest_dir.exists():
                    issues.append(f"Missing latest/ directory for {service}")
                if not archive_dir.exists():
                    issues.append(f"Missing archive/ directory for {service}")

        if not found_services:
            issues.append("No service log directories found")

        return issues

    def print_results(self, results: list[ValidationResult], file_path: Path) -> None:
        """Print validation results for a file."""
        errors = [r for r in results if r.errors]
        warnings = [r for r in results if r.warnings and not r.errors]

        if errors:
            print(f"\n{file_path}:")
            for result in errors:
                print(f"  Line {result.line_number}: ERRORS")
                for error in result.errors:
                    print(f"    - {error}")

        if warnings and (self.strict or len(errors) == 0):
            if not errors:
                print(f"\n{file_path}:")
            for result in warnings:
                print(f"  Line {result.line_number}: WARNINGS")
                for warning in result.warnings:
                    print(f"    - {warning}")


def main():
    parser = argparse.ArgumentParser(description="Validate Isengard log files")
    parser.add_argument(
        "--service",
        choices=["api", "worker", "web"],
        help="Validate only specific service logs",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("./logs"),
        help="Log directory path (default: ./logs)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print summary, not individual issues",
    )

    args = parser.parse_args()

    validator = LogValidator(strict=args.strict)

    # Check directory structure
    print("Checking log directory structure...")
    structure_issues = validator.validate_directory_structure(args.log_dir)
    for issue in structure_issues:
        print(f"  ISSUE: {issue}")

    # Find log files to validate
    log_files = []
    services = [args.service] if args.service else ["api", "worker", "web"]

    for service in services:
        service_dir = args.log_dir / service
        if service_dir.exists():
            # Check latest
            latest_dir = service_dir / "latest"
            if latest_dir.exists():
                log_files.extend(latest_dir.glob("*.log"))

            # Check archive (sample only, not all)
            archive_dir = service_dir / "archive"
            if archive_dir.exists():
                for archive in sorted(archive_dir.iterdir())[-3:]:  # Last 3 archives
                    if archive.is_dir():
                        log_files.extend(archive.glob("*.log"))

    if not log_files:
        print("\nNo log files found to validate.")
        if not structure_issues:
            print("This may be expected if services haven't run yet.")
        sys.exit(0 if not structure_issues else 1)

    # Validate each file
    print(f"\nValidating {len(log_files)} log files...")
    all_results = []

    for log_file in log_files:
        results = validator.validate_file(log_file)
        all_results.extend(results)
        if not args.quiet:
            validator.print_results(results, log_file)

    # Print summary
    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Files checked:   {validator.stats['files_checked']}")
    print(f"Entries checked: {validator.stats['entries_checked']}")
    print(f"Entries valid:   {validator.stats['entries_valid']}")
    print(f"Entries warning: {validator.stats['entries_warning']}")
    print(f"Entries error:   {validator.stats['entries_error']}")
    print()

    # Determine exit code
    has_errors = validator.stats["entries_error"] > 0 or len(structure_issues) > 0
    has_warnings = validator.stats["entries_warning"] > 0

    if has_errors:
        print("RESULT: FAILED (errors found)")
        sys.exit(1)
    elif has_warnings and args.strict:
        print("RESULT: FAILED (warnings in strict mode)")
        sys.exit(1)
    elif has_warnings:
        print("RESULT: PASSED with warnings")
        sys.exit(0)
    else:
        print("RESULT: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
