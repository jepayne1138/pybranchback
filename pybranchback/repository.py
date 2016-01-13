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

    def __init__(self, root_dir, create=False):
        """Initialize instance variables"""
        self.root_dir = root_dir
        self.create = create


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
