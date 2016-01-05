import os
import posixpath
import hashlib
import ctypes
import argparse
import pickle
import functools


def root_directory(func):
    """Decorates VersionControl methods to temporarily use root directory"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Save current working directory
        orig_dir = os.getcwd()
        # Get root directory from the first `self` parameter
        # (This means this should only decorate VersionControl methods)
        os.chdir(args[0].root)
        # Call wrapped method
        ret_val = func(*args, **kwargs)
        # Restore original working directory
        os.chdir(orig_dir)
        return ret_val
    return wrapper


def posixjoin(*args):
    """Returns a normalized path of posix joined arguments"""
    return posixpath.normpath(posixpath.join(*args))


class VersionControl:

    """Very basic version control in the same vein as git

    Current structure:
    +--.vc/
    |  +--objects/
    |     +--<first 2 hash chars>/
    |        <remaining 38 harsh chars>
    """

    VC_DIR = '.vc'
    BLOBMAP = 'blobmap'

    def __init__(self, root, create=False):
        """Simple store all arguments and call main initialization method"""
        self.root = root
        self.create = create

        self._initialize()

    @root_directory  # Change cwd to build proper paths
    def _initialize(self):
        """Initialization of important paths and version validation"""
        # Define paths to important locations
        self.vc_dir = self.VC_DIR
        self.obj_dir = os.path.join(self.vc_dir, 'objects')
        self.blobmap = os.path.join(self.vc_dir, self.BLOBMAP)

        if self.create and not os.path.isdir(self.vc_dir):
            self.create_directory()

        # Check if a .vc folder is in the directory
        if not os.path.isdir(self.vc_dir):
            raise ValueError(
                'Not a version controlled directory: {}'.format(self.root)
            )

        # Check for vc integrity
        if not os.path.isdir(self.obj_dir):
            raise ValueError(
                'Version control integrity error: {}'.format(self.root)
            )

    @root_directory
    def create_directory(self):
        """Creates a new version control directory"""
        os.makedirs(self.obj_dir)  # Makes both root dir and objects dir
        # Make the new version control folder hidden
        ctypes.windll.kernel32.SetFileAttributesW(self.vc_dir, 0x02)

        # Create new blobcache file
        self._create_blobcache()

    @root_directory
    def snapshot(self):
        """Takes a snapshot of the the current status of the directory"""
        self._create_tree_node('.')

    def _create_tree_node(self, directory):
        """Recursive function creates tree nodes for current snapshot"""
        # Validate the given root directory
        if not os.path.isdir(directory):
            raise ValueError('Not a directory: {}'.format(directory))

        # Get all files and directories for his level (excluding our vc dir)
        directories = [
            d for d in next(os.walk(directory))[1]
            if d != self.VC_DIR
        ]
        files = next(os.walk(directory))[2]

        node_entries = []

        # Recursively create nodes for subdirectories
        for subdir in directories:
            node_hash = self._create_tree_node(posixjoin(directory, subdir))
            node_entries.append('{} {}'.format(node_hash, subdir))

        for file in files:
            node_hash = self._create_blob_node(posixjoin(directory, file))
            node_entries.append('{} {}'.format(node_hash, file))

        # Join node entries into the node content
        node_content = '\n'.join(node_entries) + '\n'

        # Save the node contents to a vc object
        return self._save_node(node_content)

    def _create_blob_node(self, path):
        """Creates nodes for files in the current snapshot"""
        with open(path, 'rb') as input_file:
            node_content = input_file.read()

        # Save the node contents to a vc object
        return self._save_node(node_content)

    def _save_node(self, node_content):
        """Calculates a content hash and saves the content to a file"""
        # Get node content hash
        sha1 = hashlib.sha1()
        if type(node_content) is bytes:
            bin_content = node_content
        else:
            bin_content = node_content.encode()
        sha1.update(bin_content)
        digest = sha1.hexdigest()

        # Parse object directory and filename
        obj_dir = os.path.join(self.obj_dir, digest[:2])
        obj_path = os.path.join(obj_dir, digest[2:])

        # Make the directory if it does not exist
        os.makedirs(obj_dir, exist_ok=True)

        if not os.path.isfile(obj_path):
            with open(obj_path, 'wb') as obj_file:
                obj_file.write(bin_content)

        return digest

    def _create_blobcache(self):
        """Creates a new empty file that will store current file hashes"""
        with open(self.blobmap, 'wb') as blobfile:
            pickle.dump({}, blobfile)


def main():
    """Tests the version control program with a basic test"""
    parser = argparse.ArgumentParser(
        description='Basic version control system'
    )
    parser.add_argument('root', type=str)
    args = parser.parse_args()
    VersionControl(args.root).snapshot()


if __name__ == '__main__':
    main()
