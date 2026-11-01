import re
NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"
def nums(s): return [float(x) for x in re.findall(NUM, s.replace(",", ""))]
def option_value(o):
    o = o.replace(",", "").strip()
    m = re.fullmatch(r"(?:about |approximately |~)?(" + NUM + r")\s*(?:[a-zA-Z%° ]{0,12})", o, re.I)
    return float(m.group(1)) if m else None
def numeric_conflict(p):
    vals = [option_value(o) for o in p["options"]]
    key = vals["ABCD".index(p["answer"])]
    if key is None or sum(v is not None for v in vals) < 3: return False     # not a numeric question
    found = nums(p["explanation"])
    if not found: return False
    last = found[-1]
    close = lambda a, b: abs(a - b) <= 0.02 * max(abs(a), abs(b), 1e-9)
    pct = any(t in p["options"]["ABCD".index(p["answer"])].lower() for t in ("%", "percent"))
    ok = close(last, key) or (pct and close(last * 100, key))
    return not ok                        # explanation's final result must equal the keyed option
