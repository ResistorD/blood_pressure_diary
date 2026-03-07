#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 --run-dir <path> [--run-tests] [--py-compile]
USAGE
}

RUN_DIR=""
RUN_TESTS=0
RUN_PY_COMPILE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      RUN_DIR="${2:-}"
      shift 2
      ;;
    --run-tests)
      RUN_TESTS=1
      shift
      ;;
    --py-compile)
      RUN_PY_COMPILE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$RUN_DIR" ]]; then
  echo "--run-dir is required" >&2
  usage >&2
  exit 2
fi

mkdir -p "$RUN_DIR"

# Core git artifacts
(git status --short && echo && git status) > "$RUN_DIR/git_status.txt" 2>&1 || true

git diff --name-only > "$RUN_DIR/.changed_tracked.txt" 2>/dev/null || true
git diff --cached --name-only > "$RUN_DIR/.changed_staged.txt" 2>/dev/null || true
git ls-files --others --exclude-standard > "$RUN_DIR/.changed_untracked.txt" 2>/dev/null || true
cat "$RUN_DIR/.changed_tracked.txt" "$RUN_DIR/.changed_staged.txt" "$RUN_DIR/.changed_untracked.txt" \
  | sed '/^$/d' | sort -u > "$RUN_DIR/changed_files.txt" || true

(git diff --stat && echo && git diff --cached --stat) > "$RUN_DIR/git_diff_stat.txt" 2>&1 || true
{
  echo "# WORKTREE DIFF"
  git diff || true
  echo
  echo "# STAGED DIFF"
  git diff --cached || true
} > "$RUN_DIR/git_diff.patch" 2>&1

# Optional: tests
if [[ "$RUN_TESTS" -eq 1 ]]; then
  if python -m pytest -q > "$RUN_DIR/pytest.txt" 2>&1; then
    echo "PASS" > "$RUN_DIR/pytest_status.txt"
  else
    echo "FAIL" > "$RUN_DIR/pytest_status.txt"
  fi
fi

# Optional: py_compile for changed python files
if [[ "$RUN_PY_COMPILE" -eq 1 ]]; then
  : > "$RUN_DIR/py_compile.txt"
  PY_STATUS="PASS"
  if [[ -s "$RUN_DIR/changed_files.txt" ]]; then
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      if [[ "$file" == *.py && -f "$file" ]]; then
        {
          echo "==> $file"
          if python -m py_compile "$file"; then
            echo "OK"
          else
            echo "FAIL"
            PY_STATUS="FAIL"
          fi
          echo
        } >> "$RUN_DIR/py_compile.txt" 2>&1
      fi
    done < "$RUN_DIR/changed_files.txt"
  fi
  echo "$PY_STATUS" > "$RUN_DIR/py_compile_status.txt"
fi

rm -f "$RUN_DIR/.changed_tracked.txt" "$RUN_DIR/.changed_staged.txt" "$RUN_DIR/.changed_untracked.txt"

echo "Artifacts collected in: $RUN_DIR"
