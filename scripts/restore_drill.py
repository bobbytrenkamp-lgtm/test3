#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from test3.backup import verify_backup

parser = argparse.ArgumentParser(description="Verify backup hashes and restore to a temporary directory")
parser.add_argument("archive", type=Path)
args = parser.parse_args()
print(json.dumps(verify_backup(args.archive), indent=2))
