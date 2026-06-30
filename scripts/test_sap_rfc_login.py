#!/usr/bin/env python3
"""Probe SAP RFC login for one or more SAP client numbers."""

from __future__ import annotations

import argparse
import getpass
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Test SAP RFC login with pyrfc.")
    parser.add_argument("--host", default=os.getenv("SAP_ASHOST"))
    parser.add_argument("--sysnr", default=os.getenv("SAP_SYSNR"))
    parser.add_argument("--user", default=os.getenv("SAP_USER"))
    parser.add_argument("--clients", default=os.getenv("SAP_CLIENTS", "100,800"), help="Comma-separated SAP clients to try")
    args = parser.parse_args()

    try:
        from pyrfc import Connection
    except ModuleNotFoundError:
        print("pyrfc is not installed. Install SAP NetWeaver RFC SDK first, then install pyrfc.", file=sys.stderr)
        return 2

    missing = [name for name, value in {"SAP_ASHOST": args.host, "SAP_SYSNR": args.sysnr, "SAP_USER": args.user}.items() if not value]
    if missing:
        print(f"Missing {', '.join(missing)}. Pass flags or set environment variables.", file=sys.stderr)
        return 2

    password = getpass.getpass(f"SAP password for {args.user}: ")
    clients = [client.strip() for client in args.clients.split(",") if client.strip()]

    for client in clients:
        params = {
            "ashost": args.host,
            "sysnr": args.sysnr,
            "client": client,
            "user": args.user,
            "passwd": password,
            "lang": "EN",
        }
        try:
            conn = Connection(**params)
            result = conn.call("STFC_CONNECTION", REQUTEXT="DataChat RFC probe")
            echo = result.get("ECHOTEXT", "")
            print(f"client {client}: OK ({echo})")
            conn.close()
        except Exception as exc:
            print(f"client {client}: FAILED ({type(exc).__name__}: {exc})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
