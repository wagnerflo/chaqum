from errno import EACCES,EBADF,EEXIST,ENOENT,ENOTDIR
from functools import wraps
from grp import getgrnam
from os import access,close,dup,strerror,sysconf,X_OK
from pathlib import Path
from pwd import getpwnam
from resource import getrlimit,RLIMIT_NOFILE,RLIM_INFINITY

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
