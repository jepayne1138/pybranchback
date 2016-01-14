import ctypes
import os
import pickle
import posixpath
import pybranchback.snapshotdb as ssdb


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

        # Instance variables
        self.objhashcache = {}

        # Validate that a repository exists at the given location
        if not self.validate_repo():
            if self.create:
                self.create_repo()
            else:
                raise ValueError('Repository does not exist or is invalid')

        # Load any existing attributes
        self._load_hashmap()

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

        # Create HEAD file and set branch to 'master'
        self._set_head('master')

        # Create objhashcache file and set as empty
        self._save_hashmap()

        # Create the snapshots database
        ssdb.execute(self.FILES['snapshots'], ssdb.CREATE)

    def _join_root(self, rel_path):
        """Return a joined relative path with the instance root directory"""
        return os.path.join(self.root_dir, rel_path)

    def _set_branch(self, branch_name):
        """Sets the current branch to the given name"""
        with open(self.FILES['head'], 'w') as head_file:
            head_file.write(branch_name)

    def _save_hashmap(self):
        """Saves the current state of the hashmap"""
        with open(self.FILES['objhashcache'], 'wb') as hash_file:
            pickle.dump(self.objhashcache, hash_file)

    def _load_hashmap(self):
        """Loads a saved hashmap from a file"""
        with open(self.FILES['objhashcache'], 'rb') as hash_file:
            self.objhashcache = pickle.load(hash_file)


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
