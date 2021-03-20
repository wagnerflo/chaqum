import asyncio
import psutil

class StatsTask:
    def __init__(self, loop, interval=0.5):
        self._update_stats()
        self._loop = loop
        self._interval = 0.5
        self._waiters = {}
        self._task = loop.create_task(self._run())

    def __await__(self):
        return self.task.__await__()

    def _update_stats(self):
        self.cpu_percent = psutil.cpu_percent()

    async def _run(self):
        try:
            while True:
                await asyncio.sleep(self._interval)
                self._update_stats()

                try:
                    fut = next(
                        fut for fut,cond in self._waiters.items()
                        if cond()
                    )

                    if not fut.cancelled():
                        fut.set_result(True)

                    del self._waiters[fut]

                except StopIteration:
                    pass

        except asyncio.CancelledError:
            pass

    def notify_when(self, cond):
        fut = self._loop.create_future()
        self._waiters[fut] = cond
        return fut
