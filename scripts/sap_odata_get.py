#!/usr/bin/env python3
"""Fetch a SAP OData JSON endpoint with Basic Auth."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests


DEFAULT_TIMEOUT_SECONDS = 15
MAX_TOP = 50


def _with_top(url: str, top: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "$top" not in query:
        query["$top"] = str(max(1, min(top, MAX_TOP)))
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a SAP OData JSON endpoint with Basic Auth.")
    parser.add_argument("url", nargs="?", default=os.getenv("SAP_ODATA_URL") or os.getenv("SAP_ODATA_BASE_URL"))
    parser.add_argument("--user", default=os.getenv("SAP_ODATA_USER") or os.getenv("SAP_USER"))
    parser.add_argument("--password-env", default="SAP_ODATA_PASSWORD")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if not args.url:
        print("Missing OData URL. Pass it as an argument or set SAP_ODATA_URL/SAP_ODATA_BASE_URL.", file=sys.stderr)
        return 2
    if not args.user:
        print("Missing user. Pass --user or set SAP_ODATA_USER/SAP_USER.", file=sys.stderr)
        return 2

    password = os.getenv(args.password_env) or os.getenv("SAP_PASSWORD")
    if not password:
        password = getpass.getpass(f"SAP OData password for {args.user}: ")

    response = requests.get(
        _with_top(args.url, args.top),
        auth=(args.user, password),
        headers={"Accept": "application/json"},
        timeout=args.timeout,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
