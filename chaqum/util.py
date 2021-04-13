from errno import ENOENT,ENOTDIR,EACCES
from functools import wraps
from os import access,strerror,sysconf,X_OK
from pathlib import Path
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
