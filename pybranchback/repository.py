import os
import posixpath
import ctypes


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

    DIRS = {
        'top': '.pbb',
        'objects': '.pbb/objects',
        'refs': '.pbb/refs',
        'heads': '.pbb/refs/heads',
    }
    FILES = {
        'objhashcache': '.pbb/objhashcache',
        'head': '.pbb/HEAD',
        'snapshots': '.pbb/snapshots',
    }

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
        def is_dir(rel_path):
            return os.path.isdir(self._join_root(rel_path))

        def is_file(rel_path):
            return os.path.isfile(self._join_root(rel_path))

        return (
            all(map(is_dir, self.DIRS.values())) and
            all(map(is_file, self.FILES.values()))
        )

    def create_repo(self):
        """Create a new repository directory in the root location"""
        # Create all directories
        for rel_dir in self.DIRS.values():
            os.makedirs(self._join_root(rel_dir), exist_ok=True)

        # Make the new version control folder hidden
        ctypes.windll.kernel32.SetFileAttributesW(
            self._join_root(self.DIRS['top']), 0x02
        )

        # Create all files
        for rel_file in self.FILES.values():
            with open(self._join_root(rel_file), 'wb'):
                pass

    def _join_root(self, rel_path):
        """Return a joined relative path with the instance root directory"""
        return os.path.join(self.root_dir, rel_path)


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