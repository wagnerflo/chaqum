import dataclasses
import json
import shlex
import sys

# reconfigure sys.stdout and sys.stderr to be line buffered (in
# non-interactive mode they are block buffered by default) to make
# simple print() statements work
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# create our own handles to stderr and the command pipe so we can be
# sure that our logging works as expected even if someone reconfigures
# sys.stderr again
stderr = open(2, "wb")
pipe_wr = open(3, "wb")
pipe_rd = open(4, "rb")

def _send_log(lvl, sep, args):
    stderr.write(lvl)
    stderr.write(b"\x1f")
    stderr.write(sep.join(str(arg) for arg in args).encode())
    stderr.write(b"\n")
    stderr.flush()

def _send_command(*parts, flush=True):
    pipe_wr.write(shlex.join(str(part) for part in parts).encode())
    pipe_wr.write(b"\n")
    if flush:
        pipe_wr.flush()

def _recv_response():
    status,*rest = pipe_rd.readline().decode().strip().split(" ", 1)
    return status,rest[0] if rest else None

class log:
    @staticmethod
    def critical(*args, sep=" "):
        _send_log(b"C", sep, args)

    @staticmethod
    def error(*args, sep=" "):
        _send_log(b"E", sep, args)

    @staticmethod
    def warning(*args, sep=" "):
        _send_log(b"W", sep, args)

    @staticmethod
    def info(*args, sep=" "):
        _send_log(b"I", sep, args)

    @staticmethod
    def debug(*args, sep=" "):
        _send_log(b"D", sep, args)

@dataclasses.dataclass(frozen=True)
class msg:
    ident: str
    delivered: bool = False

    def waitrecv(self, timeout=None):
        return waitrecv(self)

@dataclasses.dataclass(frozen=True)
class job:
    ident: str
    group: str

    def wait(self, timeout=None):
        return waitjobs(self, timeout=timeout)

    def kill(self, timeout=None):
        return killjobs(self, timeout=timeout)

    def sendmsg(self, buf):
        _send_command("sendmsg", "--", self.ident, len(buf), flush=False)
        pipe_wr.write(buf)
        pipe_wr.write(b"\n")
        pipe_wr.flush()
        status,ident = _recv_response()
        if status != "S":
            raise Exception()
        return msg(ident)

    def sendjson(self, obj):
        return self.sendmsg(json.dumps(obj).encode("utf-8"))

def enqueue(script, *args, group=None, max_jobs=None, max_cpu=None):
    _send_command(
        "enqueue",
        *() if group    is None else ("-g", group),
        *() if max_jobs is None else ("-m", max_jobs),
        *() if max_cpu  is None else ("-c", max_cpu),
        "--",
        script, *args
    )
    status,ident = _recv_response()
    if status != "S":
        raise Exception()
    return job(ident, group)

def _repeat(script, args, *opts):
    _send_command(
        "repeat",
        *opts,
        "--",
        script, *args
    )
    status,_ = _recv_response()
    if status != "S":
        raise Exception()

def interval(script, *args,
             seconds=0, minutes=0, hours=0, days=0, weeks=0):
    return _repeat(
        script, args,
        "-i", f"{seconds}s{minutes}m{hours}h{days}d{weeks}w",
    )

def cron(script, *args,
         second="*", minute="*", hour="*", day="*", month="*", day_of_week="*"):
    return _repeat(
        script, args,
        "-c", f"{second} {minute} {hour} {day} {month} {day_of_week}",
    )

def _on_items(cmd, items, timeout):
    _send_command(
        cmd,
        *() if timeout is None else ("-t", timeout),
        "--",
        *(item.ident for item in items)
    )
    status,pending = _recv_response()
    if status not in ("T", "S"):
        raise Exception()
    if not pending:
        return []
    pending = pending.split(" ")
    return [
        item for item in items if item.ident in pending
    ]

def waitjobs(*jobs, timeout=None):
    return _on_items("waitjobs", jobs, timeout)

def killjobs(*jobs, timeout=None):
    return _on_items("killjobs", jobs, timeout)

def waitrecv(*messages, timeout=None):
    return _on_items("waitrecv", messages, timeout)

def recvmsg(timeout=None):
    _send_command(
        "recvmsg",
        *() if timeout is None else ("-t", timeout),
    )
    status,length = _recv_response()
    data = pipe_rd.read(int(length))
    pipe_rd.read(1)
    return data

def recvjson(timeout=None):
    return json.loads(recvmsg(timeout=timeout).decode("utf8"))

__all__ = (
    "log",
    "enqueue",
    "interval",
    "cron",
    "waitjobs",
    "killjobs",
    "waitrecv",
    "recvmsg",
    "recvjson",
)
