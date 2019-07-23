#!/usr/bin/env python3

import asyncio
import logging
from typing import Sequence


LOG = logging.getLogger(__name__)


async def run_cmd(cmd: Sequence[str], timeout: float = 10.0) -> bool:
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        LOG.error(f"{' '.join(cmd)} asyncio timed out")
        return False

    if process.returncode != 0:
        LOG.error(
            f"{' '.join(cmd)} returned {process.returncode}:\n"
            + f"STDERR: {stderr.decode('utf-8')}\nSTDOUT: {stdout.decode('utf-8')}"
        )
        return False

    return True
