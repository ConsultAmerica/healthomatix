from __future__ import annotations

import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
repository_root = backend_root.parent
sys.path.insert(0, str(backend_root))

from app.main import app  # noqa: E402


def main() -> int:
    output_path = repository_root / "packages" / "api-client" / "openapi.json"
    specification = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if not output_path.exists() or output_path.read_text(encoding="utf-8") != specification:
            print("OpenAPI specification is stale. Run npm run api:generate.", file=sys.stderr)
            return 1
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(specification, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
