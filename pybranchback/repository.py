import os
import posixpath


class Repository:

    """Manages a repository instance

    Directory structure:
    +--.pbb/
    |  +--objects/
    |     +--<first 2 hash chars>/
    |        <remaining 38 harsh chars>
    |  +--refs/
    |     +--heads/
    |        master
    |  objhashcache
    |  HEAD
    |  snapshots
    """

    REQUIRED_DIRS = [
        '.pbb',
        '.pbb/objects',
        '.pbb/refs',
        '.pbb/refs/heads',
    ]
    REQUIRED_FILES = [
        '.pbb/objhashcache',
        '.pbb/HEAD',
        '.pbb/snapshots',
    ]

    def __init__(self, root_dir, create=False):
        """Initialize instance variables"""
        self.root_dir = root_dir
        self.create = create

        # Validate that a repository exists at the given location
        if not self.validate_repo():
            if self.create:
                self.create_repo()
            else:
                raise ValueError('Repository does not exist or is invalid')

    def validate_repo(self):
        """Check that the repository structure exists and is valid"""
        def is_dir(relative_path):
            return True
        def is_file(relative_path):
            return True
        return (
            all(map(os.path.isdir, self.REQUIRED_DIRS)) and
            all(map(os.path.isfile, self.REQUIRED_FILES))
        )

    def create_repo(self):
        """Create a new repository directory in the root location"""
        pass


# Helper functions for listing in a file structure with a blacklist
def list_directories(directory, blacklist=None):
    """Returns a list of all directories not in the blacklist"""
    return _list_with_blacklist(directory, blacklist, 1)


def list_files(directory, blacklist=None):
    """Returns a list of all files not in the blacklist"""
    return _list_with_blacklist(directory, blacklist, 2)


def _list_with_blacklist(directory, blacklist, return_type):
    """Returns a listing of a directory with blacklist for a given type

    return_type:
      1:  returns a list of all non-blacklisted directories
      2:  returns a list of all non-blacklisted files
    """
    blacklist = [] if blacklist is None else blacklist
    return [
        f for f in next(os.walk(directory))[return_type]
        if f not in blacklist
    ]


# Helper function for creating normalized posix paths
def posixjoin(*args):
    """Returns a normalized path of posix joined arguments"""
    return posixpath.normpath(posixpath.join(*args))
