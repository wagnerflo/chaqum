from asyncio import sleep as async_sleep,Event
from enum import Enum
from logging import getLogger,LoggerAdapter
from psutil import cpu_percent

log = getLogger('chaqum.job')

class JobState(Enum):
    INIT = 0
    WAITING = 1
    RUNNING = 2
    DONE = 3

class Job:
    def __init__(self, loop, ident, script, *args):
        self.ident = ident
        self.script = script
        self.args = args
        self.state = JobState.INIT
        self.log = LoggerAdapter(log, extra=dict(job=self))
        self._state_changed = Event(loop=loop)

    @property
    def is_waiting(self):
        return self.state == JobState.WAITING

    @property
    def is_running(self):
        return self.state == JobState.RUNNING

    @property
    def is_done(self):
        return self.state == JobState.DONE

    def set_state(self, newstate):
        if newstate == self.state:
            return

        self.state = newstate
        self._state_changed.set()
        self._state_changed.clear()

    def set_waiting(self):
        self.set_state(JobState.WAITING)

    def set_running(self):
        self.set_state(JobState.RUNNING)

    def set_done(self):
        self.set_state(JobState.DONE)

    async def state_changed(self, *limit_to):
        if not limit_to:
            limit_to = list(JobState)

        while self.state not in limit_to:
            await self._state_changed.wait()

        return self.state

    async def wait_done(self):
        return await self.state_changed(JobState.DONE)

class Group(dict):
    def __init__(self, ident, max_jobs=0, max_load=0.0):
        self.ident = ident
        self.max_jobs = max_jobs
        self.max_load = max_load

    async def slot_free(self):
        while self.is_full:
            await async_sleep(0.5)

    @property
    def is_full(self):
        return (
            ( self.max_jobs and self.num_running_jobs >= self.max_jobs ) or
            ( self.max_load and cpu_percent() >= self.max_load )
        )

    @property
    def num_running_jobs(self):
        return sum(1 for job in self.values() if job.is_running)
