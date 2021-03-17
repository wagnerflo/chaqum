from asyncio import sleep as async_sleep,Future
from dataclasses import dataclass,field
from enum import Enum
from logging import getLogger,LoggerAdapter
from psutil import cpu_percent
from typing import List

log = getLogger('chaqum.job')

class JobState(Enum):
    INIT = 0
    WAITING = 1
    RUNNING = 2
    DONE = 3

@dataclass
class Job:
    ident: str
    done: Future
    script: str
    args: List[str] = field(default_factory=list)
    state: JobState = field(default=JobState.INIT, init=False)
    log: LoggerAdapter = field(init=False)

    def __post_init__(self):
        self.log = LoggerAdapter(log, extra=dict(job=self))

    @property
    def is_running(self):
        return self.state == JobState.RUNNING

    def set_waiting(self):
        self.state = JobState.WAITING

    def set_running(self):
        self.state = JobState.RUNNING

    def set_done(self):
        self.state = JobState.DONE
        if not self.done.done():
            self.done.set_result(True)

    def __await__(self):
        return self.done.__await__()

@dataclass
class Group(dict):
    ident: str
    max_jobs: int = field(default=0)
    max_load: float = field(default=0.0)

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
