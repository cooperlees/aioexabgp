#!/usr/bin/env python3

import argparse
import asyncio
import logging
import signal
from json import JSONDecodeError, load
from pathlib import Path
from typing import Dict

from aioexabgp.announcer import Announcer
from aioexabgp.announcer.healthcheck import gen_advertise_prefixes

LOG = logging.getLogger(__name__)


def _load_json_config(config_path: Path) -> Dict:
    """Generate an Announce config - We have one by default"""
    json_conf = {}

    if not config_path.exists():
        LOG.error(f"{config_path} does not exist. Can not continue")
        return json_conf

    try:
        with config_path.open("r") as cfp:
            json_conf = load(cfp)
    except JSONDecodeError:
        LOG.error(f"Invalid JSON in {config_path}")

    return json_conf


def _setup_logging(debug: bool, logfile: str) -> None:
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        filename=logfile,
        format="[%(asctime)s] %(levelname)s: %(message)s (%(filename)s:%(lineno)d)",
        level=log_level,
    )


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
    parser.add_argument(
        "-l",
        "--logfile",
        default=None,
        help="File to send announcer specific logs to (Default: stderr)",
    )
    args = parser.parse_args()

    _setup_logging(args.debug, args.logfile)

    config = _load_json_config(Path(args.config))
    if not config:
        return 69

    LOG.debug("Starting announcer - Config loaded ...")
    advertise_prefixes = gen_advertise_prefixes(config)
    announcer = Announcer(config, advertise_prefixes, dry_run=args.dry_run)

    loop = asyncio.get_event_loop()
    coordinator_task = loop.create_task(announcer.coordinator())
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, lambda: coordinator_task.cancel())

    try:
         loop.run_until_complete(coordinator_task)
     finally:
         loop.close()
    return 0


if __name__ == "__main__":
    exit(main())  # pragma: no cover
