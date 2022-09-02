import unittest
import pathlib
import tempfile
import shutil
import os

edir = __import__("edir")

class CustomAssertions():
    """Custom assertions relevant for the edir integration tests."""

    def assertDirContainsExactly(self, path, files):
        """
        Assert that "path" contains exactly the files specified in "files" with the specified content.

        Parameters:
            path  (pathlib.Path): the directory to check
            files (dict):         a dictionary mapping the expected file names to their content.

        Usage:
            path = pathlib.Path("the_directory")
            self.assertDirContainsExactly(
                path,
                {
                  'file1.txt': "content of file 1",
                  'file2.txt': "content of file 2",
                }
        """
        actual_files = os.listdir("testdir")
        self.assertListsEqual(actual_files, files.keys())
        for filename, content in files.items():
            file = pathlib.Path("testdir") / filename
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
                Expected element "{file}" is missing.
                Actual elements: {actual}
                ''')

        for elm in actual:
            if not elm in expected:
                raise AssertionError(f'''
                Actual element "{felement}" was not expected.
                Expected elements: {expected}
                ''')


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


    def test_actions_file_missing(self):
        """Test that the application exits with exit code 3 if the given actions file does not exit."""
        with self.assertRaises(SystemExit) as cm:
            edir.main(['-i', 'does_not_exist'])

        self.assertEqual(cm.exception.code, 3)


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
        testdir = create_dir("testdir", [
            "file1",
            "file2",
            "file3",
            "file4",
            ])

        # - test

        try:
            cwd = os.getcwd()
            os.chdir("testdir")
            edir.main(['-i', str(actions_file)])
        finally:
            os.chdir(cwd)

        # - verification

        self.assertDirContainsExactly(
            testdir,
            {
              'file2renamed': "file2content",
              'file3':        "file3content",
              'file3copy':    "file3content",
              'file4':        "file4content",
            })


def create_dir(dirname, files):
    """
    Create the directory "dirname" with the specified "files" in it.

    Parameters:
        dirname (string):    the directory to create (in the current working directory)
        files   (list[str]): the names of the files to create
    """
    os.mkdir(dirname)
    for file in files:
        create_file(dirname + "/" + file, file + "content")


def create_file(filename, content):
    file = pathlib.Path(filename)
    with file.open('w') as fp:
        fp.writelines(content)
    return file.resolve()


if __name__ == '__main__':
    unittest.main(exit=False) # exit=False doesn't work?
