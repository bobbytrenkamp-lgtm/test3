#!/usr/bin/env python3
import argparse
from pathlib import Path
from test3.backup import create_backup

parser = argparse.ArgumentParser(description="Create a local test3 backup containing confidential data")
parser.add_argument("destination", type=Path, help="New .zip path; existing files are never overwritten")
parser.add_argument("--data-dir", type=Path, default=Path("data"))
args = parser.parse_args()
print(create_backup(args.data_dir, args.destination))

