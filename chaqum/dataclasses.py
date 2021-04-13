import asyncio

from collections import deque
from dataclasses import dataclass
from enum import Enum
from logging import getLogger,LoggerAdapter
from psutil import cpu_percent

from .util import run_once

log = getLogger("chaqum.job")

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

        self._state_waiters = {
            state: deque() for state in JobState
        }
        self._msg_inbox = deque()
        self._msg_waiters = deque()

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
        waiters = self._state_waiters[newstate]

        for fut in waiters:
            if not fut.cancelled():
                fut.set_result(True)

        waiters.clear()

    def set_waiting(self):
        self.set_state(JobState.WAITING)

    def set_starting(self):
        self.set_state(JobState.STARTING)

    def set_running(self):
        self.set_state(JobState.RUNNING)

    def set_done(self):
        self.set_state(JobState.DONE)

    def _state_changed(self, to):
        fut = self.loop.create_future()
        self._state_waiters[to].append(fut)
        return fut

    def wait_running(self):
        return self._state_changed(JobState.RUNNING)

    def wait_done(self):
        return self._state_changed(JobState.DONE)

    def _collect_message(self, result, was_collected, msg):
        if not was_collected.cancelled():
            was_collected.set_result(True)
        if not result.cancelled():
            result.set_result(msg)

    def collect_message(self):
        result = self.loop.create_future()

        if self._msg_inbox:
            self._collect_message(result, *self._msg_inbox.popleft())
        else:
            self._msg_waiters.append(result)

        return result

    def enqueue_message(self, msg):
        was_collected = self.loop.create_future()

        if self._msg_waiters:
            self._collect_message(
                self._msg_waiters.popleft(), was_collected, msg
            )
        else:
            self._msg_inbox.append((was_collected, msg))

        return was_collected

@dataclass
class GroupConfig:
    ident: str = None
    max_jobs: int = 0
    max_cpu: float = 0.0

class Group(dict):
    def __init__(self, loop, stats, config):
        self.loop = loop
        self.stats = stats
        self.ident = config.ident

        self._jobs_cond = None
        self._stats_cond = None
        self._queue = None

        if config.max_jobs:
            self._jobs_cond = lambda num_running: (
                num_running < config.max_jobs
            )

        if config.max_cpu:
            self._stats_cond = lambda: all((
                self.stats.cpu_percent < config.max_cpu,
            ))

        if self._jobs_cond or self._stats_cond:
            self._queue = deque()

    async def acquire_slot(self, job):
        if self._queue is None:
            job.set_running()
            return

        job.set_waiting()
        log = run_once(job.log.info, "Waiting for slot.")

        try:
            precursor = self._queue[-1]
        except IndexError:
            precursor = None

        # Make myself known in the queue.
        self._queue.append(self.loop.create_future())

        # Wait until the job in front of me has been served.
        if precursor is not None:
            log()
            await precursor

        # Do we need to wait for another job in this group to finish?
        if self._jobs_cond:
            runnung_jobs = [
                job for job in self.values()
                if job.state in (JobState.STARTING, JobState.RUNNING)
            ]

            if not self._jobs_cond(len(runnung_jobs)):
                log()
                await asyncio.wait(
                    [job.wait_done() for job in runnung_jobs],
                    return_when=asyncio.FIRST_COMPLETED
                )

        # Do we need to wait for system statistics to reach acceptable
        # levels?
        if self._stats_cond:
            log()
            await self.stats.notify_when(self._stats_cond)

        # We got ourselves a slot.
        job.set_running()

        # Make the queue advance.
        if not (fut := self._queue.popleft()).cancelled():
            fut.set_result(True)

@dataclass
class Message:
    ident: str
    data: bytes
    delivered: asyncio.Future = None
