def main():
    import asyncio
    import json
    import logging
    import logging.config

    from argparse import ArgumentParser
    from daemon import DaemonContext
    from daemon.pidfile import TimeoutPIDLockFile
    from pkg_resources import resource_stream
    from sys import stdin,stdout,stderr

    from .manager import Manager
    from .util import (
        path_is_file,
        path_is_missing,
        get_max_open_fd,
        uid_or_user,
        gid_or_group,
    )

    prog = "chaqum"
    parser = ArgumentParser(prog=prog)
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help=(
            "Turn on verbose logging. Can be repeated up to two times "
            "for even more verbosity."
        )
    )
    parser.add_argument(
        "-l", "--log",
        default=None,
        help=(
            "Configure logging. Can be one of 'console' or "
            "'syslog[:[APPNAME][:FACILITY]]' to install sane defaults "
            "for logging to stderr or local Syslog respectivly. "
            "Otherwise the setting will be interpreted as the path to "
            "a JSON file containing the logging.config.dictConfig "
            "format. Defaults to 'syslog' if running as a daemon, "
            "'console' otherwise."
        )
    )
    parser.add_argument(
        "-d", "--daemonize", metavar="PIDFILE[:USER:GROUP]",
        help=(
            "Daemonize job manager. Use PIDFILE as lockfile to ensure "
            "only one instance is running. If USER and GROUP are "
            "specified run job manager under these credentials (this "
            "usually requires you to be root)."
        )
    )
    parser.add_argument(
        "-e", "--entry",
        default="entry",
        help=(
            "Set the entry script to run as the first in the job tree. "
            "Defaults to 'entry'."
        )
    )
    parser.add_argument(
        "directory",
        metavar="DIRECTORY",
        help=(
            "Path to the job tree. Needs to be a directory containing "
            "at least a executable file called 'entry' (or what -e is "
            "set to)."
        )
    )
    parser.add_argument(
        "arguments",
        metavar="ARGUMENT",
        nargs="*",
        help=(
            "Arguments passed on to the 'entry'/-e job."
        )
    )

    args = parser.parse_args()

    try:
        # create the job manager; constructur runs sanity checks for
        # the job tree directory
        mgr = Manager(
            path = args.directory,
            entry_script_name = args.entry,
        )

        # configure logging
        if args.log is None:
            args.log = "syslog" if args.daemonize else "console"

        appname = None
        facility = None

        if args.log.startswith("syslog"):
            args.log,_,appname = args.log.partition(":")
            appname,_,facility = appname.partition(":")

        if args.log in ("console", "syslog"):
            PACKAGE_NAME,_,_ = __name__.rpartition(".")
            fp = resource_stream(PACKAGE_NAME, f"logging.{args.log}.json")

        else:
            fp = path_is_file(args.log).open("rb")

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
                facility = facility or "daemon",
            ),
        )

        # set up logging now so any error in the logging configuration
        # end up on stderr before daemonizing
        logging.config.dictConfig(cfg)

        # set up a python-daemon context manager, that daemonizes us if
        # so requested
        pidfile = None
        uid = None
        gid = None
        daemon_stdin = None
        daemon_stdout = None
        daemon_stderr = None

        if args.daemonize:
            pidfile,sep,creds = args.daemonize.partition(":")
            pidfile = TimeoutPIDLockFile(path_is_missing(pidfile))
            if sep:
                uid,_,gid = creds.partition(":")
                if not uid or not gid:
                    raise Exception(f"Credentials '{creds}' invalid.")
                uid = uid_or_user(uid)
                gid = gid_or_group(gid)
        else:
            daemon_stdin = stdin
            daemon_stdout = stdout
            daemon_stderr = stderr

        ctx = DaemonContext(
            # we need to make sure any file descriptors opened by logging
            # handlers will not be closed
            files_preserve = list(range(3, get_max_open_fd() + 1)),
            # the boring rest
            detach_process = bool(args.daemonize),
            pidfile = pidfile,
            uid = uid,
            gid = gid,
            stdin = daemon_stdin,
            stdout = daemon_stdout,
            stderr = daemon_stderr,
        )

        # get a logger to use for exceptions
        log = logging.getLogger(prog)

    except Exception as exc:
        print(f"{prog}: {exc.__cause__ or exc}", file=stderr, flush=True)
        return 1

    except OSError as exc:
        print(f"{prog}: {exc.__cause__ or exc}", file=stderr, flush=True)
        return exc.errno

    except KeyboardInterrupt:
        print(file=stderr)

    try:
        with ctx:
            asyncio.run(mgr.run(*args.arguments))

    except Exception as exc:
        log.critical("Unhandled exception.", exc_info=True)
        return 1

    except OSError as exc:
        log.critical("Unhandled exception.", exc_info=True)
        return exc.errno

    except KeyboardInterrupt:
        print(file=stderr)
