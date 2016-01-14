import ctypes
import hashlib
import os
import pickle
import pybranchback.bindifflib as bindifflib
import pybranchback.snapshotdb as ssdb
import pybranchback.utils as utils


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

    REPO_DIR = '.pbb'
    DIRS = {
        'top': REPO_DIR,
        'objects': utils.posixjoin(REPO_DIR, 'objects'),
        'refs': utils.posixjoin(REPO_DIR, 'refs'),
        'heads': utils.posixjoin(REPO_DIR, 'refs', 'heads'),
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
            self._join_root(self.REPO_DIR), 0x02
        )

        # Create HEAD file and set branch to 'master'
        self._set_branch('master')

        # Create objhashcache file and set as empty
        self._save_hashmap()

        # Create the snapshots database
        ssdb.execute(self.FILES['snapshots'], ssdb.CREATE)

    def current_branch(self):
        """Returns the name of the current branch"""
        with open(self._join_root(self.FILES['head']), 'r') as head_file:
            return head_file.read().strip()

    def snapshot(self, label='', message='', user=''):
        """Takes a snapshot of the the current status of the directory"""
        # Recursively build tree structure
        with utils.temp_wd(self.root_dir):
            top_hash = self._create_tree_node('.')

        # Check if any changes were made and if the snapshot should be saved
        if self._get_branch_head() == top_hash:
            return 'No changes to repository'

        # Save updated hashmap
        self._save_hashmap()

        # Update current branch head with new snapshot hash
        self._update_branch_head(top_hash)

        # Insert snapshot data into the snapshot database
        self._insert_snapshot(top_hash, label, message, user)
        return top_hash

    def list_snapshots(self):
        """Return a list of sqlite.Row objects for each snapshot"""
        return ssdb.execute(
            self.FILES['snapshots'], ssdb.SELECT,
            row_factory=ssdb.Row, cursor='fetchall'
        )

    def checkout(self, checkout_hash):
        """Checks out a different snapshot in the repository"""
        snapshots = self.list_snapshots()
        matches = utils.get_matches(
            checkout_hash, [row['hash'] for row in snapshots],
        )

        # If a unique match not found, return the list of matches of display
        if len(matches) != 1:
            return matches

        # Get the full matched hash
        full_hash = matches[0]

        # Check if the hash matches any current branch
        branch = self._match_branch(full_hash)
        if branch is not None:
            # Just switch branch instead of checkout out a detached HEAD
            self.switch_branch(branch)
            return

        # If the hash doesn't match a branch, we need to detach the HEAD
        self._set_branch(full_hash)

        # TODO: Switch all files in the directory

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

    def _get_branch_head(self, branch=None):
        """Returns the hash for the given branch"""
        branch = self.current_branch() if branch is None else branch

        # Construct path to the reference file
        ref_path = self._join_root(os.path.join(self.DIRS['heads'], branch))
        try:
            with open(ref_path, 'r') as branch_file:
                return branch_file.read().strip()
        except FileNotFoundError:
            # The branch file does not exist yet (new repo)
            return None

    def _update_branch_head(self, new_hash, branch=None):
        """Updates a branch with a new hash address to a head snapshot"""
        branch = self.current_branch() if branch is None else branch

        # Construct path to the reference file
        ref_path = self._join_root(os.path.join(self.DIRS['heads'], branch))

        # Overwrite the reference file with the new hash
        with open(ref_path, 'w') as ref_file:
            ref_file.write(new_hash)

    def _insert_snapshot(self, obj_hash, label='', message='', user=''):
        """Updates snapshots database with snapshot data"""
        data = {
            'hash': obj_hash,
            'branch': self.current_branch(),
            'label': label,
            'message': message,
            'user': user,
        }

        ssdb.execute(self.FILES['snapshots'], ssdb.INSERT, data, commit=True)

    def _create_tree_node(self, directory):
        """Recursive function creates tree nodes for current snapshot"""
        # Validate the given root directory
        if not os.path.isdir(directory):
            raise ValueError('Not a directory: {}'.format(directory))

        # Get all files & directories for this level (excluding our pbb dir)
        directories = utils.list_directories(directory, [self.REPO_DIR])
        files = utils.list_files(directory)

        node_entries = []

        # Recursively create nodes for subdirectories
        for subdir in directories:
            node_hash = self._create_tree_node(
                utils.posixjoin(directory, subdir)
            )
            node_entries.append('tree {} {}'.format(node_hash, subdir))

        for file in files:
            node_hash = self._create_blob_node(
                utils.posixjoin(directory, file)
            )
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
        obj_dir = self._join_root(
            os.path.join(self.DIRS['objects'], digest[:2])
        )
        obj_path = os.path.join(obj_dir, digest[2:])

        # Make the directory if it does not exist
        os.makedirs(obj_dir, exist_ok=True)

        # Binary compress new files or return original if no reference
        final_content = self._delta_compress(path, digest, bytes_content)

        # Return the hash with no further processing if no changes
        if final_content is None:
            return digest

        # Write the final content to the final object file
        with open(obj_path, 'wb') as obj_file:
            obj_file.write(final_content)

        # Update hashmap
        self.objhashcache[path] = digest

        return digest

    def _byte_convert(self, payload):
        """Check that an object is bytes, otherwise attempt to encode"""
        if type(payload) is bytes:
            return payload

        # Try to encode if not bytes already
        return payload.encode()

    def _hash_diget(self, payload):
        """Returns a hex digest for the hash of the given payload"""
        hasher = hashlib.sha1()
        hasher.update(payload)
        return hasher.hexdigest()

    def _delta_compress(self, obj_path, obj_hash, obj_content):
        """Compresses a new object file by replacing with a delta

        Returns either a patch to a previous version of this file or returns
        the original content to be written as a new reference.

        NOTE:
          The file name hash no longer will reflect the true file
          content, rather the content that the delta reflects.
        """
        # Check if the path is in the objhashcache
        if obj_path not in self.objhashcache:
            # Return the uncompress content
            return obj_content

        # Check if changes were made to the object file
        if self.objhashcache[obj_path] == obj_hash:
            return None

        # Get paths to the reference file
        ref_hash = self.objhashcache[obj_path]

        # Calculate delta from the reference version to the new version
        patch = bindifflib.diff(
            self._byte_convert(obj_content),
            self._read_object(ref_hash),
        )

        # Format delta contents
        patch_tuple = (obj_hash, patch)
        return pickle.dumps(patch_tuple)

    def _read_object(self, obj_hash):
        """Reads and returns the contents of an object file with given hash

        Recursively rebuilds any necessary files from their deltas
        """
        obj_dir = self._join_root(
            os.path.join(self.DIRS['objects'], obj_hash[:2])
        )
        obj_path = os.path.join(obj_dir, obj_hash[2:])

        # Read the object file content
        with open(obj_path, 'rb') as obj_file:
            content = obj_file.read()

        # Check if a delta by comparing the content to the hash value
        if obj_hash != self._hash_diget(content):
            # Delta object must be rebuilt
            patch_tuple = pickle.loads(content)
            print(patch_tuple)
            ref_content = self._read_object(patch_tuple[0])
            return bindifflib.patch(patch_tuple[1], ref_content)

        # If object is not a delta, simply return it's content
        return content

    def _match_branch(self, snapshot_hash):
        """Checks if any current branch current matches the given hash"""
        head_dir = self._join_root(self.DIRS['heads'])

        branches = utils.list_files(head_dir)

        # Reach each branch reference for matching hash
        for branch in branches:
            with open(os.path.join(head_dir, branch), 'r') as branch_file:
                branch_hash = branch_file.read().strip()
            if branch_hash == snapshot_hash:
                return branch

        # If no matching hashes were found, return None
        return None
