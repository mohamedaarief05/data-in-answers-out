"""
Test runner script for Member 3's deliverables.
Executes pytest on the test suite and outputs verification status
for TEST 1, TEST 2, TEST 3, TEST 4, and TEST 5.
"""
import sys
import pytest

if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING VERIFICATION TEST SUITE (TEST 1 - TEST 5)")
    print("=" * 70)
    exit_code = pytest.main(["-v", "loader/tests"])
    print("=" * 70)
    if exit_code == 0:
        print("ALL TESTS PASSED SUCCESSFULLY!")
        print("TEST 1: Kafka message reaches Loader -> VERIFIED")
        print("TEST 2: Loader creates Dataset and Row in Neo4j -> VERIFIED")
        print("TEST 3: Duplicate safety via MERGE & stable ID -> VERIFIED")
        print("TEST 4: Chatbot answers questions using Neo4j -> VERIFIED")
        print("TEST 5: Chatbot refuses when info is not in Neo4j -> VERIFIED")
    else:
        print(f"TESTS FAILED with exit code {exit_code}")
    print("=" * 70)
    sys.exit(exit_code)
