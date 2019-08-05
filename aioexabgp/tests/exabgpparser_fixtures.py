#!/usr/bin/env python3

from ipaddress import ip_address, ip_network

from aioexabgp.announcer.fibs import FibOperation, FibPrefix


# Ensure we throw a value error
EXABGP_BAD_VERSION_JSON = {"exabgp": "69.69.69"}

# We just log this, but don't change any state
# It just shows TCP connectivity (I think)
EXABGP_CONNECTED_JSON = {
    "exabgp": "4.0.1",
    "time": 1563994945.4303036,
    "host": "us.cooperlees.com",
    "pid": 5911,
    "ppid": 5910,
    "counter": 6,
    "type": "state",
    "neighbor": {
        "address": {"local": "fc00:0:0:69::1", "peer": "fc00:0:0:69::2"},
        "asn": {"local": 65069, "peer": 65070},
        "state": "connected",
    },
}

# Pull all routes from FIBs
EXABGP_DOWN_JSON = {
    "exabgp": "4.0.1",
    "time": 1563994930.015714,
    "host": "us.cooperlees.com",
    "pid": 5911,
    "ppid": 5910,
    "counter": 5,
    "type": "state",
    "neighbor": {
        "address": {"local": "fc00:0:0:69::1", "peer": "fc00:0:0:69::2"},
        "asn": {"local": 65069, "peer": 65070},
        "state": "down",
        "reason": "peer reset, message (notification sent (4,0)) error(Hold timer expired / Unspecific)",
    },
}
EXPECTED_DOWN_RESPONSE = [
    FibPrefix(
        ip_network("::/0"), ip_address("fc00:0:0:69::2"), FibOperation.REMOVE_ALL_ROUTES
    )
]

# Readvertise all "healthy" summary routes
# - learned routes from peer will be readded to FIBs
EXABGP_UP_JSON = {
    "exabgp": "4.0.1",
    "time": 1563994945.6474342,
    "host": "us.cooperlees.com",
    "pid": 5911,
    "ppid": 5910,
    "counter": 7,
    "type": "state",
    "neighbor": {
        "address": {"local": "fc00:0:0:69::1", "peer": "fc00:0:0:69::2"},
        "asn": {"local": 65069, "peer": 65070},
        "state": "up",
    },
}
FAKE_HEALTHY_PREFIXES = {ip_network("69::/32")}
EXPECTED_UP_RESPONSE = [
    FibPrefix(
        list(FAKE_HEALTHY_PREFIXES)[0],
        ip_address("fc00:0:0:69::2"),
        FibOperation.ADD_ROUTE,
    )
]

# Add learned routes to FIBs
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

# Remove learned routes from FIBs
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
    FibPrefix(
        ip_network("70::/32"), ip_address("fc00:0:0:69::2"), FibOperation.REMOVE_ROUTE
    )
]
