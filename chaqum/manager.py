import asyncio
import os
import re
import logging
import shlex

from getopt import getopt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_REMOVED,EVENT_ALL_JOBS_REMOVED

from .util import (
    ignore,
    optstring,
    parse_interval,
)

log = logging.getLogger('chaqum')

class Job:
    def __init__(self, script):
        self._script = script
        self._id = f'{script}/{id(self)}'

    @property
    def id(self):
        return self._id

class Manager:
    def __init__(self, path):
        self._path = path
        self._jobs = None
        self._sched = None

    async def run(self):
        self._jobs = {}
        self._sched = AsyncIOScheduler()

        loop = asyncio.get_running_loop()
        done = loop.create_future()

        def check_done(self, evt):
            if not self._sched.get_jobs():
                self._sched.shutdown(wait=False)
                done.set_result(True)

        self._sched.add_listener(
            check_done, EVENT_JOB_REMOVED | EVENT_ALL_JOBS_REMOVED
        )
        self._sched.start()

        await self.run_job('init')
        await done

        self._jobs = None
        self._sched = None

    @ignore(asyncio.CancelledError)
    async def run_job(self, script):
        # create job object and add to list
        job = Job(script)
        self._jobs[job.id] = job

        # wait for free slot
        # ...

        # prepare command pipes
        rd_fd, child_wr_fd = os.pipe()
        child_rd_fd, wr_fd = os.pipe()

        def preexec_fn():
            os.dup2(child_wr_fd, 3)
            os.dup2(child_rd_fd, 4)

        # spawn child
        proc = await asyncio.create_subprocess_exec(
            self._path / job._script,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            pass_fds={ 3, 4 },
            preexec_fn=preexec_fn,
        )

        # close child pipe ends
        os.close(child_rd_fd)
        os.close(child_wr_fd)

        # connect pipe ends to asyncio protocols
        loop = asyncio.get_running_loop()
        rd = asyncio.StreamReader(loop=loop)
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(rd, loop=loop),
            open(rd_fd, 'rb', 0),
        )
        wr_transport,wr_protocol = await loop.connect_write_pipe(
            lambda: asyncio.streams.FlowControlMixin(loop=loop),
            open(wr_fd, 'wb', 0),
        )
        wr = asyncio.StreamWriter(wr_transport, wr_protocol, None, loop)

        # start task to handle task logging output
        log = loop.create_task(self._handle_logging(proc.stdout))

        # start task to handle commands
        cmd = loop.create_task(self._handle_commands(rd, wr))

        # wait for process and tasks to exit
        await asyncio.gather(proc.wait(), log, cmd, return_exceptions=True)

        # remove from job list
        del self._jobs[job.id]

    @ignore(asyncio.CancelledError)
    async def _handle_logging(self, rd):
        while line := await rd.readline():
            log.info(line.decode().rstrip())

    @ignore(asyncio.CancelledError)
    async def _handle_commands(self, rd, wr):
        async def reply(s):
            wr.write(s.encode() + b'\n')
            await wr.drain()

        while line := await rd.readline():
            func,opts,args = self._parse_command(line.decode())
            if func is None:
                await reply('E unknown command')
            else:
                await reply(func(self, opts, args))

    @optstring('i:')
    def _handle_repeat(self, opts, args):
        if interval := opts.get('-i'):
            if (interval := parse_interval(interval)) is None:
                return 'E invalid interval'

            self._sched.add_job(
                self.run_job, args=args,
                trigger='interval',
                max_instances=1,
                **interval
            )

            return 'S'

        return 'E'

    _COMMANDS = {
        'repeat': _handle_repeat
    }

    def _parse_command(self, cmd):
        cmd,*args = shlex.split(cmd)
        if func := self._COMMANDS.get(cmd, None):
            opts,args = getopt(args, func.optstring)
            return func,dict(opts),args
        return None,None,None
