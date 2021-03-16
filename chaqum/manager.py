import asyncio
import os
import logging
import shlex

from getopt import getopt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_REMOVED,EVENT_ALL_JOBS_REMOVED

from .dataclasses import Job,Group
from .util import (
    check_script,
    optstring,
    parse_interval,
    parse_cron,
    opt_to_value,
    opts_to_keywords,
)

log = logging.getLogger('chaqum')

loglevel_map = {
    'F': logging.CRITICAL,
    'C': logging.CRITICAL,
    'E': logging.ERROR,
    'W': logging.WARNING,
    'D': logging.DEBUG,
}

class Manager:
    def __init__(self, path):
        self._path = path
        self._jobs = None
        self._groups = None
        self._sched = None
        self._loop = None
        self._done = None

    @property
    def is_done(self):
        return (                        # we are done iff
            self._loop is not None and  #  - we been started
            not self._jobs and          #  - there are no jobs left
            not self._sched.get_jobs()  #  - the scheduler is empty
        )

    def _check_done(self, evt=None):
        if self.is_done:
            if not self._done.done():
                self._done.set_result(True)
            return True

    async def run(self, *init_args):
        if self._done is not None:
            raise Exception(f'{self} already running')

        self._jobs = {}
        self._groups = {}
        self._sched = AsyncIOScheduler()
        self._loop = asyncio.get_running_loop()
        self._done = self._loop.create_future()

        # add listener to get notified of relevant scheduler changes
        self._sched.add_listener(
            self._check_done,
            EVENT_JOB_REMOVED | EVENT_ALL_JOBS_REMOVED
        )

        # start the scheduler, wait for the init job and then until done
        self._sched.start()
        await self.register_job('init', ident='init', args=init_args)
        await self._done

        # cleanup
        self._sched.shutdown(wait=False)
        self._jobs = None
        self._sched = None
        self._loop = None
        self._done = None

    def register_job(self, script, args=[], ident=None, group=None, max_jobs=0):
        path = check_script(self._path, script)

        if ident is None:
            ident = f'{script}/{id(path)}'

        # create group
        grp = self._groups.get(group)

        if grp is None:
            grp = self._groups[group] = Group(group)

        # set parameters but only for none-default groups
        if group is not None:
            grp.max_jobs = max_jobs

        # create job object and register
        job = self._jobs[ident] = grp[ident] = Job(
            ident, self._loop.create_future(), path, args
        )

        # create task
        self._loop.create_task(self._run_job(job, grp))

        # return job object
        return job

    async def _run_job(self, job, grp):
        proc = None

        try:
            # wait for free slot
            job.set_waiting()
            await grp.slot_free()
            job.set_running()

            # prepare command pipes
            rd_fd, child_wr_fd = os.pipe()
            child_rd_fd, wr_fd = os.pipe()

            def preexec_fn():
                os.dup2(child_wr_fd, 3)
                os.dup2(child_rd_fd, 4)

            # spawn child
            proc = await asyncio.create_subprocess_exec(
                job.path, *job.args,
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
            rd = asyncio.StreamReader(loop=self._loop)
            await self._loop.connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(rd, loop=self._loop),
                open(rd_fd, 'rb', 0),
            )
            wr = asyncio.StreamWriter(
                *await self._loop.connect_write_pipe(
                    lambda: asyncio.streams.FlowControlMixin(loop=self._loop),
                    open(wr_fd, 'wb', 0),
                ),
                None, self._loop
            )

            # start task to handle task logging output
            log = self._loop.create_task(self._handle_logging(proc.stdout))

            # start task to handle commands
            cmd = self._loop.create_task(self._handle_commands(rd, wr))

            # wait for process and tasks to exit
            await proc.wait()
            await log
            await cmd

        except asyncio.CancelledError:
            if proc is not None:
                proc.terminate()

        finally:
            # remove from job lists
            del self._jobs[job.ident]
            del self._groups[grp.ident][job.ident]

            # signal end of job
            job.set_done()

        # check if the manager is done running
        self._check_done()

    async def _handle_logging(self, rd):
        try:
            while line := await rd.readline():
                line = line.decode().rstrip()

                if len(line) > 1 and line[1] == '\x1f':
                    lvl = loglevel_map.get(line[0], logging.INFO)
                    line = line[2:]
                else:
                    lvl = logging.INFO

                log.log(lvl, line)

        except asyncio.CancelledError:
            pass

    async def _handle_commands(self, rd, wr):
        try:
            while line := await rd.readline():
                try:
                    func,opts,args = self._parse_command(line.decode())
                    reply = await func(self, opts, *args)

                except Exception as exc:
                    reply = f'E {exc}'

                wr.write(reply.encode() + b'\n')
                await wr.drain()

        except asyncio.CancelledError:
            pass

    @optstring('i:c:')
    async def _handle_repeat(self, opts, script, *args):
        if interval := opts.get('-i'):
            trigger = parse_interval(interval)

        elif cron := opts.get('-c'):
            trigger = parse_cron(cron)

        else:
            return 'E Missing repetition specifier (-i/-c).'

        self._sched.add_job(
            self.register_job, kwargs=dict(
                script=script,
                args=args,
            ),
            trigger=trigger,
            max_instances=1,
        )

        return 'S'

    @optstring('g:m:c:')
    async def _handle_enqueue(self, opts, script, *args):
        job = self.register_job(
            script=script,
            args=args,
            **opts_to_keywords(
                opts,
                group    = ('-g', str),
                max_jobs = ('-m', int),
                max_load = ('-l', float),
            )
        )

        return f'S {job.ident}'

    @optstring('t:')
    async def _handle_wait(self, opts, *idents):
        timeout = opt_to_value(opts, '-t', float)
        jobs = {
            job.done: job
            for ident in idents
            if (job := self._jobs.get(ident)) is not None
        }

        done,pending = await asyncio.wait(jobs.keys(), timeout=timeout)

        return ' '.join(
            ['T' if pending else 'S'] +
            [jobs[fut].ident for fut in done]
        )

    _COMMANDS = {
        'repeat': _handle_repeat,
        'enqueue': _handle_enqueue,
        'wait': _handle_wait,
    }

    def _parse_command(self, cmd):
        cmd,*args = shlex.split(cmd)
        if func := self._COMMANDS.get(cmd, None):
            opts,args = getopt(args, func.optstring)
            return func,dict(opts),args
        raise Exception('Unknown command.')
