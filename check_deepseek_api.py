"""Validate DeepSeek credentials without starting Docker or an Agent task."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("DEEPSEEK_API_KEY is not configured.", file=sys.stderr)
        return 2

    api_base = os.environ.get(
        "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    ).rstrip("/")
    request = urllib.request.Request(
        f"{api_base}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        print(f"DeepSeek API check failed: HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"DeepSeek API check failed: {exc}", file=sys.stderr)
        return 1

    model_ids = sorted(
        item.get("id", "")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    )
    print("DeepSeek API credentials: PASS")
    print("Available models: " + (", ".join(model_ids) or "none returned"))
    if "deepseek-v4-flash" not in model_ids:
        print("Required model deepseek-v4-flash is unavailable.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
