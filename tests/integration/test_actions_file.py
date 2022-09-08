import unittest
import pathlib
import tempfile
import shutil
import io
import sys
import os
import re

edir = __import__("edir")

class SysOutWrapper():
    sout = None
    serr = None

    sout_orig = None
    serr_orig = None

    def __init__(self):
        self.sout = io.StringIO()
        self.serr = io.StringIO()

    def __enter__(self):
        self.sout_orig = sys.stdout
        self.serr_orig = sys.stderr
        sys.stdout = self.sout
        sys.stderr = self.serr
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = self.sout_orig
        sys.stderr = self.serr_orig

    def stdout(self):
        return self.sout.getvalue()

    def stderr(self):
        return self.serr.getvalue()

    def dispose(self):
        self.sout.close()
        self.serr.close()


class CustomAssertions():
    """Custom assertions relevant for the edir integration tests."""

    def list_dirs_recursively(self, path, only_files=False):
        result = []
        for root, dirs, files in os.walk(path):
            #print(f"VORHER: {root}")
            root = root.removeprefix(path.name)
            root = root.removeprefix("/")
            #print(f"NACHER: {root}")
            for name in files:
                result.append(os.path.join(root, name))
            if not only_files:
                for name in dirs:
                    result.append(os.path.join(root, name))
        return result

    def assertDirContainsExactlyFiles(self, path, files):
        """
        Assert that "path" contains exactly the files specified in "files" with the specified content.

        Parameters:
            path  (pathlib.Path): the directory to check
            files (dict):         a dictionary mapping the expected file names to their content.
                                  if the content is None, it will be ignored and not verified

        Usage:
            path = pathlib.Path("the_directory")
            self.assertDirContainsExactlyFiles(
                path,
                {
                  'file1.txt': "content of file 1",
                  'file2.txt': "content of file 2",
                }
        """
        actual_files = self.list_dirs_recursively(path, True)
        actual_files = [os.path.abspath(f) for f in actual_files]
        expected_files = [os.path.abspath(f) for f in files.keys()]
        self.assertListsEqual(actual_files, expected_files)
        for filename, content in files.items():
            file = path / filename
            if content:
                self.assertFileContains(file, content)

    def assertFileContains(self, file, content):
        """
        Assert that "file" has exactly the given "content".

        file (pathlib.Path):        the file to check
        content (str or list[str]): may be either the whole content as a string
                                    or a list of strings (one string per content line)
        """
        with file.open('r') as fp:
            actual = fp.readlines()
            if isinstance(content, str):
                actual = "\n".join(actual)

            testcase = unittest.TestCase()
            testcase.assertEqual(actual, content)


    def assertListsEqual(self, actual, expected):
        """
        Assert that the "actual" list is exactly equal to the "expected" one.

        Asserts that:
          - they contain the same number of elements
          - in the same order
        """
        if len(actual) != len(expected):
            raise AssertionError(f'''
            Number of elements different. Expected {len(expected)}, but was {len(actual)}.
            Expected: {expected}
            Actual:   {actual}
            ''')

        for elm in expected:
            if not elm in actual:
                raise AssertionError(f'''
                Expected element "{elm}" is missing.
                Actual elements: {actual}
                ''')

        for elm in actual:
            if not elm in expected:
                raise AssertionError(f'''
                Actual element "{elm}" was not expected.
                Expected elements: {expected}
                ''')


    def assertStdoutEquals(self, out_capture, expected):
        testcase = unittest.TestCase()
        testcase.assertEqual(out_capture.stdout().strip(), expected.strip())


    def assertStderrEquals(self, err_capture, expected):
        testcase = unittest.TestCase()
        testcase.assertEqual(err_capture.stderr().strip(), expected.strip())


    def assertStdoutContains(self, out_capture, expected):
        testcase = unittest.TestCase()
        testcase.assertIn(expected, out_capture.stdout())


    def assertStderrContains(self, err_capture, expected):
        testcase = unittest.TestCase()
        testcase.assertIn(expected, err_capture.stderr())


    def assertStdErrMentionsActionFile(self, err_capture):
        # FIXME: Wie muss die Zeile tatsächlich aussehen?
        match = re.search("ACTIONS FILE: (.+)$", err_capture.stderr().strip(), re.MULTILINE)
        if match is None:
            raise AssertionError(f"""
            No line with actions_file found in stderr:
            {err_capture.stderr()}
            """)
        return match[1]


    def assertActionsFileContainsEntries(self, actions_file, lines):
        fpath = pathlib.Path(actions_file)
        with fpath.open() as fp:
            entries = []
            for count, line in enumerate(fp, 1):
                line = line.rstrip('\n')
                if line.strip() and not re.match(edir.COMMENT_LINE_REGEX, line):
                    entries.append(line)
            self.assertListsEqual(entries, lines)



class TestReadActionsFile(unittest.TestCase, CustomAssertions):
    """Test cases for actions involving reading an actions file."""

    cwd    = '.'
    tmpdir = None

    def setUp(self):
        """Create a temporary working dir and chdir to it."""
        self.cwd = os.getcwd()
        self.tmpdir = tempfile.TemporaryDirectory()
        os.chdir(self.tmpdir.name)


    def tearDown(self):
        """Delete the temporary working dir and chdir to the previous working dir."""
        os.chdir(self.cwd)
        self.tmpdir.cleanup()

        # FIXME: This is unclean. Path should not be used static inside edir
        edir.Path.paths = []
        # FIXME: These are also bad.
        edir.counts = [0, 0]
        edir.actions_file = None


    def test_actions_file_missing(self):
        """Test that the application exits with exit code 3 if the given actions file does not exit."""
        with self.assertRaises(SystemExit) as cm, \
             SysOutWrapper() as out:
            edir.main(['-i', 'does_not_exist'])

        self.assertEqual(cm.exception.code, 3)
        self.assertStdoutEquals(out, '')
        self.assertStderrEquals(out, "ERROR: does_not_exist does not exist.")


    def test_all_operations(self):
        """
        Test the successful execute of all 3 possible operations.

        The operations are:
          - deletion
          - renaming
          - copying
        """
        # - preparation

        actions_file = create_file('actions_file', """
            d file1
            r file2 → file2renamed
            c file3 → file3copy
            """)
        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file2renamed': "file 2 content",
              'file3':        "file 3 content",
              'file3copy':    "file 3 content",
              'file4':        "file 4 content",
            })


    def test_absolute_and_relative_path_mixed(self):
        """
        Test the successful execute of all 3 possible operations where absolute paths are changed to relative paths and vice versa.
        """
        # - preparation

        actions_file = create_file('actions_file', f"""
            d ./file1
            r {os.getcwd()}/testdir/file2 → ./file2renamed
            c ./file3 → {os.getcwd()}/testdir/file3copy
            """)
        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file2renamed': "file 2 content",
              'file3':        "file 3 content",
              'file3copy':    "file 3 content",
              'file4':        "file 4 content",
            })



    def test_spaces_in_filenames(self):
        """
        Test that filenames may contain spaces at the beginning, the end and in between.
        """
        # - preparation

        actions_file = create_file('actions_file', """
            d ./ file with leading spaces
            r ./file with spaces inside → ./ file with spaces inside and before
            c ./file with trailing spaces  → ./ file with spaces everywhere
            """)
        testdir = create_dir("testdir", {
            " file with leading spaces": "file 1 content",
            "file with spaces inside": "file 2 content",
            "file with trailing spaces ": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              ' file with spaces inside and before': "file 2 content",
              'file with trailing spaces ':          "file 3 content",
              ' file with spaces everywhere':        "file 3 content",
              'file4':                               "file 4 content",
            })


    def test_move_to_new_directory(self):
        """
        Test that the directory may be changed (even to not yet existing ones).
        """
        # - preparation

        actions_file = create_file('actions_file', """
            r innerdir/file1 → other dir/file1
            r innerdir/file2 → innerdir/subdir/file2renamed
            c innerdir/file3 → ./file3copy
            """)
        testdir = create_dir("testdir", {})
        os.chdir(testdir)
        subdir = create_dir("innerdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        edir.main(['--quiet', '-i', str(actions_file)])

        # - verification

        # FIXME: Diese assert-Methode sollte auch Subdirectories gleich mit testen
        self.assertDirContainsExactlyFiles(
            pathlib.Path('.'),
            {
              'other dir/file1':              "file 1 content",
              'innerdir/subdir/file2renamed': "file 2 content",
              'innerdir/file3':               "file 3 content",
              'file3copy':                    "file 3 content",
              'innerdir/file4':               "file 4 content",
            })


    def test_multiple_operations_on_same_file(self):
        """
        Test that a file may be renamed and copied (multiple times) at the same time.
        """
        # - preparation

        actions_file = create_file('actions_file', """
            d file1
            c file2 → file2copy
            r file2 → file2renamed
            c file3 → file3copy
            c file3 → file3copy2
            """)
        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file2renamed': "file 2 content",
              'file2copy':    "file 2 content",
              'file3':        "file 3 content",
              'file3copy':    "file 3 content",
              'file3copy2':   "file 3 content",
              'file4':        "file 4 content",
            })



    def test_ignore_empty_and_comments_lines(self):
        """
        Test that comments and empty lines are being ignored.
        """
        # - preparation

        actions_file = create_file('actions_file', """
            # This is a comment line

            # This is another comment line
            d file1

            r file2 → file2renamed

            # Even more comments… → with special characters
            c file3 → file3copy
            """)
        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file2renamed': "file 2 content",
              'file3':        "file 3 content",
              'file3copy':    "file 3 content",
              'file4':        "file 4 content",
            })


    def test_arrow_in_filenames(self):
        """
        Test that the special arrow is not allowed as a character in filenames.

        FIXME: This currently show an error due to an "unparsable line".
               But we should state more clearly that the arrow is the
               problem. And we need to write a new actions file!
        """
        # - preparation

        actions_file = create_file('actions_file', """
            d file1
            r file → 2 → file2renamed
            r file3 → file→3renamed
            r file4 → file4renamed
            """)
        testdir = create_dir("testdir", {
            "file1":    "file 1 content",
            "file → 2": "file 2 content",
            "file3":    "file 3 content",
            "file4":    "file 4 content",
            })

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['--quiet', '-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file → 2': "file 2 content",
              'file3':    "file 3 content",
              'file4renamed':    "file 4 content",
            })


    def test_some_files_fail_again(self):
        """
        Test that a new actions file is written for operations that fail again.
        """
        self.fail('no yet impl')


class TestWriteActionsFile(unittest.TestCase, CustomAssertions):
    """Tests for writing an actions file for failed operations."""

    cwd    = '.'
    tmpdir = None

    def setUp(self):
        """Create a temporary working dir and chdir to it."""
        self.cwd = os.getcwd()
        self.tmpdir = tempfile.TemporaryDirectory()
        os.chdir(self.tmpdir.name)


    def tearDown(self):
        """Delete the temporary working dir and chdir to the previous working dir."""
        os.chdir(self.cwd)
        self.tmpdir.cleanup()

        # FIXME: This is unclean. Path should not be used static inside edir
        edir.Path.paths = []
        # FIXME: These are also bad.
        edir.counts = [0, 0]
        edir.actions_file = None



    def test_no_actions_file_on_success(self):
        """
        Test that no actions file is written if everything works fine.
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path('file1', None),
            path('file2', 'file2renamed'),
            path('file3', 'file3', ['file3copy']),
            ]

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                edir.perform_actions(paths)
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file2renamed': "file 2 content",
              'file3':        "file 3 content",
              'file3copy':    "file 3 content",
              'file4':        "file 4 content",
            })

        self.assertStdoutEquals(out, '')
        self.assertStderrEquals(out, '')


    def test_all_files_fail(self):
        """
        Test all files as failed with all possible operations.

        FIXME: Can we just retain the order the operations were executed in?
               Should be possible.
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path('file1', None),
            path('file2', 'file2renamed'),
            path('file3', 'file3', ['file3copy', 'file3copy2']),
            ]

        # - test

        try:
            os.chmod("testdir", 0o555)
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                exit_code = edir.perform_actions(paths)
        finally:
            os.chdir(cwd)
            os.chmod("testdir", 0o775)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file1': "file 1 content",
              'file2': "file 2 content",
              'file3': "file 3 content",
              'file4': "file 4 content",
            })

        self.assertEqual(exit_code, 2)
        self.assertStdoutContains(out, '')
        self.assertStderrContains(out, 'An actions-file was written')
        actions_file = edir.actions_file
        self.assertActionsFileContainsEntries(actions_file, [
            'd file1',
            'r file2 → file2renamed',
            'c file3 → file3copy',
            'c file3 → file3copy2',
            ])


    def test_multiple_operations_fail_on_same_file(self):
        """
        Test the actions file is correctly written for multiple failed operations.

        ATTENTION! The order or operation matters here!
                   1. copy
                   2. delete
                   3. rename
                   Can the last two be exchanged?
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path('file2', 'file2renamed', ['file2copy', 'file2copy2']),
            ]

        # - test

        try:
            os.chmod("testdir", 0o555)
            #os.chmod("testdir/file2", 0o000)
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                exit_code = edir.perform_actions(paths)
        finally:
            os.chdir(cwd)
            os.chmod("testdir", 0o775)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file1':        "file 1 content",
              'file2':        "file 2 content",
              'file3':        "file 3 content",
              'file4':        "file 4 content",
            })

        self.assertEqual(exit_code, 2)
        self.assertStdoutContains(out, '')
        self.assertStderrContains(out, 'An actions-file was written')
        actions_file = edir.actions_file
        self.assertActionsFileContainsEntries(actions_file, [
            'c file2 → file2copy',
            'c file2 → file2copy2',
            'r file2 → file2renamed',
            ])


    def test_only_some_operations_fail_on_same_file(self):
        """
        Test the actions file is correctly written, if some operations work and some don't.

        For example a file can be renamed, but not copied.
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file2": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path('file2', 'file2renamed', ['file2copy', 'file2copy2']),
            ]

        # - test

        try:
            os.chmod("testdir/file2", 0o000)
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                exit_code = edir.perform_actions(paths)
        finally:
            os.chdir(cwd)
            os.chmod("testdir/file2renamed", 0o664)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file1':        "file 1 content",
              'file2renamed': "file 2 content",
              'file3':        "file 3 content",
              'file4':        "file 4 content",
              pathlib.Path(edir.actions_file).name: None,
            })

        self.assertEqual(exit_code, 1)
        self.assertStdoutContains(out, '')
        self.assertStderrContains(out, 'An actions-file was written')
        actions_file = edir.actions_file
        self.assertActionsFileContainsEntries(actions_file, [
            'c file2 → file2copy',
            'c file2 → file2copy2',
            ])


    def test_failed_file_with_whitespaces(self):
        """
        Test the actions file is correctly written for a file with whitespace in between and around.
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            " file 2  ": "file 2 content",
            "file3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path(' file 2  ', '  file 2 renamed '),
            ]

        # - test

        try:
            os.chmod("testdir", 0o555)
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                exit_code = edir.perform_actions(paths)
        finally:
            os.chdir(cwd)
            os.chmod("testdir", 0o775)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file1': "file 1 content",
              ' file 2  ': "file 2 content",
              'file3': "file 3 content",
              'file4': "file 4 content",
            })

        self.assertEqual(exit_code, 2)
        self.assertStdoutContains(out, '')
        self.assertStderrContains(out, 'An actions-file was written')
        actions_file = edir.actions_file
        self.assertActionsFileContainsEntries(actions_file, [
            'r  file 2   →   file 2 renamed ',
            ])


    def test_failed_file_with_arrows(self):
        """
        Test that failed files with arrows are written to the script (even though they cannot be renamed via the actions file).
        """
        # - preparation

        testdir = create_dir("testdir", {
            "file1": "file 1 content",
            "file→2": "file 2 content",
            "file→3": "file 3 content",
            "file4": "file 4 content",
            })
        paths = [
            path('file→2', 'file→2renamed'),
            path('file→3', 'file3renamed'),
            path('file4', 'file→4renamed'),
            ]

        # - test

        try:
            os.chmod("testdir", 0o555)
            cwd = os.getcwd()
            os.chdir("testdir")
            with SysOutWrapper() as out:
                exit_code = edir.perform_actions(paths)
        finally:
            os.chdir(cwd)
            os.chmod("testdir", 0o775)

        # - verification

        self.assertDirContainsExactlyFiles(
            testdir,
            {
              'file1': "file 1 content",
              'file→2': "file 2 content",
              'file→3': "file 3 content",
              'file4': "file 4 content",
            })

        self.assertEqual(exit_code, 2)
        self.assertStdoutContains(out, '')
        self.assertStderrContains(out, 'An actions-file was written')
        actions_file = edir.actions_file
        self.assertActionsFileContainsEntries(actions_file, [
            'r file→2 → file→2renamed',
            'r file→3 → file3renamed',
            'r file4 → file→4renamed',
            ])


class TestBasicActions(unittest.TestCase, CustomAssertions):
    """Tests for the supported use cases."""

    def test_circular_renames(self):
        """
        Test that circular renames give the expected result.

        file1 is renamed to file2 and at the same time file2 is renamed to file1.
        """
        self.fail('no yet impl')


    def test_rename_to_new_subdirectories(self):
        """
        Test that intermediate subdirectories are created if necessary.
        """
        # TODO: Test multiple levels of subdirectories
        self.fail('no yet impl')


    def test_duplicate_target_name(self):
        """
        Test that no data loss occurs for duplicate target names.

        This checks two cases:
        1. Two renames with the same target name
        2. One rename to an already existing name (e.g. in a subdirectory)
        """
        self.fail('no yet impl')


# -- Helper methods -- #

def create_dir(dirname, files):
    """
    Create the directory "dirname" with the specified "files" in it.

    Parameters:
        dirname (string):    the directory to create (in the current working directory)
        files   (dict):      a dictionary mapping the filenames to create to their content
    """
    os.mkdir(dirname)
    for file, content in files.items():
        create_file(dirname + "/" + file, content)

    return pathlib.Path(dirname)


def create_file(filename, content):
    """
    Create a file with the given "filename" and "content".

    Parameters:
        filename (str):              the name of the file to create
        content  (str or list[str]): the content to write into the file
    """
    file = pathlib.Path(filename)
    with file.open('w') as fp:
        fp.writelines(content)
    return file.resolve()


def path(name, newname, copies= []):
    orig = pathlib.Path(name)
    path = edir.Path(orig)
    path.newpath = None if newname == None else pathlib.Path(newname)
    path.copies = copies
    return path


if __name__ == '__main__':
    unittest.main(exit=False) # exit=False doesn't work?
