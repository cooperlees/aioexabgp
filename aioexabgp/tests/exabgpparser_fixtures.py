#!/usr/bin/env python3

from ipaddress import ip_address, ip_network

from aioexabgp.announcer.fibs import FibOperation, FibPrefix


EXABGP_UPDATE_JSON = {
    "exabgp": "4.0.1",
    "time": 1562873630.5337727,
    "host": "us.cooperlees.com",
    "pid": 4734,
    "ppid": 4733,
    "counter": 18,
    "type": "update",
    "neighbor": {
        "address": {"local": "fc00:0:0:69::1", "peer": "fc00:0:0:69::2"},
        "asn": {"local": 65069, "peer": 65070},
        "direction": "receive",
        "message": {
            "update": {
                "attribute": {
                    "origin": "igp",
                    "as-path": [65070],
                    "confederation-path": [],
                },
                "announce": {"ipv6 unicast": {"fc00:0:0:69::2": [{"nlri": "70::/32"}]}},
            }
        },
    },
}
EXPECTED_UPDATE_REPONSE = [
    FibPrefix(
        ip_network("70::/32"), ip_address("fc00:0:0:69::2"), FibOperation.ADD_ROUTE
    )
]

EXABGP_WITHDRAW_JSON = {
    "exabgp": "4.0.1",
    "time": 1562873772.6388876,
    "host": "us.cooperlees.com",
    "pid": 4734,
    "ppid": 4733,
    "counter": 19,
    "type": "update",
    "neighbor": {
        "address": {"local": "fc00:0:0:69::1", "peer": "fc00:0:0:69::2"},
        "asn": {"local": 65069, "peer": 65070},
        "direction": "receive",
        "message": {
            "update": {
                "attribute": {
                    "origin": "igp",
                    "as-path": [65070],
                    "confederation-path": [],
                },
                "withdraw": {"ipv6 unicast": [{"nlri": "70::/32"}]},
            }
        },
    },
}
EXPECTED_WITHDRAW_REPONSE = [
    FibPrefix(ip_network("70::/32"), None, FibOperation.REMOVE_ROUTE)
]
