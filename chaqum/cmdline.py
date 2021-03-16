def main():
    import asyncio
    import logging

    from argparse import ArgumentParser
    from noblklog import (
        AsyncStreamHandler,
        AsyncSyslogHandler,
    )
    from pathlib import Path
    from sys import stderr

    from .util import check_script
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
        type=Path,
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

    def err(*args):
        print(*args, file=stderr, flush=True)

    if not args.directory.exists():
        err(f"{prog}: Path '{args.directory}' does not exist.")
        return 1

    if not args.directory.is_dir():
        err(f"{prog}: Path '{args.directory}' is no directory.")
        return 1

    try:
        check_script(args.directory, 'init')

    except Exception as exc:
        err(f"{prog}: {exc}")
        return 1

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
        mgr = Manager(args.directory)
        asyncio.run(mgr.run(*args.arguments))
    except KeyboardInterrupt:
        print(file=stderr)
