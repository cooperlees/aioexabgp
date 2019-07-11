#!/usr/bin/env python3

import json
from datetime import datetime
from sys import stdin


LOG_FILE = "/tmp/exabgp_json"


with open(LOG_FILE, "w") as log_fp:
    print("Starting the exabgp logger", file=log_fp, flush=True)
    while True:
        line = stdin.readline().strip()
        formatted_json = json.dumps(json.loads(line), indent=2)
        print(f"{datetime.now().isoformat()}:", file=log_fp, flush=True)
        print(formatted_json, file=log_fp, flush=True)
        print("", file=log_fp, flush=True)
