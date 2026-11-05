"""Execution match: run the gold SQL and the model's SQL on the same data and
compare what comes back, not how the SQL is written.

Lenient where it doesn't change the answer:
  - column names and column order are ignored
  - extra columns in the model's result are fine (e.g. it returns the total
    alongside the top customer's name)
  - numbers are compared to 2 decimal places, whole-day timestamps as dates
Strict where it does:
  - same number of rows
  - row order only matters when the case says `ordered: true`
"""
import math
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from itertools import permutations

def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        f = float(v)
        if math.isnan(f):
            return None
        return round(f, 2) + 0.0      # +0.0 folds -0.0 into 0.0
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        # execute_query hands back ISO strings for timestamps
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            if s[10:].strip("T0:.Z ") == "":
                return s[:10]
        return s
    return str(v)

def _columns(rows: list[dict]) -> list[list]:
    if not rows:
        return []
    keys = list(rows[0].keys())
    return [[norm(r[k]) for r in rows] for k in keys]

def _same(a: list, b: list, ordered: bool) -> bool:
    return a == b if ordered else Counter(map(repr, a)) == Counter(map(repr, b))

def match(gold: list[dict], pred: list[dict], ordered: bool = False) -> bool:
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    g_cols, p_cols = _columns(gold), _columns(pred)
    if len(p_cols) < len(g_cols):
        return False

    # candidate predicted columns for each gold column, by their values alone
    candidates = [
        [j for j, pc in enumerate(p_cols) if _same(gc, pc, ordered)]
        for gc in g_cols
    ]
    if any(not c for c in candidates):
        return False

    g_rows = list(zip(*g_cols))
    for pick in _assignments(candidates):
        p_rows = list(zip(*(p_cols[j] for j in pick)))
        if _same(g_rows, p_rows, ordered):
            return True
    return False

def _assignments(candidates: list[list[int]], limit: int = 5000):
    """Distinct predicted column per gold column; capped so a wide result can't blow up."""
    seen = 0
    def walk(i, used):
        nonlocal seen
        if seen >= limit:
            return
        if i == len(candidates):
            seen += 1
            yield list(used)
            return
        for j in candidates[i]:
            if j not in used:
                used.append(j)
                yield from walk(i + 1, used)
                used.pop()
    yield from walk(0, [])
