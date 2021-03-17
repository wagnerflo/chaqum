import dataclasses
import shlex

stderr = open(2, 'wb')
pipe_wr = open(3, 'wb')
pipe_rd = open(4, 'rb')

def _send_log(lvl, sep, args):
    stderr.write(lvl)
    stderr.write(b'\x1f')
    stderr.write(sep.join(str(arg) for arg in args).encode())
    stderr.write(b'\n')
    stderr.flush()

def _send_command(*parts):
    pipe_wr.write(shlex.join(str(part) for part in parts).encode())
    pipe_wr.write(b'\n')
    pipe_wr.flush()

def _recv_response():
    status,*rest = pipe_rd.readline().decode().strip().split(' ', 1)
    return status,rest[0] if rest else None

class log:
    @staticmethod
    def critical(*args, sep=' '):
        _send_log(b'C', sep, args)

    @staticmethod
    def error(*args, sep=' '):
        _send_log(b'E', sep, args)

    @staticmethod
    def warning(*args, sep=' '):
        _send_log(b'W', sep, args)

    @staticmethod
    def info(*args, sep=' '):
        _send_log(b'I', sep, args)

    @staticmethod
    def debug(*args, sep=' '):
        _send_log(b'D', sep, args)

@dataclasses.dataclass(frozen=True)
class job:
    ident: str
    group: str

    def wait(self, timeout=None):
        return waitjobs(self)

def enqueue(script, *args, group=None, max_jobs=None, max_load=None):
    _send_command(
        'enqueue',
        *() if group is None else ('-g', group),
        *() if max_jobs is None else ('-m', max_jobs),
        *() if max_load is None else ('-l', max_load),
        '--',
        script, *args
    )
    status,ident = _recv_response()
    if status != 'S':
        raise Exception()
    return job(ident, group)

def _repeat(script, args, *opts):
    _send_command(
        'repeat',
        *opts,
        '--',
        script, *args
    )
    status,_ = _recv_response()
    if status != 'S':
        raise Exception()

def interval(script, *args,
             seconds=0, minutes=0, hours=0, days=0, weeks=0):
    return _repeat(
        script, args,
        '-i', f'{seconds}s{minutes}m{hours}h{days}d{weeks}w',
    )

def cron(script, *args,
         second='*', minute='*', hour='*', day='*', month='*', day_of_week='*'):
    return _repeat(
        script, args,
        '-c', f'{second} {minute} {hour} {day} {month} {day_of_week}',
    )

def waitjobs(*jobs, timeout=None):
    _send_command(
        'wait',
        *() if timeout is None else ('-t', timeout),
        '--',
        *(job.ident for job in jobs)
    )
    status,done = _recv_response()
    if status not in ('T', 'S'):
        raise Exception()
    done = done.split(' ')
    return (
        status == 'T',
        [job for job in jobs if job.ident in done]
    )

__all__ = (
    'log',
    'enqueue',
    'interval',
    'cron',
    'waitjobs',
)
