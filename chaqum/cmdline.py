def main():
    import asyncio
    import json
    import logging
    import logging.config

    from argparse import ArgumentParser
    from pkg_resources import resource_stream
    from sys import stderr

    from .manager import Manager
    from .util import path_is_file

    prog = 'chaqum'
    parser = ArgumentParser(prog=prog)
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
        '-l', '--log',
        default='console',
        help=(
            "Can be one of 'console' (the default if this option is "
            "not given) or 'syslog[:[APPNAME][:FACILITY]]' to install "
            "sane defaults for logging to stderr or local Syslog "
            "respectivly. Otherwise the setting will be interpreted as "
            "a path to a JSON file containing the "
            "Python logging.config.dictConfig format."
        )
    )
    parser.add_argument(
        'directory',
        help=(
            "Path to the job tree. Needs to be a directory containing "
            "at least a executable file called 'entry'."
        )
    )
    parser.add_argument(
        'arguments',
        nargs='*',
        help=(
            "Arguments passed on to the 'entry' job."
        )
    )

    args = parser.parse_args()

    try:
        # create the job manager; constructur runs sanity checks for
        # the job tree directory
        mgr = Manager(args.directory)

        # configure logging
        appname = None
        facility = None

        if args.log.startswith('syslog'):
            args.log,_,appname = args.log.partition(':')
            appname,_,facility = appname.partition(':')

        if args.log in ('console', 'syslog'):
            PACKAGE_NAME,_,_ = __name__.rpartition('.')
            fp = resource_stream(PACKAGE_NAME, f"logging.{args.log}.json")

        else:
            fp = path_is_file(args.log).open('rb')

        with fp:
            cfg = json.load(fp)

        level_root = logging.INFO
        level_apscheduler = logging.WARN

        if args.verbose >= 1:
            level_root = logging.DEBUG

        if args.verbose >= 2:
            level_apscheduler = logging.DEBUG

        cfg.update(
            levels = dict(
                root = level_root,
                apscheduler = level_apscheduler,
            ),
            syslog = dict(
                appname = appname or prog,
                facility = facility or 'daemon',
            ),
        )

        logging.config.dictConfig(cfg)

        # start the job mananger
        asyncio.run(mgr.run(*args.arguments))

    except Exception as exc:
        print(f"{prog}: {exc}", file=stderr, flush=True)
        return 1

    except OSError as exc:
        print(f"{prog}: {exc}", file=stderr, flush=True)
        return exc.errno

    except KeyboardInterrupt:
        print(file=stderr)
