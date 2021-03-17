def main():
    import asyncio
    import logging

    from argparse import ArgumentParser
    from noblklog import (
        AsyncStreamHandler,
        AsyncSyslogHandler,
    )
    from sys import stderr

    from .manager import Manager

    prog = 'chaqum'
    parser = ArgumentParser(prog=prog)
    AsyncSyslogHandler.argparse_add_argument(
        parser, '-s', '--syslog',
        facility='daemon',
        appname=prog,
    )
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help=(
            "Turn on verbose logging. Can be repeated up to two times "
            "for even more verbosity."
        )
    )
    parser.add_argument(
        'directory',
        help=(
            "Path to the job tree. Minimally required to a directory "
            "containing a executable file called 'init'."
        )
    )
    parser.add_argument(
        'arguments',
        nargs='*',
        help=(
            "Arguments passed on to the 'init' job."
        )
    )

    args = parser.parse_args()

    try:
        # create the job manager; constructur runs sanity checks for
        # the job tree directory
        mgr = Manager(args.directory)

    except Exception as exc:
        print(f"{prog}: {exc}", file=stderr, flush=True)
        return 1

    except OSError as exc:
        print(f"{prog}: {exc}", file=stderr, flush=True)
        return exc.errno

    lvl_root = logging.INFO
    lvl_apsched = logging.WARN

    if args.verbose >= 1:
        lvl_root = logging.DEBUG

    if args.verbose >= 2:
        lvl_apsched = logging.DEBUG

    if args.syslog:
        handler = args.syslog()
        prefix = ''

    else:
        handler = AsyncStreamHandler()
        prefix = '[ %(name)-15s ] %(levelname).1s '

    logging.basicConfig(
        level = lvl_root,
        handlers = [handler],
        format = f'{prefix}%(message)s',
    )

    logging.getLogger('apscheduler').setLevel(lvl_apsched)

    try:
        asyncio.run(mgr.run(*args.arguments))
    except KeyboardInterrupt:
        print(file=stderr)
