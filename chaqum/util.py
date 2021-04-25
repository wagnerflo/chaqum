from collections import deque
from errno import EACCES,EBADF,EEXIST,ENOENT,ENOTDIR
from functools import wraps
from grp import getgrnam
from os import access,close,dup,getpid,strerror,sysconf,X_OK
from pathlib import Path
from platform import system as operating_system
from pwd import getpwnam
from resource import getrlimit,RLIMIT_NOFILE,RLIM_INFINITY
from subprocess import Popen,PIPE,DEVNULL

try:
    _MAXFD = sysconf("SC_OPEN_MAX")
except Exception:
    _MAXFD = 2048

def path_exists(path):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(ENOENT, f"{strerror(ENOENT)}: '{path}'")
    return path

def path_is_dir(path):
    path = Path(path).resolve()
    path_exists(path)
    if not path.is_dir():
        raise OSError(ENOTDIR, f"{strerror(ENOTDIR)}: '{path}'")
    return path

def path_is_file(path):
    path = Path(path).resolve()
    path_exists(path)
    if not path.is_file():
        raise OSError(ENOENT, f"Not a file: '{path}'")
    return path

def path_is_executable(path):
    path = Path(path).resolve()
    if not access(path, X_OK):
        raise OSError(EACCES, f"{strerror(EACCES)}: '{path}'")
    return path

def path_is_missing(path):
    path = Path(path).resolve()
    if path.exists():
        raise OSError(EEXIST, f"{strerror(EEXIST)}: '{path}'")
    return path

def run_once(func, *args, **kws):
    once = False
    @wraps(func)
    def wrapper():
        nonlocal once
        if not once:
            once = True
            return func(*args, **kws)
    return wrapper

def move_fd_above(tgt, fd):
    to_close = deque()
    while fd <= tgt:
        to_close.append(fd)
        fd = dup(fd)
    for c in to_close:
        close(c)
    return fd

def get_max_fd():
    _,hard_limit = getrlimit(RLIMIT_NOFILE)
    if hard_limit == RLIM_INFINITY:
        return _MAXFD
    return hard_limit

def get_max_open_fd():
    for fd in range(get_max_fd(), -1, -1):
        try:
            close(dup(fd))
            return fd
        except OSError as exc:
            if exc.errno != EBADF:
                raise

def get_open_fds_dumb():
    return set(range(get_max_open_fd() + 1))

if operating_system() == "FreeBSD":
    def get_open_fds():
        try:
            res = set()
            proc = Popen(
                ("/usr/bin/procstat", "-f", str(getpid())),
                stdout=PIPE, stderr=DEVNULL,
                universal_newlines=True
            )

            # verify header
            assert next(proc.stdout).split()[2] == "FD"

            # parse output
            for line in proc.stdout:
                try:
                    res.add(int(line.split()[2]))
                except (IndexError,ValueError):
                    pass

            # remove the fd of the pipe used by Popen
            res.remove(proc.stdout.fileno())
            proc.stdout.close()
            return res

        except:
            return get_open_fds_dumb()

else:
    get_open_fds = get_open_fds_dumb

def uid_or_user(uid):
    try:
        return int(uid)
    except ValueError:
        return getpwnam(uid).pw_uid

def gid_or_group(gid):
    try:
        return int(gid)
    except ValueError:
        return getgrnam(gid).gr_gid
