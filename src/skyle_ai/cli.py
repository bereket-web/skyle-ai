from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(prog="skyle-ai", description="Run or inspect the local Skyle AI workbench.")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Start the local API and web interface")
    serve.add_argument("--host", default="127.0.0.1", help="Bind address; loopback is the safe default")
    serve.add_argument("--port", type=int, default=8000)
    check = sub.add_parser("health", help="Check a running Skyle AI instance")
    check.add_argument("--url", default="http://127.0.0.1:8000/health")
    args = parser.parse_args()
    if args.command in {None, "serve"}:
        import uvicorn

        uvicorn.run(
            "skyle_ai.api:app", host=getattr(args, "host", "127.0.0.1"), port=getattr(args, "port", 8000), reload=False
        )
    elif args.command == "health":
        request = urllib.request.Request(args.url)
        token = os.environ.get("SKYLE_API_KEY")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                print(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Health check failed: {exc.__class__.__name__}", file=sys.stderr)
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
