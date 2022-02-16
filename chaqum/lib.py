import dataclasses
import json
import os
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

# hook current working directory into PYTHONPATH to make handling of
# imports across multi-directory job trees easier
if (cwd := os.getcwd()) not in sys.path:
    sys.path.insert(1, cwd)

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

    def waitrecv(self, timeout=None):
        (_,status), = waitrecv(self, timeout=timeout)
        return status

@dataclasses.dataclass(frozen=True)
class job:
    ident: str

    def wait(self, timeout=None):
        if res := waitjobs(self, timeout=timeout):
            return res[0][1]
        else:
            return job_status(False, True, None)

    def kill(self, timeout=None):
        if res := killjobs(self, timeout=timeout):
            return res[0][1]
        else:
            return job_status(False, True, None)

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

@dataclasses.dataclass(frozen=True)
class job_status:
    timeout: bool
    done: bool
    exitcode: int

def enqueue(script, *args, group=None, max_jobs=None, max_cpu=None, forget=False):
    _send_command(
        "enqueue",
        *() if group    is None else ("-g", group),
        *() if max_jobs is None else ("-m", max_jobs),
        *() if max_cpu  is None else ("-c", max_cpu),
        *() if not forget       else ("-F",),
        "--",
        script, *args
    )
    status,ident = _recv_response()
    if status != "S":
        raise Exception()
    return job(ident)

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
    status,results = _recv_response()
    if status != "S":
        raise Exception()
    if results is None:
        return
    results = iter(results.split(" "))
    results = dict(zip(results, results))
    for item in items:
        yield item,results.get(item.ident)

def _do_jobs(func, jobs, timeout):
    for job,result in _on_items(func, jobs, timeout):
        if result is None:
            yield job,None
        elif result == "T":
            yield job,job_status(True, None, None)
        elif result == "N":
            yield job,job_status(False, True, None)
        else:
            yield job,job_status(False, True, int(result))

def waitjobs(*jobs, timeout=None):
    return list(_do_jobs("waitjobs", jobs, timeout))

def killjobs(*jobs, timeout=None):
    return list(_do_jobs("killjobs", jobs, timeout))

def waitrecv(*messages, timeout=None):
    return [
        (msg,result == "R")
        for msg,result in _on_items("waitrecv", messages, timeout)
    ]

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

if parent := os.environ.get("CHAQUM_PARENT"):
    parent = job(parent)

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
    "parent",
)
