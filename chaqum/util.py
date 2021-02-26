import functools
import inspect
import re

def ignore(excs):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args, **kws):
                try:
                    return await func(*args, **kws)
                except excs:
                    pass
        else:
            @functools.wraps(func)
            def wrapper(*args, **kws):
                try:
                    return func(*args, **kws)
                except excs:
                    pass
        return wrapper
    return decorator

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
        (?P<days>\d+)s    |
        (?P<weeks>\d+)w
    ''', re.X
)

def parse_interval(interval):
    result = {}
    while interval:
        match = _RE_INTERVAL.match(interval)
        if match is None:
            return
        result.update(
            (k,int(v)) for k,v in match.groupdict().items()
            if v is not None
        )
        interval = interval[match.end():]
    return result
