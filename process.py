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
    HASHMAP = 'hashmap'

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
        self.hashmap_path = os.path.join(self.vc_dir, self.HASHMAP)

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

        # Define helper attributes
        self.hashmap = {}

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
        return self._save_node(directory, node_content)

    def _create_blob_node(self, path):
        """Creates nodes for files in the current snapshot"""
        with open(path, 'rb') as input_file:
            node_content = input_file.read()

        # Save the node contents to a vc object
        return self._save_node(path, node_content)

    def _save_node(self, path, node_content):
        """Calculates a content hash and saves the content to a file"""
        # Get node content hash
        digest = self._hash_diget(node_content)

        # Parse object directory and filename
        obj_dir = os.path.join(self.obj_dir, digest[:2])
        obj_path = os.path.join(obj_dir, digest[2:])

        # Make the directory if it does not exist
        os.makedirs(obj_dir, exist_ok=True)

        if not os.path.isfile(obj_path):
            with open(obj_path, 'wb') as obj_file:
                obj_file.write(bin_content)

        self._update_hashmap(path, digest, node_content)

        return digest

    def _hash_diget(self, payload):
        """Returns a hex digest for the hash of the given payload"""
        hasher = hashlib.sha1()
        # Convert to binary content if necessary
        if type(node_content) is bytes:
            bin_content = node_content
        else:
            bin_content = node_content.encode()
        hasher.update(bin_content)
        return hasher.hexdigest

    def _create_blobcache(self):
        """Creates a new empty file that will store current file hashes"""
        with open(self.hashmap_path, 'wb') as hashmap_file:
            pickle.dump({}, hashmap_file)

    def _update_hashmap(self, obj_path, obj_hash, obj_content):
        """Updates the hashmap with a pointer to the new file"""
        if path in self.hashmap:
            if self.hashmap[path] != obj_hash:
                self._delta_compress(self.hashmap[path], obj_hash, obj_content)
        # Update hashmap
        self.hashmap[path] == obj_hash

    def _delta_compress(self, old_hash, new_hash, new_content):
        """Compresses an old object file by replacing with a delta

        NOTE:
          The file name hash no longer will reflect the true file
          content, rather the content that the delta reflects.
        """
        # Clean up old file
        old_dir = os.path.join(self.obj_dir, old_hash[:2])
        old_path = os.path.join(old_dir, old_hash[2:])

        # Calculate delta from new to old version
        delta = ''

        # Format delta contents
        delta_dict = {
            'origin': new_hash,
            'delta': delta,
        }
        delta_contents = pickle.dumps(delta_dict)

        # Overwrite old file contents with a delta to the new file
        with open(old_path, 'wb') as obj_file:
            obj_file.write(delta_contents)

    def _read_object(self, obj_hash):
        """Reads and returns the contents of an object file with given hash

        Recursively rebuilds any necessary files from their deltas
        """
        obj_dir = os.path.join(self.obj_dir, obj_hash[:2])
        obj_path = os.path.join(old_dir, obj_hash[2:])

        with open(obj_path, 'rb') as obj_file:
            content = obj_file.read()

        # Check if a delta by comparing the content to the hash value
        if obj_hash != self._hash_diget(content):
            # Delta object must be rebuilt
            delta_dict = pickle.loads(content)
            origin_content = self._read_object(delta_dict['origin'])
            return self._rebuild_content(origin_content, delta_dict['delta'])

        # If object is not a delta, simply return it's content
        return content

    def _rebuild_content(self, origin, delta):
        """Rebuilds object content from origin data and a delta"""
        return ''


def main():
    """Tests the version control program with a basic test"""
    parser = argparse.ArgumentParser(
        description='Basic version control system'
    )
    parser.add_argument(
        'root', type=str,
        help='Directory to be version controlled'
    )
    parser.add_argument(
        '--create', '-c', action='store_true',
        help='Create a new version control repo if not existent'
    )
    args = parser.parse_args()
    VersionControl(args.root, create=args.create).snapshot()


if __name__ == '__main__':
    main()
