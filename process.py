import os
import posixpath
import hashlib
import ctypes
import argparse
import pickle
import functools
import difflib
import sqlite3
import contextlib
import shutil


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


def list_directories(directory, blacklist=None):
    """Returns a list of all directories not in the blacklist"""
    blacklist = [] if blacklist is None else blacklist
    return [
        d for d in next(os.walk(directory))[1]
        if d not in blacklist
    ]


def list_files(directory, blacklist=None):
    """Returns a list of all files not in the blacklist"""
    blacklist = [] if blacklist is None else blacklist
    return [
        f for f in next(os.walk(directory))[2]
        if f not in blacklist
    ]


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
    CREATE_SNAPSHOT_DB = """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            hash TEXT NOT NULL,
            branch TEXT NOT NULL,
            label TEXT,
            message TEXT,
            user TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        );
    """
    INSERT_SNAPSHOT_DB = """
        INSERT INTO snapshots (hash, branch, label, message, user)
        VALUES (:hash, :branch, :label, :message, :user)
    """
    SELECT_SNAPSHOT_DB = """SELECT * FROM snapshots"""

    def __init__(self, root, create=False):
        """Simple store all arguments and call main initialization method"""
        self.root = root
        self.create = create

        self._initialize()

    @root_directory
    def snapshot(self):
        """Takes a snapshot of the the current status of the directory"""
        top_hash = self._create_tree_node('.')
        if self._get_branch_head() == top_hash:
            return 'No changes to repository'
        self._update_branch_head(top_hash)
        self._insert_snapshot(top_hash)
        return top_hash

    @root_directory
    def list_snapshots(self):
        with contextlib.closing(sqlite3.connect(self.ssdb_path)) as con:
            con.row_factory = sqlite3.Row
            with contextlib.closing(con.cursor()) as cur:
                cur.execute(self.SELECT_SNAPSHOT_DB)
                return cur.fetchall()

    def current_branch(self):
        """Returns the name of the current branch"""
        with open(os.path.join(self.root, self.head_path), 'r') as head_file:
            return head_file.read().strip()

    def change_branch(self, branch):
        """Sets the branch to the new name then updates all files"""
        self._set_branch(branch)
        self._update_files()

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
        self.ssdb_path = os.path.join(self.vc_dir, 'snapshots')

        # Check if a .vc folder is in the directory
        if not os.path.isdir(self.vc_dir):
            # Not a version controlled directory
            if self.create:
                # Create a new version control instance
                self._create_directory()
            else:
                raise ValueError(
                    'Not a version controlled directory: {}'.format(self.root)
                )

        # Define helper attributes
        self.hashmap = {}

        # Set default HEAD path
        self._set_branch('master')

    def _set_branch(self, branch_name):
        """Sets the current branch to the given name"""
        with open(self.head_path, 'w') as head_file:
            head_file.write(branch_name)

    @root_directory
    def _create_directory(self):
        """Creates a new version control directory"""
        # Explicitly create all directories
        os.makedirs(self.vc_dir)
        os.makedirs(self.obj_dir)
        os.makedirs(self.ref_dir)
        os.makedirs(self.head_dir)
        # Make the new version control folder hidden
        ctypes.windll.kernel32.SetFileAttributesW(self.vc_dir, 0x02)

        # Create files
        self._create_hashmap()  # Create new blobcache file
        self._create_snapshots()  # Create new snapshots database

    def _update_branch_head(self, new_hash):
        branch_name = self.current_branch()
        branch_path = os.path.join(self.head_dir, branch_name)
        with open(branch_path, 'w') as branch_file:
            branch_file.write(new_hash)

    def _get_branch_head(self):
        """Returns the current hash for the current branch"""
        branch_name = self.current_branch()
        branch_path = os.path.join(self.head_dir, branch_name)
        with open(branch_path, 'r') as branch_file:
            return branch_file.read().strip()

    def _create_tree_node(self, directory):
        """Recursive function creates tree nodes for current snapshot"""
        # Validate the given root directory
        if not os.path.isdir(directory):
            raise ValueError('Not a directory: {}'.format(directory))

        # Get all files and directories for his level (excluding our vc dir)
        directories = list_directories(directory, [self.VC_DIR])
        files = list_files(directory)

        node_entries = []

        # Recursively create nodes for subdirectories
        for subdir in directories:
            node_hash = self._create_tree_node(posixjoin(directory, subdir))
            node_entries.append('tree {} {}'.format(node_hash, subdir))

        for file in files:
            node_hash = self._create_blob_node(posixjoin(directory, file))
            node_entries.append('blob {} {}'.format(node_hash, file))

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
        return hasher.hexdigest()

    def _create_hashmap(self):
        """Creates a new empty file that will store current file hashes"""
        with open(self.hashmap_path, 'wb') as hashmap_file:
            pickle.dump({}, hashmap_file)

    def _create_snapshots(self):
        """Create a new database for storing snapshot information"""
        with contextlib.closing(sqlite3.connect(self.ssdb_path)) as con:
            with con as cur:
                cur.execute(self.CREATE_SNAPSHOT_DB)

    def _insert_snapshot(self, obj_hash, label='', message='', user=''):
        """Updates snapshots database with snapshot data"""
        data = {
            'hash': obj_hash,
            'branch': self.current_branch(),
            'label': label,
            'message': message,
            'user': user,
        }
        with contextlib.closing(sqlite3.connect(self.ssdb_path)) as con:
            with con as cur:
                cur.execute(self.INSERT_SNAPSHOT_DB, data)

    def _update_hashmap(self, obj_path, obj_hash, obj_content):
        """Updates the hashmap with a pointer to the new file"""
        if obj_path in self.hashmap:
            if self.hashmap[obj_path] != obj_hash:
                self._delta_compress(self.hashmap[obj_path], obj_hash, obj_content)
        # Update hashmap
        self.hashmap[obj_path] = obj_hash

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

    def _update_files(self, snapshot_hash):
        """Updates directory with the files for the given snapshot"""
        # Get all files and directories for his level (excluding our vc dir)
        directories = list_directories(self.root, [self.VC_DIR])
        files = list_files(self.root)

        # Remove of these files and recursively remove directories
        # Remove files
        for file in files:
            os.remove(os.path.join(self.root, file))
        # Remove directories
        for directory in directories:
            shutil.rmtree(os.path.join(self.root, directory))

        top_hash = self._get_branch_head()
        self._build_tree(top_hash, self.root)

    def _build_tree(self, node_hash, current_dir):
        """Recursive function to rebuild file structure for objects"""
        content = self._read_object(node_hash).decode().rstrip()

        for line in content.split('\n'):
            obj_type, obj_hash, obj_name = self._parse_tree_line(line)
            new_path = os.path.join(current_dir, obj_name)

            # Process each type of object
            if obj_type == 'tree':
                # Make the directory
                os.makedirs(new_path)
                # Make the directory
                self._build_tree(obj_hash, new_path)
            if obj_type == 'blob':
                # Rebuild the file
                with open(new_path, 'wb') as obj_file:
                    obj_file.write(self._read_oject(obj_hash))

    def _parse_tree_line(self, line):
        """Parses each line in a tree object"""
        clean = line.rstrip()
        return clean[:5].rstrip(), clean[5:46].rstrip(), clean[46:].rstrip()


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
        'command', type=str,
        help='Command to be run'
    )
    parser.add_argument(
        '--new', '-n', action='store_true',
        help='Create a new version control repo if not existent'
    )
    parser.add_argument(
        '--checkout', '-c', type=int,
        help='Checks out the snapshot with the given id'
    )
    parser.add_argument(
        '--list', '-l', action='store_true',
        help='Lists options for the given command'
    )
    args = parser.parse_args()
    vc = VersionControl(args.root, create=args.create)

    if args.command == 'snapshot':
        if args.list:
            base_string = '{id: <3} {hash: <40} {branch: <10} {timestamp}'
            header_string = base_string.format(
                id='id', hash='hash', branch='branch', timestamp='timestamp'
            )
            print('\n' + header_string)
            print('-' * len(header_string))
            for snapshot in vc.list_snapshots():
                print(base_string.format(**snapshot))
        else:
            print(vc.snapshot())

if __name__ == '__main__':
    main()
