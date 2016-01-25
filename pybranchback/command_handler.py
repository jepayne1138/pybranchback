import argparse
import os
import pybranchback.repository as repository


def parse_arguments():
    """Parses commands line options

    Commands:
      init - Creates a new repository
      save - Save a new snapshot of the current status of the directory
      load - Loads an existing snapshot or branch
      branch - Creates a new branch
      list - Lists snapshots and/or branches of the repository
    """
    # Create main parser and subparsers
    parser = argparse.ArgumentParser(
        description='Simple branching version control program'
    )
    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    # Parse 'init' Command
    subparsers.add_parser(
        'init', help='Creates a new repository'
    )

    # Parse 'save'
    save_parser = subparsers.add_parser(
        'save', help='Save a new snapshot of the current status of the directory'
    )
    save_parser.add_argument(
        '-l', '--label', type=str, default='',
        help='Assigns a label to the snapshot'
    )
    save_parser.add_argument(
        '-m', '--message', type=str, default='',
        help='Assigns a message to the snapshot'
    )
    save_parser.add_argument(
        '-u', '--user', type=str, default='',
        help='Assigns a user to the snapshot'
    )

    # Parse 'load'
    load_parser = subparsers.add_parser(
        'load', help='Loads an existing snapshot or branch'
    )
    load_parser.add_argument(
        'snapshot', type=str,
        help='Address (or branch name with -b) of the snapshot to be loaded'
    )
    load_parser.add_argument(
        '-c', '--create', type=str,
        help='Creates a new branch with the given label'
    )
    load_parser.add_argument(
        '-b', '--branch', action='store_true',
        help='Load the branch with the given name'
    )
    load_parser.add_argument(
        '-f', '--force', action='store_true',
        help='Forces checkout even if unsaved changes in the directory'
    )

    # Parse 'branch'
    branch_parser = subparsers.add_parser(
        'branch', help='Creates a new branch'
    )
    branch_parser.add_argument(
        'name', type=str, help='Name of the new branch'
    )
    branch_parser.add_argument(
        'snapshot', type=str, nargs='?',
        help='Identifier of the snapshot to branch from'
    )

    # Parse 'list'
    list_parser = subparsers.add_parser(
        'list', help='Lists snapshots and/or branches of the repository',
    )
    list_parser.add_argument(
        '-s', '--snapshots', action='store_true',
        help='Display list of snapshots'
    )
    list_parser.add_argument(
        '-b', '--branches', action='store_true',
        help='Display list of branches'
    )
    list_parser.add_argument(
        '-d', '--detailed', action='store_true',
        help='Displays detailed information'
    )

    # Parse and return arguments
    return parser.parse_args()


def process_commands():
    """Parses and processes command line options"""
    # Parse and handle each different command
    args = parse_arguments()

    # Get repository instance and process 'init' command
    repo = repository.Repository(
        os.getcwd(), create=(args.command == 'init')
    )

    # Process 'save'
    if args.command == 'save':
        try:
            repo.snapshot(args.label, args.message, args.user)
        except repository.RepositoryException as err:
            print(err)

    # Process 'load'
    if args.command == 'load':
        try:
            repo.checkout(args.snapshot, args.force, args.create, args.branch)
        except repository.InvalidHashException as err:
            print(invalid_hash_handler(err))
        except repository.DirtyDirectoryException as err:
            print(dirty_directory_handler(err))
            print(
                'User -f (--force) option to override. '
                'All changes since the last snapshot will be lost.'
            )

    # Process 'branch'
    if args.command == 'branch':
        try:
            repo.create_branch(args.name, args.snapshot)
        except repository.InvalidHashException as err:
            print(invalid_hash_handler(err))

    # Process 'list'
    if args.command == 'list':
        # Get information for display
        snapshots = repo.list_snapshots()
        cur_hash = repo._get_branch_head()
        cur_branch = repo.current_branch()

        # Display the snapshot header
        print('\nSnapshots:')
        base_string = '{cur}{id: <3} {hash: <40} {branch: <10} {timestamp}'
        header_string = base_string.format(
            cur=' ', id='id', hash='hash',
            branch='branch', timestamp='timestamp'
        )
        print(header_string)
        print('-' * len(header_string))

        # Display all snapshot data
        for snapshot in snapshots:
            if (snapshot['hash'] == cur_hash and
                    snapshot['branch'] == cur_branch):
                current = '*'
            else:
                current = ' '
            print(base_string.format(cur=current, **snapshot))


def invalid_hash_handler(err):
    """Generates a string message on an InvalidHashException"""
    str_lines = [str(err)]
    for match in err.results:
        str_lines.append('  - {}'.format(match))
    return '\n'.join(str_lines)


def dirty_directory_handler(err):
    """Generates a string message on an DirtyDirectyoryException"""
    return err.msg
