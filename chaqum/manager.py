import asyncio
import itertools
import os
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_REMOVED,EVENT_ALL_JOBS_REMOVED

from .dataclasses import (
    Job,
    Group,
    GroupConfig,
    Message,
)
from .flowcontrolmixin import (
    FlowControlMixin,
)
from .tasks import (
    CommandTask,
    LoggingTask,
    StatsTask,
)
from .util import (
    path_is_file,
    path_is_dir,
    path_is_executable,
    move_fd_above,
    get_max_fd,
)

log = logging.getLogger("chaqum.manager")

class Manager:
    def __init__(self, path, entry_script_name="entry"):
        self._path = path_is_dir(path)
        self._entry_script_name = entry_script_name
        self._reset()
        self._check_script(entry_script_name)

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

    def _check_script(self, script):
        path = self._path / script
        path_is_file(path)
        path_is_executable(path)

    async def run(self, *entry_args):
        if self._done is not None:
            raise Exception(f"{self} already running")

        self._loop = asyncio.get_running_loop()
        self._jobs = {}
        self._groups = {}
        self._messages = {}
        self._sched = AsyncIOScheduler()
        self._stats = StatsTask(self._loop)
        self._done = self._loop.create_future()

        self._pid = itertools.count(1)
        self._mid = itertools.count(1)

        # add listener to get notified of relevant scheduler changes
        self._sched.add_listener(
            self._check_done,
            EVENT_JOB_REMOVED | EVENT_ALL_JOBS_REMOVED
        )

        log.info("Job manager starting.")

        # start the scheduler, wait for the entry job to complete and
        # then until done
        self._sched.start()

        entry = self.register_job(
            self._entry_script_name,
            args = entry_args,
            ident = self._entry_script_name,
            forget = True,
        )

        await entry.wait_done()
        await self._done

        log.debug("Job manager shutting down.")

        # cleanup
        self._sched.shutdown(wait=False)
        self._reset()

        log.debug("Job manager stopped.")

    def _reset(self):
        self._loop = None
        self._jobs = None
        self._groups = None
        self._messages = None
        self._sched = None
        self._stats = None
        self._done = None
        self._pid = None
        self._mid = None

    def register_repeat(self, script, args, trigger):
        self._sched.add_job(
            self.register_job,
            kwargs = dict(
                script = script,
                args = args,
            ),
            trigger =trigger,
            max_instances = 1,
        )

    def register_message(self, data):
        ident = f"msg:{next(self._mid)}"
        msg = self._messages[ident] = Message(ident, data)
        return msg

    def get_message(self, ident):
        return self._messages.get(ident)

    def forget_message(self, msg):
        del self._messages[msg.ident]

    def register_job(self, script, args=[], ident=None, parent=None,
                     forget=False, group=GroupConfig()):
        self._check_script(script)

        if ident is None:
            ident = f"{script}/{next(self._pid)}"

        # get or create group
        if (grp := self._groups.get(group.ident)) is None:
            grp = self._groups[group.ident] = Group(
                self._loop, self._stats, group
            )

        # create job object and register it
        job = self._jobs[ident] = grp[ident] = Job(
            self._loop, ident, parent, script, *args
        )

        log.debug(f"Registered job '{' '.join((script,) + args)}'.")

        # create task
        job.task = self._loop.create_task(self._run_job(job, grp, forget))

        # return job object
        return job

    def get_job(self, ident):
        return self._jobs.get(ident)

    def forget_job(self, job):
        try:
            del self._jobs[job.ident]
        except:
            pass

    async def _run_job(self, job, grp, forget):
        proc = None

        try:
            # wait for free slot
            await grp.acquire_slot(job)

            # prepare command pipes
            rd_fd, child_wr_fd = os.pipe()
            child_rd_fd, wr_fd = os.pipe()

            # make sure that the child ends of the pipes lie above fd 4
            # so that preexec_fn can simply dup2 them without worry
            child_wr_fd = move_fd_above(4, child_wr_fd)
            child_rd_fd = move_fd_above(4, child_rd_fd)

            def preexec_fn():
                os.dup2(child_wr_fd, 3)
                os.dup2(child_rd_fd, 4)
                os.closerange(5, get_max_fd())

            job.log.info("Starting job.")

            # prepare environment variables for child
            env = os.environ.copy()
            env["CHAQUM_IDENT"] = job.ident
            if job.parent is not None:
                env["CHAQUM_PARENT"] = job.parent.ident

            # spawn child process
            proc = await asyncio.create_subprocess_exec(
                str(self._path / job.script),
                *job.args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                close_fds=False,
                preexec_fn=preexec_fn,
                cwd=self._path,
                env=env,
            )

            # close child pipe ends
            os.close(child_rd_fd)
            os.close(child_wr_fd)

            # connect pipe ends to asyncio protocols
            rd = asyncio.StreamReader(loop=self._loop)
            await self._loop.connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(rd, loop=self._loop),
                open(rd_fd, "rb", 0),
            )
            wr = asyncio.StreamWriter(
                *await self._loop.connect_write_pipe(
                    lambda: FlowControlMixin(loop=self._loop),
                    open(wr_fd, "wb", 0),
                ),
                None, self._loop
            )

            # start tasks to handle logging output and commands
            logtask = LoggingTask(self._loop, job, proc.stdout)
            cmdtask = CommandTask(self._loop, self, job, rd, wr)

            # set job to running and wait for process and tasks to exit
            job.set_running()
            await proc.wait()
            await logtask
            await cmdtask

            job.log.info("Job completed.")

        except asyncio.CancelledError:
            if proc is not None:
                proc.terminate()
                await proc.wait()

            job.log.info("Job terminated.")

        finally:
            # remove from group list
            del self._groups[grp.ident][job.ident]

            # remove from job list if user won't guarantee that job'll be awaited
            if forget:
                self.forget_job(job)

            # take note of exit code or signal
            if proc is not None:
                job.exitcode = proc.returncode

            # signal end of job
            job.set_done()

        # check if the manager is done running
        self._check_done()
