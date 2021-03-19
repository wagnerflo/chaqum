import os
import re

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from errno import ENOENT,ENOTDIR,EACCES
from pathlib import Path

try:
    MAXFD = os.sysconf('SC_OPEN_MAX')
except Exception:
    MAXFD = 256

def optstring(optstr):
    def decorator(func):
        func.optstring = optstr
        return func
    return decorator

_RE_INTERVAL = re.compile(
    r'''
        ^
        (?P<seconds>\d+)s |
        (?P<minutes>\d+)m |
        (?P<hours>\d+)h   |
        (?P<days>\d+)d    |
        (?P<weeks>\d+)w
    ''', re.X
)

def parse_interval(interval):
    kws = {}
    while interval:
        match = _RE_INTERVAL.match(interval)
        if match is None:
            raise Exception('Invalid interval specifier.')
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

    raise Exception('Invalid cron specifier.')

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

def path_exists(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            ENOENT, f"{os.strerror(ENOENT)}: '{path}'"
        )
    return path

def path_is_dir(path):
    path = Path(path)
    path_exists(path)
    if not path.is_dir():
        raise OSError(
            ENOTDIR, f"{os.strerror(ENOTDIR)}: '{path}'"
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
    if not os.access(path, os.X_OK):
        raise OSError(
            EACCES, f"{os.strerror(EACCES)}: '{path}'"
        )
    return path
