#!/usr/bin/env python3
'''
Program to rename, remove, or copy files and directories using your
editor. Will use git to action the rename and remove if run within a git
repository.
'''
# Author: Mark Blakeney, May 2019.

import sys
import os
import re
import argparse
import subprocess
import tempfile
import itertools
import shlex
import pathlib
import datetime
import textwrap
from collections import OrderedDict
from shutil import rmtree, copy2, copytree

# Some constants
PROG = pathlib.Path(sys.argv[0]).stem
CNFFILE = pathlib.Path(os.getenv('XDG_CONFIG_HOME', '~/.config'),
        f'{PROG}-flags.conf')
EDITOR = PROG.upper() + '_EDITOR'
SUFFIX = '.sh'

# The temp dir we will use in the dir of each target move
TEMPDIR = '.tmp-' + PROG

ACTION_LINE_REGEX = r'^([drc]) ([^→]+)(?: → ([^→]*))?$'
COMMENT_LINE_REGEX = r'^\s*#'
WORKING_DIR_REGEX = r'^\s*#\s*workdir:\s*(\S+)$'

args = None
gitfiles = set()
actions_file = None
applied_actions = []
failed_actions = []


class Colorization:

    def __init__(self, use_color):
        if not use_color:
            self.RST = ''
            self.RED = ''
            self.GRN = ''
            self.YLW = ''
            self.BLU = ''
            self.MGT = ''
            self.CYN = ''
            self.WHT = ''
            self.BLD = ''
            self.FNT = ''
            self.NRM = ''
            self.action_colors = {
                    'd': {"col": '', "name": 'Deleted'},
                    'r': {"col": '', "name": 'Renamed'},
                    'c': {"col": '', "name": 'Copied '},
                    }
        else:
            self.RST = '\033[0m'
            self.RED = '\033[31m'
            self.GRN = '\033[32m'
            self.YLW = '\033[33m'
            self.BLU = '\033[34m'
            self.MGT = '\033[35m'
            self.CYN = '\033[36m'
            self.WHT = '\033[37m'
            self.BLD = '\033[1m'
            self.FNT = '\033[2m'
            self.NRM = '\033[22m'
            self.action_colors = {
                    'd': {"col": self.MGT, "name": 'Deleted'},
                    'r': {"col": self.YLW, "name": 'Renamed'},
                    'c': {"col": self.CYN, "name": 'Copied '},
                    }

    def bright(self, col):
        'Return a color string with the bright version of the given color'
        if col == '':
            return '';
        else:
            number = re.sub('^\033\\[(\\d+)m', '\\1', col)
            return '\033['+str(int(number)+60)+'m'

color = Colorization(False)


def sout(*args, **kwargs):
    'Print a message to stdout'
    print(*args, file=sys.stdout, **kwargs)

def serr(*args, no_color=False, **kwargs):
    '''
    Print a message to stderr.

    The message will be colored in bright red (except 'no_color' is True)

    Parameters:
        no_color (bool): Don't automatically color in red. Useful when
                         customizing the colorization of the output.
                         Default: False
    '''
    if no_color:
        print(*args, file=sys.stderr, **kwargs)
    else:
        print(f'{color.bright(color.RED)}', *args, f'{color.RST}', file=sys.stderr, **kwargs)

def run(cmd):
    'Run given command and return stdout, stderr'
    stdout = ''
    stderr = ''
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True,
                stderr=subprocess.PIPE, universal_newlines=True)
    except Exception as e:
        stderr = str(e)
    else:
        if res.stdout:
            stdout = res.stdout.strip()
        if res.stderr:
            stderr = res.stderr.strip()

    return stdout, stderr

def remove(path, git=False, trash=False, recurse=False):
    'Delete given file/directory'
    if not recurse and not path.is_symlink() and path.is_dir() and \
            any(path.iterdir()):
        return 'Directory not empty'

    if git:
        ropt = '-r' if recurse else ''
        out, err = run(f'git rm -f {ropt} "{path}"')
        return f'git error: {err}' if err else None

    if trash:
        out, err = run(f'{args.trash_program} "{path}"')
        return f'{args.trash_program} error: {err}' if err else None

    if recurse:
        try:
            rmtree(str(path))
        except Exception as e:
            return str(e)
    else:
        try:
            if not path.is_symlink() and path.is_dir():
                path.rmdir()
            else:
                path.unlink()
        except Exception as e:
            return str(e)

    return None

def rename(pathsrc, pathdest, is_git=False):
    'Rename given pathsrc to pathdest'
    if is_git:
        out, err = run(f'git mv -f "{pathsrc}" "{pathdest}"')
        if err:
            serr(f'Rename "{pathsrc}" git mv ERROR: {err}')
    else:
        pathsrc.replace(pathdest)

class Path:
    'Class to manage each instance of a file/dir'
    paths = []
    tempdirs = set()

    def __init__(self, path):
        'Class constructor'
        self.path = path
        self.newpath = None
        self.temppath = None
        self.copies = []
        self.is_dir = path.is_dir()
        self.diagrepr = str(self.path)
        self.is_git = self.diagrepr in gitfiles

        self.linerepr = self.diagrepr if self.diagrepr.startswith('/') \
                else './' + self.diagrepr
        if self.is_dir and not self.diagrepr.endswith('/'):
            self.linerepr += '/'
            self.diagrepr += '/'

    @staticmethod
    def inc_path(path):
        'Find next unique file name'
        # Iterate forever, there can only be a finite number of existing
        # paths
        name = path.name
        for c in itertools.count():
            if not path.is_symlink() and not path.exists():
                return path
            path = path.with_name(name + ('~' if c <= 0 else f'~{c}'))

    def copy(self, pathdest):
        'Copy given pathsrc to pathdest'
        func = copytree if self.is_dir else copy2
        try:
            func(self.newpath, pathdest)
        except Exception as e:
            return str(e)
        return None

    def rename_temp(self):
        'Move this path to a temp place in advance of final move'
        tempdir = self.newpath.parent / TEMPDIR
        try:
            tempdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return f'Create dir for {self.diagrepr} ERROR: Can not write in {tempdir.parent}'
        else:
            self.temppath = self.inc_path(tempdir / self.newpath.name)
            self.tempdirs.add(tempdir)
            rename(self.path, self.temppath, self.is_git)

    def restore_temp(self):
        'Restore temp path to final destination'
        if not self.temppath:
            return False
        self.newpath = self.inc_path(self.newpath)
        rename(self.temppath, self.newpath, self.is_git)
        return True

    def sort_name(self):
        'Return name for sort'
        return str(self.path)

    def sort_time(self):
        'Return time for sort'
        return self.path.stat().st_mtime

    def sort_size(self):
        'Return size for sort'
        return self.path.stat().st_size

    @classmethod
    def remove_temps(cls):
        'Remove all the temp dirs we created in rename_temp() above'
        for p in cls.tempdirs:
            remove(p, git=None, trash=None, recurse=True)

        cls.tempdirs.clear()

    @classmethod
    def append(cls, path):
        'Add a single file/dir to the list of paths'
        # Filter out files/dirs if asked
        if args.files:
            if path.is_dir():
                return
        elif args.dirs:
            if not path.is_dir():
                return

        # Filter out links if asked
        if args.nolinks and path.is_symlink():
            return

        cls.paths.append(cls(path))

    @classmethod
    def get(cls, name):
        'Get the file/dir with the given name'
        for p in cls.paths:
            if p.path.name == name:
                return p
        return None

    @classmethod
    def add(cls, name, expand):
        'Add file[s]/dir[s] to the list of paths'
        path = pathlib.Path(name)
        if not path.exists():
            sys.exit(f'ERROR: {name} does not exist')

        if expand and path.is_dir():
            for child in sorted(path.iterdir()):
                if args.all or not child.name.startswith('.'):
                    cls.append(child)
        else:
            cls.append(path)

    @classmethod
    def writefile(cls, fp):
        'Write the file for user to edit'
        fp.writelines(f'{i}\t{p.linerepr}\n' for i, p in
                enumerate(cls.paths, 1))

    @classmethod
    def readfile(cls, fp):
        'Read the list of files/dirs as edited by user'
        for count, line in enumerate(fp, 1):
            # Skip blank or commented lines
            rawline = line.rstrip('\n\r')
            line = rawline.lstrip()
            if not line or line[0] == '#':
                continue

            try:
                n, pathstr = line.split(maxsplit=1)
            except Exception:
                sys.exit(f'ERROR: line {count} invalid:\n{rawline}')
            try:
                num = int(n)
            except Exception:
                sys.exit(f'ERROR: line {count} number {n} invalid:\n{rawline}')

            if num <= 0 or num > len(cls.paths):
                sys.exit(f'ERROR: line {count} number {num} '
                        f'out of range:\n{rawline}')

            path = cls.paths[num - 1]

            if len(pathstr) > 1:
                pathstr = pathstr.rstrip('/')

            newpath = pathlib.Path(pathstr)

            if path.newpath:
                if newpath != path.path:
                    path.copies.append(newpath)
            else:
                path.newpath = newpath

    @classmethod
    def read_actionsfile(cls, fp):
        'Read the paths from an actions file'
        workdir_was_specified = False
        for count, line in enumerate(fp, 1):
            # check the working directory
            match = re.search(WORKING_DIR_REGEX, line)
            if match:
                if workdir_was_specified:
                    serr(f'{color.BLD}workdir was specified multiple times in the actions file!\n'
                         f'Cowardly refusing to proceed…\n'
                         f'  workdir 1: {prev_workdir}\n'
                         f'  workdir 2: {match[1]}')
                    sys.exit(2)
                workdir_was_specified = True
                prev_workdir = match[1]
                cur_workdir = os.getcwd()
                if prev_workdir != cur_workdir:
                    confirmation = input(f'{color.bright(color.RED)}The current directory \n'
                                         f'  "{color.BLD}{cur_workdir}{color.NRM}"\n'
                                         f'is different than the workdir the actions file was generated in:\n'
                                         f'  "{color.BLD}{prev_workdir}{color.NRM}"\n'
                                         f'Executing the actions file in different directory may lead to unexpected results.\n'
                                         f'\nProceed anyway? {color.RST}')
                    if confirmation not in ['y', 'Y']:
                        sout('Aborting as requested…')
                        sys.exit(0)

            # Skip blank or commented lines
            rawline = line.rstrip('\n\r')
            line = rawline.lstrip()
            if not line or line[0] == '#':
                continue

            match = re.search(ACTION_LINE_REGEX, line)
            if match is None:
                to_failed_actions(line, None, None, f'unparsable line: {line}')
                if line.count('→') > 0:
                    serr(f'The arrow character (→) is not supported in file names when using an actions-file.')
                continue

            action    = match[1]
            file_from = match[2]
            file_to   = pathlib.Path(match[3]) if action != 'd' else None

            path = Path.get(file_from)
            if path is None:
                Path.add(file_from, False)
                path = Path.paths[-1]
            if action == 'r':
                path.newpath = file_to
            elif action == 'c':
                if not path.newpath:
                    path.newpath = pathlib.Path(file_from)
                path.copies.append(file_to)
            elif action == 'd':
                pass
            else:
                serr(f'unsupported action: {action}')
                continue


def editfile(filename):
    'Run the editor command'
    # Use explicit editor or choose default
    editor = os.getenv(EDITOR) or os.getenv('VISUAL') or \
            os.getenv('EDITOR') or 'vi'
    editcmd = shlex.split(editor) + [str(filename)]

    # Run the editor ..
    with open('/dev/tty') as tty:
        res = subprocess.run(editcmd, stdin=tty)

    # Check if editor returned error
    if res.returncode != 0:
        sys.exit(f'ERROR: {editor} returned {res.returncode}')

def main(argv=[]):
    'Main code'
    global args

    # Process command line options
    opt = argparse.ArgumentParser(description=__doc__.strip(),
            epilog='Note you can set default starting options in '
            f'{CNFFILE}. The negation options (i.e. the --no-* options '
            'and their shortforms) allow you to temporarily override your '
            'defaults.')
    opt.add_argument('-a', '--all', action='store_true',
            help='include all (including hidden) files')
    opt.add_argument('-A', '--no-all', dest='all', action='store_false',
            help='negate the -a/--all/ option')
    opt.add_argument('-r', '--recurse', action='store_true',
            help='recursively remove any files and directories in '
            'removed directories')
    opt.add_argument('-R', '--no-recurse', dest='recurse', action='store_false',
            help='negate the -r/--recurse/ option')
    opt.add_argument('-q', '--quiet', action='store_true',
            help='do not print rename/remove/copy actions')
    opt.add_argument('-Q', '--no-quiet', dest='quiet', action='store_false',
            help='negate the -q/--quiet/ option')
    opt.add_argument('-G', '--no-git', dest='git',
            action='store_const', const=0,
            help='do not use git if invoked within a git repository')
    opt.add_argument('-g', '--git', dest='git',
            action='store_const', const=1,
            help='negate the --no-git option and DO use automatic git')
    opt.add_argument('-t', '--trash', action='store_true',
            help='use trash program to do deletions')
    opt.add_argument('-T', '--no-trash', dest='trash', action='store_false',
            help='negate the -t/--trash/ option')
    opt.add_argument('--trash-program', default='trash-put',
            help='trash program to use, default="%(default)s"')
    opt.add_argument('-c', '--no-color', action='store_true',
            help='do not color rename/remove/copy messages')
    opt.add_argument('-d', '--dirnames', action='store_true',
            help='edit given directory names directly, not their contents')
    grp = opt.add_mutually_exclusive_group()
    grp.add_argument('-F', '--files', action='store_true',
            help='only show/edit files')
    grp.add_argument('-D', '--dirs', action='store_true',
            help='only show/edit directories')
    opt.add_argument('-L', '--nolinks', action='store_true',
            help='ignore all symlinks')
    opt.add_argument('-N', '--sort-name', dest='sort',
            action='store_const', const=1,
            help='sort paths in file by name, alphabetically')
    opt.add_argument('-i', '--input-from', dest='actions_file',
            help='read actions to execute from an the given actions file')
    opt.add_argument('-I', '--sort-time', dest='sort',
            action='store_const', const=2,
            help='sort paths in file by time, oldest first')
    opt.add_argument('-S', '--sort-size', dest='sort',
            action='store_const', const=3,
            help='sort paths in file by size, smallest first')
    opt.add_argument('-E', '--sort-reverse', action='store_true',
            help='sort paths (by name/time/size) in reverse')
    opt.add_argument('-X', '--group-dirs-first', dest='group_dirs',
            action='store_const', const=1,
            help='group directories first (including when sorted)')
    opt.add_argument('-Y', '--group-dirs-last', dest='group_dirs',
            action='store_const', const=0,
            help='group directories last (including when sorted)')
    opt.add_argument('-Z', '--no-group-dirs', dest='group_dirs',
            action='store_const', const=-1,
            help='negate the options to group directories')
    opt.add_argument('--suffix', default=SUFFIX,
            help='specify suffix for editor file, default="%(default)s"')
    opt.add_argument('args', nargs='*',
            help='file|dir, or "-" for stdin')

    # Merge in default args from user config file. Then parse the
    # command line.
    cnflines = ''
    cnffile = CNFFILE.expanduser()
    if cnffile.exists():
        with cnffile.open() as fp:
            cnflines = [re.sub(r'#.*$', '', line).strip() for line in fp]
        cnflines = ' '.join(cnflines).strip()

    args = opt.parse_args(shlex.split(cnflines) + argv)

    # FIXME: Check if terminal is color capable
    if not args.no_color:
        global color
        color = Colorization(True)

    # Check if we are in a git repo
    if args.git != 0:
        out, err = run('git ls-files')
        if err and args.git:
            print(f'Git invocation error: {err}', file=sys.stderr)
        if out:
            gitfiles.update(out.splitlines())

        if args.git and not gitfiles:
            opt.error('must be within a git repo to use -g/--git option')

    # If an actions file was specified, run non-interactively and execute
    # the actions specified in that file. Otherwise run interactively as usual.
    if args.actions_file is None:
        # Set input list to a combination of arguments and stdin
        filelist = args.args
        if sys.stdin.isatty():
            if not filelist:
                filelist.append('.')
        elif '-' not in filelist:
            filelist.insert(0, '-')
        run_interactively(filelist)
    else:
        run_noninteractively(args.actions_file)

    return perform_actions(Path.paths)

def run_noninteractively(actions_file):
    'Execute an actions file noninteractive use'
    fpath = pathlib.Path(actions_file)
    if not fpath.exists():
        serr(f'ERROR: {fpath} does not exist.')
        # FIXME: Exit code 3 is not defined and never tested
        sys.exit(3)

    try:
        with fpath.open() as fp:
            Path.read_actionsfile(fp)
    except OSError as err:
        serr(f'ERROR: Reading actions_file {fpath} failed: {err}')
        sys.exit(3)

def run_interactively(filelist):
    'Open the list of files in the editor for interactive use'
    # Iterate over all (unique) inputs to get a list of files/dirs
    for name in OrderedDict.fromkeys(filelist):
        if name == '-':
            for line in sys.stdin:
                name = line.rstrip('\n\r')
                if name != '.':
                    Path.add(line.rstrip('\n\r'), False)
        else:
            Path.add(name, not args.dirnames)

    # Sanity check that we have something to edit
    if not Path.paths:
        desc = 'files' if args.files else \
                'directories' if args.dirs else 'files or directories'
        print(f'No {desc}.')
        return

    if args.sort == 1:
        Path.paths.sort(key=Path.sort_name, reverse=args.sort_reverse)
    elif args.sort == 2:
        Path.paths.sort(key=Path.sort_time, reverse=args.sort_reverse)
    elif args.sort == 3:
        Path.paths.sort(key=Path.sort_size, reverse=args.sort_reverse)

    if args.group_dirs is not None and args.group_dirs >= 0:
        ldirs, lfiles = [], []
        for path in Path.paths:
            (ldirs if path.is_dir else lfiles).append(path)
        Path.paths = ldirs + lfiles if args.group_dirs else lfiles + ldirs

    # Create a temp file for the user to edit then read the lines back
    with tempfile.TemporaryDirectory() as fdir:
        fpath = pathlib.Path(fdir, f'{PROG}{args.suffix}')
        with fpath.open('w') as fp:
            Path.writefile(fp)
        editfile(fpath)
        with fpath.open() as fp:
            Path.readfile(fp)

    # Reduce paths to only those that were removed or changed by the user
    paths = [p for p in Path.paths if p.path != p.newpath or p.copies]
    Path.paths = paths

def perform_actions(paths):
    'Start the actual renaming/deleting/copying'
    # Pass 1: Rename all moved files & dirs to temps, delete all removed
    # files.

    for p in paths:
        # Lazy eval the next path value
        p.note = ' recursively' if p.is_dir and any(p.path.iterdir()) else ''

        if p.newpath:
            if p.newpath != p.path:
                err = p.rename_temp()
                if err:
                    to_failed_actions('r', p.path, p.newpath, f'Delete "{p.diagrepr}" ERROR: {err}')
        elif not p.is_dir:
            err = remove(p.path, p.is_git, args.trash)
            if err:
                to_failed_actions('d', p.path, None, f'Delete "{p.diagrepr}" ERROR: {err}')
            else:
                applied_actions.append(('d', p.diagrepr))

    # Pass 2: Delete all removed dirs, if empty or recursive delete.
    for p in paths:
        if p.is_dir and not p.newpath:
            if remove(p.path, p.is_git, args.trash, args.recurse) is None:
                # Have removed, so flag as finished for final dirs pass below
                p.is_dir = False
                applied_actions.append(('d', f"{p.diagrepr}{p.note}"))

    # Pass 3. Rename all temp files and dirs to final target, and make
    # copies.
    for p in paths:
        appdash = '/' if p.is_dir else ''
        if p.restore_temp():
            applied_actions.append(('r', p.diagrepr, f"{p.newpath}{appdash}"))

        for c in p.copies:
            err = p.copy(c)
            if err:
                to_failed_actions('c', p.path, c, f'Copy   "{p.diagrepr}" to "{c}{appdash}"{p.note} ERROR: {err}')
            else:
                applied_actions.append(('c', p.diagrepr, f"{c}{appdash}{p.note}"))

    # Remove all the temporary dirs we created
    Path.remove_temps()

    # Pass 4. Delete all remaining dirs
    for p in paths:
        if p.is_dir and not p.newpath:
            err = remove(p.path, p.is_git, args.trash, args.recurse)
            if err:
                to_failed_actions('d', p.path, None, f'Delete "{p.diagrepr}" ERROR: {err}')
            else:
                applied_actions.append(('d', f"{p.diagrepr}{p.note}"))

    # Now print the applied operations
    print_executed_actions()

    # Show a prominent error message indicating that some actions failed
    # and how to reexecute these.
    if failed_actions:
        write_actions_file()
        serr(f"\nSome or all files could not be processed. An actions-file was written for them to \n"
             f"  {color.BLD}{actions_file}{color.NRM}\n"
             f"You can try to reapply those actions with \n"
             f"  {color.BLD}edir -i {actions_file}{color.NRM}")


    # Return status code 0 = all good, 1 = some bad, 2 = all bad.
    return (1 if len(applied_actions) > 0 else 2) if len(failed_actions) > 0 else 0


def print_executed_actions():
    # This is an ugly hack. The number of successful chanegs should be
    # checked elsewhere
    if args.quiet:
        return
    col2 = [a[1] for a in applied_actions]
    col2len = 0 if col2 == [] else len(max(col2, key=len))
    for action in applied_actions:
        act = color.action_colors[action[0]]["name"]
        col = color.action_colors[action[0]]["col"]
        source = f'"{action[1]}"'
        source = f'{source: <{col2len+2}}'
        target = None
        if action[0] != 'd':
            target = action[2]
        if target is None:
            sout(f'{col}{act}  {color.bright(col)}{color.BLD}{source}{color.NRM}{color.RST}')
        else:
            sout(f'{col}{act}  {color.bright(col)}{color.BLD}{source}{color.NRM}  →  "{color.BLD}{target}{color.NRM}{color.RST}"')


def to_failed_actions(action, source_path, target_path, msg):
    """Record a failed action and write an error message"""
    failed_actions.append((action, source_path, target_path))
    serr(msg)


def write_actions_file():
    """Write the failed actions into an actions file"""
    create_actions_file()
    for failed_action in failed_actions:
        to_actions_file(failed_action[0], failed_action[1], failed_action[2])


def to_actions_file(action, source_path, target_path):
    """
    Write an action to the actions file.

    If the actions file does not exist yet, it will be created.

    Parameters:
        action (char):     the action to write (a single character)
        source_path (str): the file to apply the action to
        target_path (str): the result of the action (if action is != d)
    """
    if source_path is None:
        to_actions_file_line(f"{action}")
    elif target_path is None:
        to_actions_file_line(f"{action} {source_path}")
    else:
        to_actions_file_line(f"{action} {source_path} → {target_path}")


def to_actions_file_line(line):
    """
    Write a line to the actions file.

    If the actions file does not exist yet, it will be created.

    Parameters:
        line (str): the line to write
    """
    if not actions_file:
        create_actions_file()

    with open(actions_file, 'a') as f:
        f.write(line + '\n')


def create_actions_file():
    """
    Create an actions file.

    The actions file will be created in the filesystem. Either in the
    current directory or, if that fails, in a system-defined directory for
    temporary files.

    The actions file will already be filled with a leading comment
    specifying the working directory when the file was created and some
    info about the format of its entries.

    The pathlib.Path to the actions file will be stored in the global
    variable actions_file.
    """
    # First try to create the actions file in the current directory
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H.%M.%S')
    try:
        fp, path = tempfile.mkstemp(prefix=f"edir-actions-{timestamp}-", dir=".", text=True)
    except Exception as err:
        try:
            fp, path = tempfile.mkstemp(prefix=f"edir-actions-{timestamp}-", text=True)
        except Exception as err:
            serr(f'ERROR: Cannot write actions file. Unfortunately, your changes are lost.')
            raise err

    # now print the header into the file
    with open(fp, 'w') as f:
        f.writelines(textwrap.dedent(f"""\
        # workdir: {os.getcwd()}
        #
        # Be careful when editing this file. The order of entries matters. Also the
        # number of whitespace characters is significant.
        #
        # Format of this file:
        #  operation  source file name  [single space  arrow  single space  new file name]
        #  │          │                  │             │      │             │
        #  │ ┌────────┘   ┌──────────────┘             │      │             │
        #  │ │            │┌───────────────────────────┘      │             │
        #  │ │            ││┌─────────────────────────────────┘             │
        #  │ │            │││┌──────────────────────────────────────────────┘
        #  │ │            ││││
        #  ▼ ▼            ▼▼▼▼
        #  d ./source file → ./target file
        #
        #  The possible operations are:
        #  d: Delete (only the source file name is allowed as additional content then
        #  r: Rename
        #  c: Copy
        #
        #  The arrow symbol must be surrounded by exactly 1 space character on each
        #  side. All other whitespace characters are recognized as parts of the
        #  file name then.
        #
        #  As the arrow has a special meaning here, it is not possible to use it in
        #  the actual file names. Escaping is not supported.
        #
        #  This file format is still subject to change.
        #
        #  Empty lines and lines starting with a hash mark (#) are ignored

        """))
    global actions_file
    actions_file = pathlib.Path(path)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
