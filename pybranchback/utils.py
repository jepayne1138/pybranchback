import contextlib
import os
import posixpath


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
    if blacklist is None:
        blacklist = []
    return [
        f for f in next(os.walk(directory))[return_type]
        if f not in blacklist
    ]


# Returns a list of all strings that start with the given match string
def get_matches(match_string, iter_strings):
    return [
        x.lower()
        for x in iter_strings
        if x.lower().startswith(match_string.lower())
    ]


# Helper function for creating normalized posix paths
def posixjoin(*args):
    """Returns a normalized path of posix joined arguments"""
    return posixpath.normpath(posixpath.join(*args))


# Context manager for temporarily changing the working directory
@contextlib.contextmanager
def temp_wd(path):
    """Context manager for temporarily switching directories"""
    save_wd = os.getcwd()
    os.chdir(path)
    yield
    os.chdir(save_wd)
