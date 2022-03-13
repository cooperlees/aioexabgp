#!/usr/bin/env python3

from subprocess import CompletedProcess


V4_ROUTES = """\
default via 174.87.192.1 dev ens2f0 proto dhcp src 174.87.192.58 metric 1012
default via 10.1.1.3 dev eno4 proto static metric 1070
10.0.0.0/8 via 10.6.9.3 dev vlan69 proto static metric 100
10.255.0.0/16 via 10.1.1.3 dev eno4 proto static metric 31337
1.1.1.0/24 via inet6 fd00::4 dev wg0 metric 31337
10.255.255.0/24 dev docker0 proto kernel scope link src 10.255.255.1 linkdown
174.87.192.1 dev ens2f0 proto dhcp scope link src 174.87.192.58 metric 1012
192.168.1.0/24 via 10.1.1.3 dev eno4 proto static metric 1069
"""
V4_CP = CompletedProcess(args=None, returncode=0, stdout=V4_ROUTES)

V6_ROUTES = """\
fd00:70::/64 via fd00::4 dev wg0 metric 31337
fc00::/7 via fe80::3 dev vlan69 proto static metric 1469 pref medium
default via fe80::201:5cff:fe7e:8446 dev ens2f0 proto ra metric 1012 expires 8997sec pref medium
"""
V6_CP = CompletedProcess(args=None, returncode=0, stdout=V6_ROUTES)


async def mocked_get_route_table(_, ip_version: int) -> CompletedProcess:
    if ip_version == 4:
        return V4_CP
    return V6_CP
