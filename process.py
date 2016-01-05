import os
import posixpath
import hashlib
import ctypes
import argparse
import pickle
import functools
import difflib


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
    |  +--refs/
    |     +--heads/
    |        master
    |  hashmap
    |  HEAD
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
        self.ref_dir = os.path.join(self.vc_dir, 'refs')
        self.head_dir = os.path.join(self.ref_dir, 'heads')
        self.hashmap_path = os.path.join(self.vc_dir, 'hashmap')
        self.head_path = os.path.join(self.vc_dir, 'HEAD')

        # Check if a .vc folder is in the directory
        if not os.path.isdir(self.vc_dir):
            # Not a version controlled directory
            if self.create:
                # Create a new version control instance
                self.create_directory()
            else:
                raise ValueError(
                    'Not a version controlled directory: {}'.format(self.root)
                )

        # Define helper attributes
        self.hashmap = {}

        # Set default HEAD path
        with open(self.head_path, 'w') as head_file:
            head_file.write('master')

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
        top_hash = self._create_tree_node('.')
        with open(self.head_file, 'r') as head_file:
            branch_name = head_file.read().strip()
        with open('refs/heads/{}'.format(branch_name), 'w') as branch_file:
            branch_file.write(top_hash)

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
        # Convert to bytes if necessary
        bytes_content = self._byte_convert(node_content)
        # Get node content hash
        digest = self._hash_diget(bytes_content)

        # Parse object directory and filename
        obj_dir = os.path.join(self.obj_dir, digest[:2])
        obj_path = os.path.join(obj_dir, digest[2:])

        # Make the directory if it does not exist
        os.makedirs(obj_dir, exist_ok=True)

        if not os.path.isfile(obj_path):
            with open(obj_path, 'wb') as obj_file:
                obj_file.write(bytes_content)

        self._update_hashmap(path, digest, node_content)

        return digest

    def _byte_convert(self, payload):
        if type(payload) is bytes:
            return payload
        # Try to encode if not bytes already
        return payload.encode()

    def _hash_diget(self, payload):
        """Returns a hex digest for the hash of the given payload"""
        hasher = hashlib.sha1()
        hasher.update(payload)
        return hasher.hexdigest

    def _create_blobcache(self):
        """Creates a new empty file that will store current file hashes"""
        with open(self.hashmap_path, 'wb') as hashmap_file:
            pickle.dump({}, hashmap_file)

    def _update_hashmap(self, obj_path, obj_hash, obj_content):
        """Updates the hashmap with a pointer to the new file"""
        if obj_path in self.hashmap:
            if self.hashmap[obj_path] != obj_hash:
                self._delta_compress(self.hashmap[obj_path], obj_hash, obj_content)
        # Update hashmap
        self.hashmap[obj_path] == obj_hash

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
        delta = generate_delta(
            self._byte_convert(new_content),
            self._read_object(old_hash)
        )

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
        obj_path = os.path.join(obj_dir, obj_hash[2:])

        with open(obj_path, 'rb') as obj_file:
            content = obj_file.read()

        # Check if a delta by comparing the content to the hash value
        if obj_hash != self._hash_diget(content):
            # Delta object must be rebuilt
            delta_dict = pickle.loads(content)
            origin_content = self._read_object(delta_dict['origin'])
            return rebuild_delta(origin_content, delta_dict['delta'])

        # If object is not a delta, simply return it's content
        return content


def generate_delta(bytes1, bytes2):
    """Returns a series of instruction for turning bytes1 into bytes2

    Code mappings:
      equal = 0
      delete = 1
      insert = 2
      replace = 3
    """
    opcodes = difflib.SequenceMatcher(None, bytes1, bytes2).get_opcodes()
    ret_diff = []
    for code, s1, e1, s2, e2 in opcodes:
        if code == 'equal':
            ret_diff.append((0, s1, e1, None))
        if code == 'delete':
            ret_diff.append((1, s1, e1, None))
        if code == 'insert':
            ret_diff.append((2, s1, e1, bytes2[s2:e2]))
        if code == 'replace':
            ret_diff.append((3, s1, e1, bytes2[s2:e2]))
    return ret_diff


def rebuild_delta(base, delta):
    """Rebuilds a byte string from a base and delta

    Code mappings:
      equal = 0
      delete = 1
      insert = 2
      replace = 3
    """
    rebuild = []
    for code, start, end, value in delta:
        if code == 0:
            rebuild.append(base[start:end])
        if code == 1:
            pass
        if code == 2:
            rebuild.append(value)
        if code == 3:
            rebuild.append(value)
    return b''.join(rebuild)


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
