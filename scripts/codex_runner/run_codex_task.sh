#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--run-tests] [--py-compile] [--name <run-name>] [--dry-run] <prompt-file>
USAGE
}

RUN_TESTS=0
RUN_PY_COMPILE=0
DRY_RUN=0
RUN_NAME=""
PROMPT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-tests)
      RUN_TESTS=1
      shift
      ;;
    --py-compile)
      RUN_PY_COMPILE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --name)
      RUN_NAME="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      PROMPT_FILE="$1"
      shift
      ;;
  esac
done

if [[ -z "$PROMPT_FILE" ]]; then
  echo "Prompt file is required" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi

if [[ -z "$RUN_NAME" ]]; then
  base_name="$(basename "$PROMPT_FILE")"
  RUN_NAME="${base_name%.*}"
fi

safe_name="$(echo "$RUN_NAME" | tr ' ' '_' | tr -cd '[:alnum:]_.-')"
if [[ -z "$safe_name" ]]; then
  safe_name="task"
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

ts="$(date +%Y-%m-%d_%H%M%S)"
RUN_DIR="$REPO_ROOT/codex/runs/${ts}_${safe_name}"
mkdir -p "$RUN_DIR"

cp "$PROMPT_FILE" "$RUN_DIR/prompt.txt"

CODEX_BIN="$(command -v codex || true)"
if [[ -z "$CODEX_BIN" ]]; then
  echo "codex CLI not found in PATH" >&2
  exit 127
fi

CODEX_EXIT="0"
MODE="exec"

if [[ "$DRY_RUN" -eq 1 ]]; then
  MODE="dry-run"
  {
    echo "Dry run: codex execution skipped."
    echo "Would run: codex exec -C \"$REPO_ROOT\" --output-last-message \"$RUN_DIR/codex_last_message.txt\" -"
  } > "$RUN_DIR/codex_stdout.txt"
  : > "$RUN_DIR/codex_stderr.txt"
else
  if codex exec --help >/dev/null 2>&1; then
    if codex exec -C "$REPO_ROOT" --output-last-message "$RUN_DIR/codex_last_message.txt" - \
      < "$RUN_DIR/prompt.txt" > "$RUN_DIR/codex_stdout.txt" 2> "$RUN_DIR/codex_stderr.txt"; then
      CODEX_EXIT="0"
    else
      CODEX_EXIT="$?"
    fi
  else
    MODE="interactive-fallback"
    if codex -C "$REPO_ROOT" "$(cat "$RUN_DIR/prompt.txt")" > "$RUN_DIR/codex_stdout.txt" 2> "$RUN_DIR/codex_stderr.txt"; then
      CODEX_EXIT="0"
    else
      CODEX_EXIT="$?"
    fi
  fi
fi

scripts/codex_runner/collect_artifacts.sh --run-dir "$RUN_DIR" \
  $([[ "$RUN_TESTS" -eq 1 ]] && echo --run-tests) \
  $([[ "$RUN_PY_COMPILE" -eq 1 ]] && echo --py-compile) \
  > "$RUN_DIR/collect_stdout.txt" 2> "$RUN_DIR/collect_stderr.txt" || true

{
  echo "codex_runner summary"
  echo "run_dir: $RUN_DIR"
  echo "repo_root: $REPO_ROOT"
  echo "prompt_source: $PROMPT_FILE"
  echo "prompt_copy: $RUN_DIR/prompt.txt"
  echo "codex_mode: $MODE"
  echo "codex_exit_code: $CODEX_EXIT"
  echo "run_tests: $RUN_TESTS"
  echo "py_compile: $RUN_PY_COMPILE"
  echo "artifacts:"
  echo "- codex_stdout.txt"
  echo "- codex_stderr.txt"
  echo "- codex_last_message.txt (if produced)"
  echo "- git_status.txt"
  echo "- changed_files.txt"
  echo "- git_diff_stat.txt"
  echo "- git_diff.patch"
  if [[ "$RUN_TESTS" -eq 1 ]]; then
    echo "- pytest.txt"
    echo "- pytest_status.txt"
  fi
  if [[ "$RUN_PY_COMPILE" -eq 1 ]]; then
    echo "- py_compile.txt"
    echo "- py_compile_status.txt"
  fi
  echo "paste_hint: share summary.txt + git_diff_stat.txt + (optional) codex_last_message.txt"
} > "$RUN_DIR/summary.txt"

cat "$RUN_DIR/summary.txt"

# Return codex exit code for CI/local scripting expectations.
# In dry-run mode this is always 0.
if [[ "$DRY_RUN" -eq 0 ]]; then
  exit "$CODEX_EXIT"
fi
