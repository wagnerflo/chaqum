def main():
    import asyncio
    import logging

    from argparse import ArgumentParser
    from os import access,X_OK
    from pathlib import Path
    from sys import stderr

    from .logging import Bla
    from .manager import Manager

    parser = ArgumentParser()
    parser.add_argument(
        'directory',
        type=Path,
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

    init = args.directory / 'init'

    if not init.exists():
        err(f"Path '{args.directory}' contains no 'init' job.")
        return 1

    if not access(init, X_OK):
        err(f"Job file '{init}' is not executable.")
        return 1

    # configure logging
    root = logging.getLogger(None)
    root.setLevel(logging.INFO)
    root.addHandler(Bla())

    try:
        mgr = Manager(args.directory)
        asyncio.run(mgr.run())
    except KeyboardInterrupt:
        print()
