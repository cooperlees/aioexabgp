#!/usr/bin/env python3

import asyncio
import logging
from subprocess import CompletedProcess
from typing import Sequence


LOG = logging.getLogger(__name__)


async def run_cmd(
    cmd: Sequence[str], timeout: float = 10.0, encoding: str = "utf-8"
) -> CompletedProcess:
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        LOG.error(f"{' '.join(cmd)} asyncio timed out")
        return CompletedProcess(
            args=cmd,
            returncode=-1,
            stderr="TIMEOUT",
            stdout="",
        )

    if process.returncode is None:
        LOG.error(f"{' '.join(cmd)} didn't return a returncode ...")
        return CompletedProcess(
            args=cmd,
            returncode=-2,
            stderr="Returncode is None",
            stdout="",
        )

    cp = CompletedProcess(
        args=cmd,
        returncode=process.returncode,
        stderr=stderr.decode(encoding),
        stdout=stdout.decode(encoding),
    )

    if cp.returncode != 0:
        LOG.error(
            f"{' '.join(cmd)} returned {cp.returncode}:\nSTDERR: {cp.stderr}\n"
            + f"STDOUT: {cp.stdout}"
        )

    return cp
