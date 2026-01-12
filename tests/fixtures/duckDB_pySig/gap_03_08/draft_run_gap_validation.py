#!/usr/bin/env python3
"""
run_gap_validation.py - Execute GAP-03 and GAP-08 validation fixtures

Usage:
    python run_gap_validation.py [--verbose]

Requirements:
    pip install duckdb

This script:
1. Creates an in-memory DuckDB database
2. Loads the schema and sample data
3. Runs all validation queries
4. Reports pass/fail status for each test
"""

import argparse
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("ERROR: duckdb not installed. Run: pip install duckdb")
    sys.exit(1)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gap_03_08"


def load_sql_file(path: Path) -> str:
    """Load SQL from file."""
    return path.read_text()


def extract_tests(sql: str) -> list[tuple[str, str]]:
    """Extract individual tests from SQL file.
    
    Tests are delimited by lines starting with '-- TEST N:' 
    and end at the next test or end of file.
    """
    tests = []
    current_name = None
    current_sql = []
    
    for line in sql.split('\n'):
        if line.startswith('-- TEST '):
            if current_name:
                tests.append((current_name, '\n'.join(current_sql)))
            # Extract test name from "-- TEST N: description"
            current_name = line[3:].strip()
            current_sql = []
        elif current_name:
            # Skip comment lines that are part of expected results
            if not line.startswith('--'):
                current_sql.append(line)
    
    if current_name:
        tests.append((current_name, '\n'.join(current_sql)))
    
    return tests


def run_test(conn: duckdb.DuckDBPyConnection, name: str, sql: str, verbose: bool) -> bool:
    """Run a single test query and return success status."""
    # Clean up SQL (remove empty lines, get actual query)
    lines = [l.strip() for l in sql.strip().split('\n') if l.strip() and not l.strip().startswith('--')]
    if not lines:
        return True  # Empty test (comment-only section)
    
    query = '\n'.join(lines)
    
    try:
        result = conn.execute(query).fetchall()
        if verbose:
            print(f"  ✓ {name}")
            print(f"    Returned {len(result)} rows")
            if len(result) <= 5:
                for row in result:
                    print(f"      {row}")
            else:
                for row in result[:3]:
                    print(f"      {row}")
                print(f"      ... ({len(result) - 3} more rows)")
        else:
            print(f"  ✓ {name} ({len(result)} rows)")
        return True
    except Exception as e:
        print(f"  ✗ {name}")
        print(f"    ERROR: {e}")
        if verbose:
            print(f"    Query: {query[:200]}...")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run GAP-03/08 validation fixtures")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()
    
    # Check fixture files exist
    schema_file = FIXTURE_DIR / "schema.sql"
    data_file = FIXTURE_DIR / "data.sql"
    gap03_file = FIXTURE_DIR / "validate_gap_03.sql"
    gap08_file = FIXTURE_DIR / "validate_gap_08.sql"
    
    for f in [schema_file, data_file, gap03_file, gap08_file]:
        if not f.exists():
            print(f"ERROR: Missing fixture file: {f}")
            sys.exit(1)
    
    # Create in-memory database
    print("Creating in-memory DuckDB database...")
    conn = duckdb.connect(":memory:")
    
    # Load schema
    print("Loading schema...")
    conn.execute(load_sql_file(schema_file))
    
    # Load data
    print("Loading sample data...")
    conn.execute(load_sql_file(data_file))
    
    # Verify data loaded
    count = conn.execute("SELECT COUNT(*) FROM ocsf_events").fetchone()[0]
    print(f"Loaded {count} test records\n")
    
    # Run GAP-03 tests
    print("=" * 60)
    print("GAP-03: Nested Field Access Validation")
    print("=" * 60)
    gap03_sql = load_sql_file(gap03_file)
    gap03_tests = extract_tests(gap03_sql)
    gap03_passed = 0
    gap03_failed = 0
    
    for name, sql in gap03_tests:
        if run_test(conn, name, sql, args.verbose):
            gap03_passed += 1
        else:
            gap03_failed += 1
    
    print(f"\nGAP-03 Results: {gap03_passed} passed, {gap03_failed} failed\n")
    
    # Run GAP-08 tests
    print("=" * 60)
    print("GAP-08: Timestamp Typing Validation")
    print("=" * 60)
    gap08_sql = load_sql_file(gap08_file)
    gap08_tests = extract_tests(gap08_sql)
    gap08_passed = 0
    gap08_failed = 0
    
    for name, sql in gap08_tests:
        if run_test(conn, name, sql, args.verbose):
            gap08_passed += 1
        else:
            gap08_failed += 1
    
    print(f"\nGAP-08 Results: {gap08_passed} passed, {gap08_failed} failed\n")
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_passed = gap03_passed + gap08_passed
    total_failed = gap03_failed + gap08_failed
    print(f"Total: {total_passed} passed, {total_failed} failed")
    
    if total_failed > 0:
        print("\n⚠️  Some tests failed. Review output above.")
        sys.exit(1)
    else:
        print("\n✓ All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()