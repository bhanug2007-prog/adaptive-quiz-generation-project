"""Regenerates docs/openapi.json and docs/API.md from the running code, so the docs cannot drift.

    python -m scripts.write_api_doc
"""
import json
from collections import defaultdict
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

DOCS = Path(__file__).resolve().parents[2] / "docs"

INTRO = """# AdaptiveIQ API

Generated from the code by `python -m scripts.write_api_doc`. Interactive docs: http://127.0.0.1:8000/docs
(while the backend runs). Example responses for most endpoints: `docs/api-samples/` (test data).

**Conventions**

- JSON in and out. Errors are `{"detail": "<readable message>"}`. Validation errors (422) list each field.
- Sign-in sets an httpOnly session cookie (`aiq_session`). Send requests with credentials.
- Every POST, PUT, PATCH and DELETE must send the header `X-Requested-With: AdaptiveIQ`, and the browser's
  `Origin` must be the site itself or a configured frontend origin. Otherwise the response is 403.
- 401 = not signed in or session ended; 403 = wrong role, unverified email for that action, or blocked origin;
  404 = does not exist or not yours (the API does not reveal which); 409 = conflict with the current state
  (time is up, attempts used, question already answered); 429 = rate limited; 503 = model or integration
  not available.
- Answer keys are never in student responses before feedback is released.
"""


def main():
    spec = create_app(Settings(_env_file=None, database_url="sqlite://"), start_worker=False).openapi()
    (DOCS / "openapi.json").write_text(json.dumps(spec, indent=1))
    groups = defaultdict(list)
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            doc = (op.get("description") or "").strip().split("\n")[0]
            groups[op.get("tags", ["other"])[0]].append((path, method.upper(), op.get("summary", ""), doc))
    lines = [INTRO]
    for tag, items in groups.items():
        lines.append(f"\n## {tag[0].upper() + tag[1:]}\n\n| Method | Path | What it does |\n|---|---|---|")
        for path, method, summary, doc in items:
            lines.append(f"| {method} | `{path}` | {doc or summary} |")
    (DOCS / "API.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {DOCS / 'API.md'} ({sum(len(v) for v in groups.values())} operations) and openapi.json")


if __name__ == "__main__":
    main()
