# Design considerations

## Be unixy

- Each job is a process.
- Job process inherits closed standard input from manager.
- Manager redirects job process standard output and error to log.
- Job manager and job process communicate using file descriptors 3 & 4.
  Commands are always initiated by job process and answered by manager.
- One line per command/answer. Shell like escaping.
- Simple library for POSIX shell, Python and Perl to make wrap this.

## Commands

- `enqueue`: Add a one time job to the queue. Returns a internal job ID
  that is valid even before an actual job process has been spawned.
- `repeat`: Setup a repeatedly run job. Support cron-like and interval
  starting conditions.
- `wait`: Block and wait for completion of one or more jobs. Expects a
  return condition (`-a` only when all completed, `-f` as soon as first
  completed) and a list of job IDs.

## Job trees and composition

- Job trees are represented as a directory. One instance of `chaqum`
  will manage one job tree and associated jobs.
- All executable files inside a job tree are considered possible jobs.
- Every `chaqum` instance will on startup spawn a job called `init`.
- Usually the `init` job will contain repeat jobs that are scanners
  waiting for some external (filesystem, database) trigger. They will
  enqueue new jobs.
- The jobs themselves can be subdivided into smaller units of work that
  are spawned by the main job process.

## Support load control

- Jobs can be grouped when they are registered:
  `enqueue -g convert -- process [arguments]`.
- Groups are automatically created when they are first encountered.
- Per group maximum processes number (`-m 6`)
- Small selection of barriers to delay spawning jobs in a group until
  system load permits (possibly `-c 0.7` = only spawn if CPU less than
  70% idle; use `vmstat`).
- There are no globals. `init` or jobs spawned by it will have to take
  care to set up groups and limit.

## Some ideas and assorted links

- [nq: queue utilities](https://github.com/leahneukirchen/nq).
- [load average calculation](https://forums.freebsd.org/threads/load-average-calculation.72066/).
- File watching on FreeBSD:
  [sysutils/inotify-tools](https://www.freshports.org/sysutils/inotify-tools/),
  [devel/py-pyinotify](https://www.freshports.org/devel/py-pyinotify/).
