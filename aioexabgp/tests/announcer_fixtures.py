#!/usr/bin/env python3


NEXT_HOP = "2000:69::1"
ANNOUNCER_CONFIG = {
    "conf_version": "0.0.2",
    "advertise": {
        "interval": 5.0,
        "next_hop": NEXT_HOP,
        "prefixes": {
            "69::/32": [
                {
                    "class": "PingChecker",
                    "kwargs": {"config": {"ping_target": "69::69"}},
                }
            ],
            "70::/32": [
                {
                    "class": "PingChecker",
                    "kwargs": {"config": {"ping_target": "70::69"}},
                }
            ],
        },
    },
    "learn": {
        "allow_default": True,
        "fibs": ["Linux"],
        "filter_prefixes": [],
        "prefix_limit": 0,
    },
    "log_level": "Debug",
}
