#!/usr/bin/env bash

# RISE @ RST #5 - Member 2 API Automated Curl Verification Script
set -e

BASE_URL="http://localhost:8000"
SAMPLE_CSV="$(dirname "$0")/../sample.csv"

echo "=================================================="
echo "1. GET /health"
echo "=================================================="
curl -s -X GET "${BASE_URL}/health" | python3 -m json.tool || true
echo -e "\n"

echo "=================================================="
echo "2. POST /ingest (valid sample.csv)"
echo "=================================================="
INGEST_RESPONSE=$(curl -s -X POST "${BASE_URL}/ingest" -F "file=@${SAMPLE_CSV}")
echo "${INGEST_RESPONSE}" | python3 -m json.tool || true

JOB_ID=$(echo "${INGEST_RESPONSE}" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null || true)
echo -e "\nCaptured Job ID: ${JOB_ID}"
echo -e "\n"

echo "=================================================="
echo "3. GET /status?job_id=${JOB_ID}"
echo "=================================================="
if [ -n "${JOB_ID}" ]; then
  curl -s -X GET "${BASE_URL}/status?job_id=${JOB_ID}" | python3 -m json.tool || true
else
  echo "Skipping status check due to missing JOB_ID"
fi
echo -e "\n"

echo "=================================================="
echo "4. POST /chat (supported question: How many rows are there?)"
echo "=================================================="
curl -s -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many rows are there?"}' | python3 -m json.tool || true
echo -e "\n"

echo "=================================================="
echo "5. POST /chat (supported question: How many datasets are there?)"
echo "=================================================="
curl -s -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "How many datasets are there?"}' | python3 -m json.tool || true
echo -e "\n"

echo "=================================================="
echo "6. POST /chat (unsupported question)"
echo "=================================================="
curl -s -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the stock price of Apple?"}' | python3 -m json.tool || true
echo -e "\n"

echo "=================================================="
echo "7. Hostile input check: Non-CSV file upload"
echo "=================================================="
TEMP_TXT=$(mktemp /tmp/test_invalid.txt)
echo "This is not a CSV" > "${TEMP_TXT}"
curl -s -o /dev/null -w "HTTP Status Code: %{http_code}\n" -X POST "${BASE_URL}/ingest" -F "file=@${TEMP_TXT}" || true
rm -f "${TEMP_TXT}"
echo -e "\n"

echo "All curl tests executed successfully."
