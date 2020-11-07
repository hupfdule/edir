## EDIR - Rename and Delete Files and Directories Using Your Editor

[edir](http://github.com/bulletmark/edir) is a command line utility to
rename and remove filenames and directories using your text editor. Run
it in the current directory and `edir` will open your editor on a list
of files and directories in that directory. Each item in the directory
will appear on its own numbered line. These numbers are how `edir` keeps
track of what items are changed. Delete lines to remove
files/directories, or edit lines to rename files/directories. You can
also switch pairs of numbers to swap files or directories. If run from
within a [Git](https://git-scm.com/) repository, `edir` will use
[Git](https://git-scm.com/) to rename or delete tracked
files/directories.

The latest version and documentation is available at
https://github.com/bulletmark/edir.

## Advantages Compared to Vidir

[edir](http://github.com/bulletmark/edir) unashamedly mimics the
functionality of the [vidir](https://linux.die.net/man/1/vidir) utility
from [moreutils](https://joeyh.name/code/moreutils/) but aims to improve it in
the following ways:

1. `edir` automatically uses `git mv` instead of `mv` and `git rm`
    instead of `rm` for tracked files when working in a
    [Git](https://git-scm.com/) repository. There is also a `-G/--no-git`
    option to suppress this default action. See the description in the
    section below about the git options.

2. `vidir` presents file and directories equivalently but `edir` adds a
   trailing slash `/` to visually discriminate directories. E.g. if `afile` and
   `bfile` are files, `adir` and `bdir` are directories, then `vidir`
   presents these in your editor as follows.

   ```
   1	./a
   2	./b
   3	./c
   4	./d
   ```
 
   But `edir` presents these as:
 
   ```
   1	./a
   2	./b
   3	./c/
   4	./d/
   ```

   Note the trailing slash is only for presentation in your editor. You
   are not required to ensure it is present after editing. E.g. editing
   line 3 above to `./e` (or even just to `e`) would still rename the
   directory `c` to `e`.

   Note also, that both `edir` and `vidir` show the leading `./` on each
   entry so that any leading spaces are clearly seen, and can be edited.

3. `edir` allows you to remove a file/directory by deleting the line, as
   `vidir` does, but you can also remove it by pre-pending a `#` to
   "comment it out" or by substituting an entirely blank line.

4. By default, `edir` prints remove and rename messages whereas `vidir`
   prints those only when the `-v/--verbose` switch is added. You can add
   `-q/--quiet` to `edir` to suppress these messages.

5. When `vidir` is run with the `-v/--verbose` switch then it reports
   the renaming of original to intermediate temporary to final files if
   files are swapped etc. That is rather an implementation detail so
   `edir` only reports the original to final renames which is all the
   user really cares about.

6. To remove a large recursive tree you must pipe the directory tree to
   `vidir` and then explicitly remove all children files and directories
   before deleting a parent directory. You can do this also in `edir` of
   course (and arguably it is probably the safest approach) but there
   are times when you really want to let `edir` remove recursively so
   `edir` adds a `-r/--recurse` switch to allow this. BE CAREFUL USING
   THIS!

7. `vidir` always shows all files and directories in a directory,
   including hidden files and directories (i.e. those starting with a
   `.`). Usually a user does not want to be bothered with these so
   `edir` by default does not show them. They can be included by adding
   the `-a/--all` switch.

8. `edir` does not require the user to specify the `-` if something has
    been piped to standard input. E.g. you need only type `find | edir`
    as opposed to `find | edir -`. Note that `vidir` requires the second
    form.

9. `edir` adds a `-F/--files` option to only show files, or `-D/--dirs`
    to only show directories.

10. `edir` adds a `-L/--nolinks` option to ignore symbolic links.

11. `edir` adds a `-d/--dirnames` option to edit specified directory
    names directly, not their contents. I.e. this is like `ls -d mydir`
    compared to `ls mydir`.

12. `edir` adds a `-t/--trash` option to delete to your
     [Trash](https://specifications.freedesktop.org/trash-spec/trashspec-1.0.html).
     This option invokes
     [`trash-put`](https://www.mankier.com/1/trash-put) from the
     [trash-cli](https://github.com/andreafrancia/trash-cli) package to do
     deletions.

13. `edir` shows a message "No files or directories" if there is nothing
   to edit, rather than opening an empty file to edit.

14. `edir` filters out any duplicate paths you may inadvertently specify
    on it's command line.

15. `edir` always invokes a consistent duplicate renaming scheme. E.g. if
    you rename `b`, `c`, `d` all to the same pre-existing name `a` then
    `edir` will rename `b` to `a~`, `c` to `a~1`, `d` to `a~2`.
    Depending on order of operations, `vidir` is not always consistent
    about this, E.g. sometimes it creates a `a~1` with no `a~` (this may
    be a bug in `vidir` that nobody has ever bothered to
    report/address?).

16. `edir` creates the temporary editing file with a `.sh` suffix so
    your EDITOR may syntax highlight the entries. Optionally, you can
    change this default suffix.

17. `edir` provides an optional environment value to add custom options
    to the invocation of your editor. See section below.

18. `edir` provides an optional configuration file to set default `edir`
    command line arguments. See section below.

19. Contrary to what it's name implies, `vidir` actually respects your
    `$EDITOR` variable and runs your preferred editor like `edir` does
    but `edir` has been given a generic name to make this more apparent.

20. `edir` is very strict about the format of the lines you edit and
    immediately exits with an error message (before changing anything)
    if you format one of the lines incorrectly. All lines in the edited
    list:

    1. Must start with a number, that number must be in range, and that
       number must be unique,
    2. Must have at least one white space/tab after the number,
    3. Must have a remaining valid path name.
    4. Can start with a `#` or be completely blank to be considered the
       same as deleted.

    Note the final edited order of lines does not matter, only the first
    number value is used to match the newly edited line to the original
    line so an easy way to swap two file names is just to swap their
    numbers.

21. `edir` always removes and renames files consistently. The sequence of
     operations applied is:

    1. Deleted files are removed and all renamed files and directories
       are renamed to temporaries. The temporaries are made on the same
       file-system as the target.
 
    2. Empty deleted directories are removed.
 
    3. Renamed temporary files and directories are renamed to their target name.
 
    4. Remaining deleted directories are removed.
 
    In simple terms, remember that files are processed before directories
    so you can rename files into a different directory and then delete
    the original directory, all in one edit.

## Renames and Deletes in a GIT Repository

When working within a [Git](https://git-scm.com/) repository, you nearly
always want to use `git mv` instead of `mv` and `git rm` instead of `rm`
for files and directories so `edir` recognises this and does it
automatically. Note that only tracked files/dirs are moved or renamed
using Git. Untracked files/dirs within the repository are removed or
renamed in the normal way.

If for some reason you don't want automatic git action then you can
set the `--no-git` option as a default option, see the section below on
how to set default options. If you set `--no-git` as the default, then
you can use `-g/-git` on the command line to turn that default option
off temporarily.

## Using Trash

Given how easy `edir` facilitates deleting files, some users may prefer
to delete them to system
[Trash](https://specifications.freedesktop.org/trash-spec/trashspec-1.0.html)
from where they can be later listed and/or recovered. Specifying
`-t/--trash` does this by executing the
[`trash-put`](https://www.mankier.com/1/trash-put) command, from the
[`trash-cli`](https://github.com/andreafrancia/trash-cli) package, to
remove files rather than removing them natively.

You may want to set `-t/--trash` as a default option. If you do so then
you can use `-T` on the command line to turn that default option off
temporarily.

## Installation

Arch users can install [edir from the AUR](https://aur.archlinux.org/packages/edir/).

Python 3.6 or later is required. Note [edir is on
PyPI](https://pypi.org/project/edir/) so you can just do:

```
$ sudo pip3 install edir
```

or, to install from this source repository:

```
$ git clone http://github.com/bulletmark/edir
$ cd edir
$ sudo pip3 install .
```

Optionally, if you are using an odd system and/or want to install this
manually then all you need to do is rename `edir.py` as `edir` and make
it executable somewhere in your path.

Edir runs on pure Python. No 3rd party packages are required.
[Git](https://git-scm.com/) must be installed if you want to use the git
options. The [trash-cli](https://github.com/andreafrancia/trash-cli)
package is required if you want `-t/--trash` functionality.

### EDIR_EDITOR Environment Variable

`edir` selects your editor from the first environment value found of:
`$EDIR_EDITOR`, `$VISUAL`, `$EDITOR`, then falls back to "vi" if
none of these are set.

You can also `EDIR_EDITOR` explicitly to an editor + arguments
string if you want `edir` to call your editor with specific arguments.

## EDIR Command Default Arguments

You can add default arguments to a personal configuration file
`~/.config/edir-flags.conf`. If that file exists then each line of arguments
will be concatenated and automatically prepended to your `edir` command
line arguments.

This allow you to set default preferred starting arguments to `edir`.
Type `edir -h` to see the arguments supported.

The options `--all`, `--recurse`, `--quiet`, `--no-git`, `--trash`,
`--suffix`, are sensible candidates to consider setting as default. If
you set these then "on-the-fly" negation options `-A`, `-R`, `-Q`, `-g`,
`-T`, are also provided to temporarily override and disable default
options on the command line.

## Examples

Rename and/or delete any files and directories in the current directory:

```
$ edir
```

Rename and/or delete any jpeg files in current dir:

```
$ edir *.jpg
```

Rename and/or delete any files under current directory and subdirectories:

```
$ find | edir -F
```

Use [`fd`](https://github.com/sharkdp/fd) to view and `git mv/rm`
repository files only, in the current directory only:

```
$ fd -d1 -tf | edir -g
```

## Command Line Options

```
usage: edir [-h] [-a] [-A] [-r] [-R] [-q] [-Q] [-G] [-g] [-d] [-t] [-T]
            [-F | -D] [-L] [--suffix SUFFIX]
            [args [args ...]]

Program to rename and remove files and directories using your editor. Will use
git to action the rename and remove if run within a git repository.

positional arguments:
  args              file|dir, or "-" for stdin

optional arguments:
  -h, --help        show this help message and exit
  -a, --all         include all (including hidden) files
  -A, --no-all      negate the -a/--all/ option
  -r, --recurse     recursively remove any files and directories in removed
                    directories
  -R, --no-recurse  negate the -r/--recurse/ option
  -q, --quiet       do not print rename/remove actions
  -Q, --no-quiet    negate the -q/--quiet/ option
  -G, --no-git      do not use git if invoked within a git repository
  -g, --git         negate the --no-git option and DO use automatic git
  -d, --dirnames    edit given directory names directly, not their contents
  -t, --trash       use trash-put (from trash-cli) to do deletions
  -T, --no-trash    negate the -t/--trash/ option
  -F, --files       only show/edit files
  -D, --dirs        only show/edit directories
  -L, --nolinks     ignore all symlinks
  --suffix SUFFIX   specify suffix for editor file, default=".sh"

Note you can set default starting arguments in ~/.config/edir-flags.conf. The
negation options (i.e. the --no-* options and their shortforms) allow you to
temporarily override your defaults.
```

## Embed in Ranger File Manager

In many ways `edir` (and `vidir`) are better than the
[ranger](https://ranger.github.io/)
[bulkrename](https://github.com/ranger/ranger/wiki/Official-user-guide#bulk-renaming)
command which does not handle name swaps and clashes etc. To add `edir`
as a command within [ranger](https://ranger.github.io/), add or create
the following in `~/.config/ranger/commands.py`. Then run it from within
[ranger](https://ranger.github.io/) by typing `:edir`.

```python
from ranger.api.commands import Command

class edir(Command):
    '''
    :edir [file|dir]

    Run edir on the selected file or dir.
    Default argument is current dir.
    '''
    def execute(self):
        self.fm.run('edir -q ' + self.rest(1))
    def tab(self, tabnum):
        return self._tab_directory_content()
```

## License

Copyright (C) 2019 Mark Blakeney. This program is distributed under the
terms of the GNU General Public License.
This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or any later
version.
This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License at <http://www.gnu.org/licenses/> for more details.

<!-- vim: se ai syn=markdown: -->
