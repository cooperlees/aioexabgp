#!/usr/bin/env python3
""" Experimental ExaBGP Pipes handling with asyncio """

import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from select import select
from typing import NamedTuple, Optional, Union


LOG = logging.getLogger(__name__)


class PipePaths(NamedTuple):
    in_pipe: Path
    out_pipe: Path


class ExaBGPPipes:
    """Class to control reading and writing to ExaBGP FIFO Named Pipes
    - Caller to maintain synconization with self.alock"""

    def __init__(
        self,
        in_pipe: Path,
        out_pipe: Path,
        *,
        executor: Optional[Union[ProcessPoolExecutor, ThreadPoolExecutor]] = None,
        read_chunk_size: int = 4096,
    ) -> None:
        self.alock = asyncio.Lock()
        self.executor = executor
        self.loop = asyncio.get_event_loop()
        self.pipe_paths = PipePaths(in_pipe, out_pipe)
        self.read_chunk_size = read_chunk_size

    async def check_pipes(self) -> bool:
        """Check that we can stat each pipe"""
        access_results = await asyncio.gather(
            self.loop.run_in_executor(
                self.executor, os.access, self.pipe_paths.in_pipe, os.W_OK
            ),
            self.loop.run_in_executor(
                self.executor, os.access, self.pipe_paths.out_pipe, os.R_OK
            ),
        )
        for idx, access_success in enumerate(access_results):
            if not access_success:
                LOG.error(f"{self.pipe_paths[idx]} does not have required access")

        return True

    def _read(self) -> bytes:
        rbuffer = b""
        try:
            fd = os.open(self.pipe_paths.in_pipe, os.O_RDONLY | os.O_NONBLOCK)
            while select([fd], [], [], 0) != ([], [], []):
                rbuffer = os.read(fd, self.read_chunk_size)
            return rbuffer
        finally:
            os.close(fd)

    async def read(self, *, timeout: float = 5.0) -> bytes:
        """Read API response and deserialize it
        - Wrap blocking read in an executor so it's non blocking
          and has a customizable timeout

        Throws:
            - IOError
            - asyncio.TimeoutError"""

        return await asyncio.wait_for(
            self.loop.run_in_executor(self.executor, self._read), timeout=timeout
        )

    def _write(self, msg: bytes) -> int:
        try:
            fd = os.open(self.pipe_paths.in_pipe, os.O_WRONLY)
            return os.write(fd, msg + b"\n")
        finally:
            os.close(fd)

    async def write(self, msg: Union[bytes, str], *, timeout: float = 5.0) -> int:
        """Write str to API FIFO
        - Wrap blocking write in an executor so it's non blocking
          and has a customizable timeout

        Throws: IOError, asyncio.TimeoutError"""

        if isinstance(msg, str):
            msg = msg.encode("utf-8")

        return await asyncio.wait_for(
            self.loop.run_in_executor(self.executor, self._write, msg), timeout=timeout
        )
