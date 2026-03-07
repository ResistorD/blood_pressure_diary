#!/usr/bin/env bash
set -euo pipefail

HOST="${PS_API_HOST:-127.0.0.1}"
PORT="${PS_API_PORT:-8000}"
BASE="http://${HOST}:${PORT}"
DEV_FLAG="${PS_DEV:-0}"

echo "== Dev Sanity =="
echo "BASE=${BASE}"
echo "PS_DEV=${DEV_FLAG}"

echo
echo "1) Server availability"
if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"; then
  echo "listen check: port ${PORT} is listening"
else
  echo "listen check: port ${PORT} not found in ss output (continuing with HTTP check)"
fi

curl -fsS -D - -o /dev/null "${BASE}/cases" | sed -n '1,12p'

echo
echo "2) static_v change check on /cases (2 requests, 2s apart)"
HTML1="$(curl -fsS "${BASE}/cases")"
V1="$(printf '%s' "${HTML1}" | grep -Eo '/static/[^"]+\?v=[^"]+' | head -n1 | sed -E 's/.*\?v=//')"
if [[ -z "${V1}" ]]; then
  echo "ERROR: could not extract static_v from first /cases response"
  exit 1
fi
sleep 2
HTML2="$(curl -fsS "${BASE}/cases")"
V2="$(printf '%s' "${HTML2}" | grep -Eo '/static/[^"]+\?v=[^"]+' | head -n1 | sed -E 's/.*\?v=//')"
if [[ -z "${V2}" ]]; then
  echo "ERROR: could not extract static_v from second /cases response"
  exit 1
fi
echo "v1=${V1}"
echo "v2=${V2}"

if [[ "${DEV_FLAG}" == "1" || "${DEV_FLAG,,}" == "true" || "${DEV_FLAG,,}" == "yes" || "${DEV_FLAG,,}" == "on" ]]; then
  if [[ "${V1}" == "${V2}" ]]; then
    echo "ERROR: static_v did not change in DEV"
    exit 1
  fi
  echo "OK: static_v changes in DEV"
else
  echo "INFO: PS_DEV is not enabled; static_v may stay stable in PROD"
fi

echo
echo "3) Cache headers"
echo "-- HTML (/cases) --"
curl -fsS -D - -o /dev/null "${BASE}/cases" | grep -Ei '^(cache-control|pragma|expires|etag|last-modified|http/)'
echo "-- CSS (/static/ps_terminal.css) --"
curl -fsS -D - -o /dev/null "${BASE}/static/ps_terminal.css" | grep -Ei '^(cache-control|pragma|expires|etag|last-modified|http/)'

echo
echo "Dev sanity completed."
