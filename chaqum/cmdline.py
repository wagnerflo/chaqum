def main():
    import asyncio
    import logging

    from argparse import ArgumentParser
    from noblklog import (
        AsyncStreamHandler,
        AsyncSysLogHandler,
    )
    from pathlib import Path
    from sys import stderr

    from .util import check_script
    from .manager import Manager

    parser = ArgumentParser()
    parser.add_argument(
        'directory',
        type=Path,
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
        err(f"Path '{args.directory}' does not exist.")
        return 1

    if not args.directory.is_dir():
        err(f"Path '{args.directory}' is no directory.")
        return 1

    try:
        check_script(args.directory, 'init')

    except Exception as exc:
        err(exc)
        return 1

    # configure logging
    root = logging.getLogger(None)
    root.setLevel(logging.INFO)
    #root.addHandler(AsyncSysLogHandler())
    root.addHandler(AsyncStreamHandler())

    try:
        mgr = Manager(args.directory)
        asyncio.run(mgr.run(*args.arguments))
    except KeyboardInterrupt:
        print(file=stderr)
