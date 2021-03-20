from errno import ENOENT,ENOTDIR,EACCES
from functools import wraps
from os import access,strerror,sysconf,X_OK
from pathlib import Path

try:
    MAXFD = sysconf('SC_OPEN_MAX')
except Exception:
    MAXFD = 256

def path_exists(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            ENOENT, f"{strerror(ENOENT)}: '{path}'"
        )
    return path

def path_is_dir(path):
    path = Path(path)
    path_exists(path)
    if not path.is_dir():
        raise OSError(
            ENOTDIR, f"{strerror(ENOTDIR)}: '{path}'"
        )
    return path

def path_is_file(path):
    path = Path(path)
    path_exists(path)
    if not path.is_file():
        raise OSError(
            ENOENT, f"Not a file: '{path}'"
        )
    return path

def path_is_executable(path):
    path = Path(path)
    if not access(path, X_OK):
        raise OSError(
            EACCES, f"{strerror(EACCES)}: '{path}'"
        )
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
