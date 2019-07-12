#!/usr/bin/env python3

import argparse
import asyncio
import logging
from ipaddress import IPv4Network, IPv6Network, ip_network
from json import JSONDecodeError, load
from pathlib import Path
from time import time
from typing import Awaitable, Dict, List, Union

from aioexabgp.announcer import Announcer
from aioexabgp.announcer.healthcheck import get_health_checker


IPNetwork = Union[IPv4Network, IPv6Network]
LOG = logging.getLogger(__name__)


class SampleAnnouncer(Announcer):
    """ An example making a ping cause routing advertising and withdrawal
        Note: I don't reccomend ping as your first choice
        - Alternate: Looking at your IGP's RIB/FIB programatically """

    async def advertise(self) -> None:
        while True:
            interval = self.config["advertise"]["interval"]
            start_time = time()

            healthcheck_coros: List[Awaitable] = []
            for prefix, checks in self.advertise_prefixes.items():
                LOG.debug(f"Scheduling health check(s) for {prefix}")
                for check in checks:
                    healthcheck_coros.append(check.check())

            # TODO: Create consumer worker pool
            healthcheck_results = await asyncio.gather(*healthcheck_coros)

            start_at = 0
            advertise_routes: List[IPNetwork] = []
            withdraw_routes: List[IPNetwork] = []
            for prefix, checks in self.advertise_prefixes.items():
                end_results = start_at + len(checks)
                my_results = healthcheck_results[start_at:end_results]

                if map(lambda r: isinstance(r, Exception), my_results) and all(
                    my_results
                ):
                    LOG.info(f"Advertising {prefix} prefix")
                    advertise_routes.append(prefix)
                else:
                    LOG.info(f"Withdrawing {prefix} prefix")
                    withdraw_routes.append(prefix)

                start_at += 1

            if advertise_routes:
                await self.add_routes(advertise_routes)
            if withdraw_routes:
                await self.withdraw_routes(withdraw_routes)

            run_time = time() - start_time
            sleep_time = interval - run_time
            LOG.debug(f"Route check original sleep_time = {sleep_time}s")
            if sleep_time < 0:
                sleep_time = 0
            LOG.info(f"Route checks complete. Sleeping for {sleep_time}s")
            await asyncio.sleep(sleep_time)

    async def learn(self) -> None:
        pass


def _gen_advertise_prefixes(config: Dict) -> Dict:
    advertise_prefixes = {}
    for prefix, checkers in config["advertise"]["prefixes"].items():
        try:
            network_prefix = ip_network(prefix)
        except ValueError:
            LOG.error(f"{prefix} ignored - Invalid IP Network")
            continue

        advertise_prefixes[network_prefix] = []

        if not checkers:
            continue

        for checker in checkers:
            advertise_prefixes[network_prefix].append(
                get_health_checker(checker["class"], checker["kwargs"])
            )

    return advertise_prefixes


def _gen_config(config: str) -> Dict:
    """ Generate an Announce config - We have one by default """
    json_conf = {}

    config_path = Path(config.config)
    if not config_path.exists():
        LOG.error(f"{config_path} does not exist. Can not continue")
        return json_conf

    try:
        with config_path.open("r") as cfp:
            json_conf = load(cfp)
    except JSONDecodeError:
        LOG.error(f"Invalid JSON in {config_path}")

    return json_conf


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample ExaBGP Announcer")
    parser.add_argument(
        "-c",
        "--config",
        default="sample_announcer.json",
        help="JSON Config mapping prefixes to healthchecks",
    )
    parser.add_argument(
        "-D", "--dry-run", action="store_true", help="Do not program learnt routes"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Verbose debug output"
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s (%(filename)s:%(lineno)d)",
        level=log_level,
    )

    config = _gen_config(args)
    if not config:
        return 69

    advertise_prefixes = _gen_advertise_prefixes(config)
    learn_fibs = []  # TODO: Pull from config
    announcer = SampleAnnouncer(config, advertise_prefixes, learn_fibs)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(announcer.coordinator())
    finally:
        loop.close()

    return 0


if __name__ == "__main__":
    exit(main())  # pragma: no cover
