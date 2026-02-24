from __future__ import annotations

import glob
import os
import sys
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.logging import get_logger

logger = get_logger("scripts.table_sanity_check")


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[dict[str, object]] = []
        self._current: dict[str, object] | None = None
        self._in_thead = False
        self._in_tbody = False
        self._in_tr = False
        self._row_cols = 0
        self._row_type: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "table":
            self._current = {"thead_cols": None, "tbody_cols": None, "thead_has_td": False}
            self.tables.append(self._current)
            return
        if t == "thead":
            self._in_thead = True
            return
        if t == "tbody":
            self._in_tbody = True
            return
        if t == "tr":
            if self._in_thead or self._in_tbody:
                self._in_tr = True
                self._row_cols = 0
                self._row_type = "thead" if self._in_thead else "tbody"
            return
        if t in {"th", "td"} and self._in_tr and self._current is not None:
            if self._in_thead and t == "td":
                self._current["thead_has_td"] = True
            colspan = 1
            for k, v in attrs:
                if k.lower() == "colspan" and v:
                    try:
                        colspan = int(v)
                    except ValueError:
                        colspan = 1
            self._row_cols += max(colspan, 1)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "tr":
            if self._in_tr and self._current is not None:
                if self._row_type == "thead" and self._current["thead_cols"] is None:
                    self._current["thead_cols"] = self._row_cols
                elif self._row_type == "tbody" and self._current["tbody_cols"] is None:
                    self._current["tbody_cols"] = self._row_cols
            self._in_tr = False
            self._row_cols = 0
            self._row_type = None
            return
        if t == "thead":
            self._in_thead = False
            return
        if t == "tbody":
            self._in_tbody = False
            return
        if t == "table":
            self._current = None


def run_checks(root: str | None = None) -> list[str]:
    base = root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    templates = glob.glob(os.path.join(base, "ui", "templates", "*.html"))
    issues: list[str] = []

    for path in sorted(templates):
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        parser = _TableParser()
        parser.feed(data)
        for idx, table in enumerate(parser.tables, start=1):
            thead_has_td = bool(table.get("thead_has_td"))
            thead_cols = table.get("thead_cols")
            tbody_cols = table.get("tbody_cols")
            if thead_has_td:
                issues.append(f"{path}: table#{idx} has <td> in <thead>")
            if thead_cols is not None and tbody_cols is not None and thead_cols != tbody_cols:
                issues.append(
                    f"{path}: table#{idx} column mismatch thead={thead_cols} tbody={tbody_cols}"
                )

    return issues


def main() -> int:
    issues = run_checks()
    if issues:
        logger.error("TABLE_SANITY_FAIL")
        for issue in issues:
            logger.error(issue)
        return 1
    logger.info("TABLE_SANITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
