from __future__ import annotations

STATE_OK = "OK"
STATE_WARN = "WARN"
STATE_STOP = "STOP"


def _bucket_for_age(age_s: float | None, warn_s: float, stop_s: float) -> str:
    if age_s is None:
        return STATE_STOP
    age = max(0.0, float(age_s))
    warn = float(warn_s)
    stop = float(stop_s)
    if age > stop:
        return STATE_STOP
    if age > warn:
        return STATE_WARN
    return STATE_OK


def compute_state(
    prev_state: str | None,
    age_s: float | None,
    warn_s: float,
    stop_s: float,
    hysteresis_s: float = 0.5,
) -> str:
    bucket = _bucket_for_age(age_s=age_s, warn_s=warn_s, stop_s=stop_s)
    if prev_state is None:
        return bucket

    prev = str(prev_state).upper()
    if prev not in {STATE_OK, STATE_WARN, STATE_STOP}:
        prev = bucket
    if age_s is None:
        return STATE_STOP

    age = max(0.0, float(age_s))
    warn = float(warn_s)
    stop = float(stop_s)
    hysteresis = max(0.0, float(hysteresis_s))

    if prev == STATE_OK and age > warn:
        return STATE_WARN
    if prev == STATE_WARN and age > stop:
        return STATE_STOP
    if prev == STATE_STOP and age <= (stop - hysteresis):
        return STATE_WARN
    if prev == STATE_WARN and age <= (warn - hysteresis):
        return STATE_OK
    return prev


def max_severity(data_state: str, book_state: str) -> str:
    ds = str(data_state).upper()
    bs = str(book_state).upper()
    if STATE_STOP in {ds, bs}:
        return STATE_STOP
    if STATE_WARN in {ds, bs}:
        return STATE_WARN
    return STATE_OK
