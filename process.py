import os
import hashlib
import ctypes



class VersionControl:
    """Very basic version control in the same vein as git

    Current structure:
    +--.vc/
    |  +--objects/
    |     +--<first 2 hash chars>/
    |        <remaining 38 harsh chars>
    """

    VC_DIR = '.vc'

    def __init__(self, root, create=False):
        self.root = root
        self.vc_dir = os.path.join(self.root, self.VC_DIR)
        self.obj_dir = os.path.join(self.vc_dir, 'objects')

        if create and not os.path.isdir(self.vc_dir):self.obj_dir
            os.makedirs(self.obj_dir)  # Makes both root dir and objects dir
            # Make the new version control folder hidden
            ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)

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

    def create_tree_node(self, directory=None):
        if directory is None:
            directory = self.root

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
            node_hash = self.create_tree_node(os.path.join(directory, subdir))
            node_entries.append('{} {}'.format(node_hash, subdir))

        for file in files:
            node_hash = self.create_blob_node(os.path.join(directory, file))
            node_entries.append('{} {}'.format(node_hash, file))

        # Join node entries into the node content
        node_content = '\n'.join(node_entries) + '\n'

        # Save the node contents to a vc object
        return self.save_node(node_content)


    def create_blob_node(self, path):
        with open(path, 'rb') as input_file:
            node_content = input_file.read()

        # Save the node contents to a vc object
        return self.save_node(node_content)

    def save_node(self, node_content):
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



def main():
    path = os.path.normpath(os.path.join(os.getcwd(), '..', 'PathTest'))
    vc = VersionControl(path).create_tree_node()


if __name__ == '__main__':
    main()
