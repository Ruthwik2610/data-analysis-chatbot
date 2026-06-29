#!/usr/bin/env python3
"""Call a specific SAP RFC function through PyRFC.

Connection values can be passed as flags or environment variables. The password
is intentionally read from an environment variable or prompt, not a CLI flag.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Any


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("JSON parameters must be an object")
    return value


def _required(value: str | None, name: str) -> str:
    if value:
        return value
    raise SystemExit(f"Missing {name}. Pass --{name.lower()} or set SAP_{name}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Call an SAP ABAP RFC function through PyRFC.")
    parser.add_argument("--function", required=True, help="RFC function module name, e.g. STFC_CONNECTION")
    parser.add_argument("--params-json", type=_json_object, default={}, help='RFC parameters as JSON object, e.g. \'{"REQUTEXT":"ping"}\'')
    parser.add_argument("--ashost", default=os.getenv("SAP_ASHOST"), help="SAP application server host")
    parser.add_argument("--sysnr", default=os.getenv("SAP_SYSNR"), help="SAP system number")
    parser.add_argument("--client", default=os.getenv("SAP_CLIENT"), help="SAP client")
    parser.add_argument("--user", default=os.getenv("SAP_USER"), help="SAP user")
    parser.add_argument("--password-env", default="SAP_PASSWORD", help="Environment variable containing the SAP password")
    parser.add_argument("--lang", default=os.getenv("SAP_LANG", "EN"), help="SAP logon language")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    try:
        from pyrfc import Connection
    except ModuleNotFoundError:
        print(
            "pyrfc is not installed. Install SAP NetWeaver RFC SDK, set SAPNWRFC_HOME, then install pyrfc.",
            file=sys.stderr,
        )
        return 2

    password = os.getenv(args.password_env) or getpass.getpass(f"SAP password for {args.user or 'user'}: ")
    conn = Connection(
        ashost=_required(args.ashost, "ASHOST"),
        sysnr=_required(args.sysnr, "SYSNR"),
        client=_required(args.client, "CLIENT"),
        user=_required(args.user, "USER"),
        passwd=password,
        lang=args.lang,
    )
    try:
        result = conn.call(args.function, **args.params_json)
    finally:
        conn.close()

    print(json.dumps(result, indent=2 if args.pretty else None, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
