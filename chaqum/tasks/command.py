import asyncio
import getopt
import re
import shlex

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from ..dataclasses import GroupConfig

_RE_INTERVAL = re.compile(
    r"""
        ^
        (?P<seconds>\d+)s |
        (?P<minutes>\d+)m |
        (?P<hours>\d+)h   |
        (?P<days>\d+)d    |
        (?P<weeks>\d+)w
    """, re.X
)

def parse_interval(interval):
    kws = {}
    while interval:
        match = _RE_INTERVAL.match(interval)
        if match is None:
            raise Exception("Invalid interval specifier.")
        kws.update(
            (k,int(v)) for k,v in match.groupdict().items()
            if v is not None
        )
        interval = interval[match.end():]
    return IntervalTrigger(**kws)

def parse_cron(cron):
    parts = cron.split()
    kws = dict()

    if len(parts) == 6:
        kws.update(
            second = parts.pop(0)
        )

    if len(parts) == 5:
        kws.update(
            minute      = parts[0],
            hour        = parts[1],
            day         = parts[2],
            month       = parts[3],
            day_of_week = parts[4],
        )
        return CronTrigger(**kws)

    raise Exception("Invalid cron specifier.")

def opt_to_value(opts, opt, conv):
    try:
        return conv(opts[opt])
    except KeyError:
        return None
    except ValueError:
        raise Exception(
            f"Expected '{conv.__name__}' for option '{opt}'."
        )

def opts_to_keywords(opts, **kws):
    return {
        name: val
        for name,(opt,conv) in kws.items()
        if (val := opt_to_value(opts, opt, conv)) is not None
    }

class CommandRegistry(dict):
    def add(self, optstr=""):
        def decorator(func):
            func.optstring = optstr
            self[func.__name__] = func
            return func
        return decorator

class CommandTask:
    commands = CommandRegistry()

    def __init__(self, loop, manager, job, rd, wr):
        self.loop = loop
        self.manager = manager
        self.job = job
        self.rd = rd
        self.wr = wr
        self.task = loop.create_task(self._run())

    def __await__(self):
        return self.task.__await__()

    async def _run(self):
        try:
            while line := (await self.rd.readline()).decode().strip():
                reply = "E"
                func = None
                opts = None

                try:
                    cmd,*args = shlex.split(line)
                    if func := self.commands.get(cmd, None):
                        opts,args = getopt.getopt(args, func.optstring)
                    else:
                        self.job.log.error(f"Unknown command '{line}'.")

                except Exception as exc:
                    self.job.log.error(
                        f"Unparsable command '{line}': {exc}.",
                        exc_info=True
                    )

                if func is not None and opts is not None:
                    try:
                        reply = await func(self, dict(opts), *args)

                    except Exception as exc:
                        self.job.log.error(f"{cmd}: {exc}", exc_info=True)

                if isinstance(reply, str):
                    reply = (reply.encode(), b"\n")

                self.wr.writelines(reply)
                await self.wr.drain()

        except asyncio.CancelledError:
            pass

    @commands.add("i:c:")
    async def repeat(self, opts, script, *args):
        if interval := opts.get("-i"):
            trigger = parse_interval(interval)

        elif cron := opts.get("-c"):
            trigger = parse_cron(cron)

        else:
            raise Exception("Missing repetition specifier (-i/-c).")

        self.manager.register_repeat(script, args, trigger)

        return "S"

    @commands.add("g:m:c:")
    async def enqueue(self, opts, script, *args):
        kws = dict(
            script = script,
            args = args,
        )

        if "-g" in opts:
            kws.update(
                group = GroupConfig(
                    **opts_to_keywords(
                        opts,
                        ident    = ("-g", str),
                        max_jobs = ("-m", int),
                        max_cpu  = ("-c", float),
                    )
                ),
            )

        job = self.manager.register_job(**kws)

        return f"S {job.ident}"

    @commands.add("t:")
    async def waitjobs(self, opts, *idents):
        jobs = {
            job.wait_done(): job
            for ident in idents
            if (job := self.manager.get_job(ident)) is not None
        }

        _,pending = await asyncio.wait(
            jobs.keys(),
            timeout=opt_to_value(opts, "-t", float),
        )

        return " ".join(
            ["T" if pending else "S"] +
            [jobs[fut].ident for fut in pending]
        )

    @commands.add()
    async def sendmsg(self, opts, ident, length):
        data = await self.rd.readexactly(int(length))
        await self.rd.readuntil()

        if (job := self.manager.get_job(ident)) is None:
            raise Exception(f"Unknown message destination '{ident}'.")

        msg = self.manager.register_message(data)
        msg.delivered = job.enqueue_message(msg)

        return f"S {msg.ident}"

    @commands.add("t:")
    async def waitrecv(self, opts, *idents):
        messages = {
            msg.delivered: msg
            for ident in idents
            if (msg := self.manager.get_message(ident)) is not None
        }

        _,pending = await asyncio.wait(
            messages.keys(),
            timeout=opt_to_value(opts, "-t", float),
        )

        return " ".join(
            ["T" if pending else "S"] +
            [messages[fut].ident for fut in pending]
        )

    @commands.add("t:")
    async def recvmsg(self, opts):
        fut = self.job.collect_message()
        _,pending = await asyncio.wait(
            [fut],
            timeout=opt_to_value(opts, "-t", float),
        )
        if pending:
            return "T"

        msg = fut.result()
        self.manager.forget_message(msg)

        return (
            f"S {len(msg.data)}\n".encode("ascii"),
            msg.data,
            b"\n",
        )
