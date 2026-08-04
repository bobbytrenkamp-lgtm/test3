from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from .api import ROOT
from .service import Service


def _new_password() -> str:
    password = getpass.getpass("New local administrator password (16+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no change was made.")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize or rotate a test3 local administrator credential without exposing the password.")
    parser.add_argument("--email", required=True, help="Local sign-in email (not a hosted-service account)")
    parser.add_argument("--organization", default="Local CRE Organization")
    parser.add_argument("--display-name", default="Local Administrator")
    parser.add_argument("--reset-password", action="store_true", help="Rotate an existing unambiguous local user and revoke all sessions")
    args = parser.parse_args()
    data_dir = Path(os.getenv("TEST3_DATA_DIR", ROOT / "data"))
    service = Service(data_dir)
    if service.has_users() and not args.reset_password:
        raise SystemExit("A local user already exists. Use --reset-password only when you intend to rotate that credential and revoke its sessions.")
    if not service.has_users() and args.reset_password:
        raise SystemExit("No local user exists. Initialize the first administrator without --reset-password.")
    password = _new_password()
    try:
        if args.reset_password:
            result = service.reset_local_password(args.email, password)
            print(f"Local password rotated and sessions revoked for {result['email']}.")
        else:
            result = service.initialize_admin(args.organization, args.email, args.display_name, password)
            print(f"Local administrator initialized for {result['email']}.")
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
