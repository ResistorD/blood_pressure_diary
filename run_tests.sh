#!/bin/bash
# Run tests with coverage

set -e

echo "Running PolySyndicate test suite..."
echo "===================================="

# Run tests with coverage
python -m pytest tests/ \
    --cov=. \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-report=xml \
    -v \
    "$@"

echo ""
echo "===================================="
echo "Coverage report generated in htmlcov/index.html"
echo "Run 'python -m http.server 8080 -d htmlcov' to view"
