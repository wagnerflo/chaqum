import asyncio
import logging

class Bla(logging.Handler):
    def emit(self, record):
        asyncio.create_task(self._emit(record))

    async def _emit(self, record):
        print(self.format(record))
