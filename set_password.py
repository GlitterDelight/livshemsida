#!/usr/bin/env python3
"""Set the admin password: python3 set_password.py yourpassword"""
import hashlib
import json
import sys
from pathlib import Path

CONFIG = Path(__file__).parent / "admin_config.json"

if len(sys.argv) != 2 or not sys.argv[1]:
    print("Usage: python3 set_password.py <password>")
    raise SystemExit(1)

pw = sys.argv[1]
cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
cfg["password_hash"] = hashlib.sha256(pw.encode()).hexdigest()
CONFIG.write_text(json.dumps(cfg, indent=2))
print("Password set successfully.")
