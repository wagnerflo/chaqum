import asyncio
import logging

loglevel_map = {
    "C": logging.CRITICAL,
    "E": logging.ERROR,
    "W": logging.WARNING,
    "D": logging.DEBUG,
}

class LoggingTask:
    def __init__(self, loop, job, rd):
        self.loop = loop
        self.job = job
        self.rd = rd
        self.task = loop.create_task(self._run())

    def __await__(self):
        return self.task.__await__()

    async def _run(self):
        try:
            while line := await self.rd.readline():
                line = line.decode().rstrip()

                if len(line) > 1 and line[1] == "\x1f":
                    lvl = loglevel_map.get(line[0], logging.INFO)
                    line = line[2:]
                else:
                    lvl = logging.INFO

                self.job.log.log(lvl, line)

        except asyncio.CancelledError:
            pass
