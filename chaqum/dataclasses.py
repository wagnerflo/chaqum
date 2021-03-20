from asyncio import sleep as async_sleep
from enum import Enum
from logging import getLogger,LoggerAdapter
from psutil import cpu_percent

log = getLogger('chaqum.job')

class JobState(Enum):
    INIT     = 1
    WAITING  = 2
    STARTING = 3
    RUNNING  = 4
    DONE     = 5

class Job:
    def __init__(self, loop, ident, script, *args):
        self.loop = loop
        self.ident = ident
        self.script = script
        self.args = args
        self.state = JobState.INIT
        self.log = LoggerAdapter(log, extra=dict(job=self))
        self._state_waiters = []

    @property
    def is_waiting(self):
        return self.state == JobState.WAITING

    @property
    def is_starting(self):
        return self.state == JobState.STARTING

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
        self._state_waiters = [
            waiter for waiter in self._state_waiters
            if not self._notify_waiter(newstate, *waiter)
        ]

    def set_waiting(self):
        self.set_state(JobState.WAITING)

    def set_starting(self):
        self.set_state(JobState.STARTING)

    def set_running(self):
        self.set_state(JobState.RUNNING)

    def set_done(self):
        self.set_state(JobState.DONE)

    def state_changed(self, *limit_to):
        if not limit_to:
            limit_to = list(JobState)

        fut = self.loop.create_future()
        self._state_waiters.append((fut, limit_to))
        return fut

    def wait_done(self):
        return self.state_changed(JobState.DONE)

    def _notify_waiter(self, newstate, fut, limit_to):
        if newstate not in limit_to:
            return False

        if not fut.cancelled():
            fut.set_result(True)

        return True

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
            ( self.max_jobs and self.num_slots_used >= self.max_jobs ) or
            ( self.max_load and cpu_percent() >= self.max_load )
        )

    @property
    def num_slots_used(self):
        return sum(
            1 for job in self.values()
            if job.state in (JobState.STARTING, JobState.RUNNING)
        )
