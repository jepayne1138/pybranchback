import ctypes
import hashlib
import os
import pickle
import shutil

import pybranchback.bindifflib as bindifflib
import pybranchback.snapshotdb as ssdb
import pybranchback.utils as utils


class RepositoryException(Exception):

    """Base Exception for all Repository Exceptions"""

    pass


class InvalidHashException(RepositoryException):

    """A given snapshot hash is not found or ambiguous"""

    def __init__(self, msg, results=None):
        super().__init__(msg)
        self.msg = msg
        self.results = results


class DirtyDirectoryException(RepositoryException):

    """Checkout was attempted with changes to the directory"""

    pass


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

        # Get hash of the current snapshot and if it is detached
        old_hash, detached = self._current_snapshot_hash()

        # Check if any changes were made and if the snapshot should be saved
        if old_hash == top_hash:
            return 'No changes to repository'

        if detached:
            raise ValueError(
                'Detached HEAD. Snapshot was not saved. '
                'Save as branch to make changes.'
            )

        # Save updated hashmap
        self._save_hashmap()

        # Update current branch head with new snapshot hash
        self._update_branch_head(top_hash)

        # Insert snapshot data into the snapshot database
        self._insert_snapshot(top_hash, label, message, user)
        return top_hash

    def create_branch(self, name, snapshot=None):
        """Creates a new branch with the given name at the given snapshot

        Raises:
          InvalidHashException: If not a single unique hash is found
        """
        if snapshot is None:
            full_hash, _ = self._current_snapshot_hash()
        else:
            full_hash = self._full_hash(snapshot)

        self._update_branch_head(full_hash, name)

    def list_snapshots(self):
        """Return a list of sqlite.Row objects for each snapshot"""
        return ssdb.execute(
            self.FILES['snapshots'], ssdb.SELECT,
            row_factory=ssdb.Row, cursor='fetchall'
        )

    def checkout(self, checkout_hash, force=False, branch=None):
        """Checks out a different snapshot in the repository

        If a string is given for branch parameter, a new branch at the
        checkout location will be created

        Raises:
          InvalidHashException: If not a single unique hash is found
          DirtyDirectoryException: If changes made since last save
        """
        # Get the full hash to be checked out
        full_hash = self._full_hash(checkout_hash)

        # Raise exception on a dirty directory if no force option
        if not force:
            self._check_dirty()

        # Check if branch option was given
        if branch is not None:
            # Crate a new branch as the checkout location, then the
            # following code will simply check out that branch
            self.create_branch(branch, full_hash)

        # Check if the hash matches any current branch
        branch = self._match_branch(full_hash)
        if branch is not None:
            # Just switch branch instead of checkout out a detached HEAD
            self.switch_branch(branch)
            return

        # If the hash doesn't match a branch, we need to detach the HEAD
        self._set_branch(full_hash)

        # TODO: Switch all files in the directory
        self.update_files()

    def switch_branch(self, name, force=False):
        """Sets the branch to the given name then updates all files

        Raises:
          ValueError: No branch found with given name
          DirtyDirectoryException: If changes made since last save
        """
        # Validate given branch name
        if name not in self.list_branches():
            raise ValueError('No branch found: '.format(name))

        # Raise exception on a dirty directory if no force option
        if not force:
            self._check_dirty()

        # Switch the the existing branch
        self._set_branch(name)
        self._update_files()

    def list_branches(self):
        """Returns a list of all existing branch names"""
        return utils.list_files(self._join_root(self.DIRS['heads']))

    def _check_dirty(self):
        """Raises exception if the directory has changes since last save

        Raises:
          DirtyDirectoryException: If changes made since last save
        """
        # Get hash of directory in it's current form
        with utils.temp_wd(self.root_dir):
            dir_hash = self._get_tree_hash('.')

        # Check if any outstanding changes are in the directory
        cur_hash, _ = self._current_snapshot_hash()
        if cur_hash == dir_hash:
            # Changes have been made and we want to warn the user
            raise DirtyDirectoryException(
                'Changes have been made to the directory. '
                'Use force option to overwrite.'
            )

    def _full_hash(self, partial):
        """Returns a unique full snapshot hash from from a partial hash

        Raises:
          InvalidHashException: If not a single unique hash is found
        """
        snapshots = self.list_snapshots()
        matches = utils.get_matches(
            partial, [row['hash'] for row in snapshots],
        )

        if len(matches) < 1:
            raise InvalidHashException(
                'No snapshots found for: {}'.format(partial), matches
            )

        if len(matches) > 1:
            raise InvalidHashException(
                'No unique match for: {}'.format(partial), matches
            )

        # Get the full matched hash
        return matches[0]

    def _update_files(self):
        """Updates directory with the files for the given snapshot

        Clears out the entire directory, then rebuilds the directory from
        the repository. Would be better in the future to probably only
        overwrite files that needed updates and remove files that no longer
        should be there, but this was simple and I can optimize later if
        it needs better performance.
        """
        # Get all files and directories for this level (excluding repo)
        directories = utils.list_directories(self.root, [self.REPO_DIR])
        files = utils.list_files(self.root)

        # Remove all of these files and recursively remove directories
        # Remove files
        for file in files:
            os.remove(self._join_root(file))
        # Remove directories
        for directory in directories:
            shutil.rmtree(self._join_root(directory))

        # Get hash of the current snapshot
        top_hash, _ = self._current_snapshot_hash()

        self._build_tree(top_hash, self.root)

    def _build_tree(self, node_hash, current_path):
        """Recursive function to rebuild file structure for objects"""
        content = self._read_object(node_hash).decode().rstrip()

        for line in content.split('\n'):
            obj_type, obj_hash, obj_name = self._parse_tree_line(line)
            new_path = os.path.join(current_path, obj_name)

            # Process each type of object
            if obj_type == 'tree':
                # Make the directory
                os.makedirs(new_path)
                # Make the directory
                self._build_tree(obj_hash, new_path)
            if obj_type == 'blob':
                # Rebuild the file
                with open(new_path, 'wb') as obj_file:
                    obj_file.write(self._read_object(obj_hash))

    def _parse_tree_line(self, line):
        """Parses each line in a tree object"""
        clean = line.rstrip()
        return clean[:5].rstrip(), clean[5:46].rstrip(), clean[46:].rstrip()

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

    def _current_snapshot_hash(self):
        """Returns the hash of the current snapshot and if it is detached"""
        # Check HEAD for branch name of snapshot address
        branch = self.current_branch()

        # Branch might not be a branch, could be detached address
        if branch not in self.list_branches():
            # Branch name is actually detached address
            snapshot_hash = branch
            detached = True
        else:
            snapshot_hash = self._get_branch_head()
            detached = False

        return (snapshot_hash, detached)

    def _get_branch_head(self, branch=None):
        """Returns the hash for the given branch"""
        if branch is None:
            branch = self.current_branch()

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
        if branch is None:
            branch = self.current_branch()

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

    def _get_tree_hash(self, directory):
        """Recursively generate hashes of nodes for current directory"""
        # Validate the given root directory
        if not os.path.isdir(directory):
            raise ValueError('Not a directory: {}'.format(directory))

        # Get all files & directories for this level (excluding our pbb dir)
        directories = utils.list_directories(directory, [self.REPO_DIR])
        files = utils.list_files(directory)

        node_entries = []

        # Recursively create nodes for subdirectories
        for subdir in directories:
            node_hash = self._get_tree_hash(
                utils.posixjoin(directory, subdir)
            )
            node_entries.append('tree {} {}'.format(node_hash, subdir))

        for file in files:
            node_hash = self._get_blob_hash(
                utils.posixjoin(directory, file)
            )
            node_entries.append('blob {} {}'.format(node_hash, file))

        # Join node entries into the node content
        node_content = '\n'.join(node_entries) + '\n'

        # Get node content hash
        return self._hash_diget(self._byte_convert(node_content))

    def _get_blob_hash(self, path):
        """Get the hash for a given blob file at the path"""
        with open(path, 'rb') as input_file:
            node_content = input_file.read()

        # Convert to bytes if necessary
        bytes_content = self._byte_convert(node_content)

        # Get node content hash
        return self._hash_diget(bytes_content)

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

        branches = self.list_branches()

        # Reach each branch reference for matching hash
        for branch in branches:
            with open(os.path.join(head_dir, branch), 'r') as branch_file:
                branch_hash = branch_file.read().strip()
            if branch_hash == snapshot_hash:
                return branch

        # If no matching hashes were found, return None
        return None
