import argparse
import os
from pybranchback.repository import Repository
import pybranchback.utils as utils


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
        'snapshot', type=str, help='Address of the snapshot to be loaded'
    )
    load_parser.add_argument(
        '-b', '--branch', type=str,
        help='Creates a new branch with the given label'
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
    repo = Repository(
        os.getcwd(), create=(args.command == 'init')
    )

    # Process 'save'
    if args.command == 'save':
        repo.snapshot(args.label, args.message, args.user)

    # Process 'load'
    if args.command == 'load':
        matches = repo.checkout(args.snapshot)

        # On error, display some helpful information
        if len(matches) == 0:
            print('No snapshots found for: {args.snapshot}'.format(args=args))
        if len(matches) > 1:
            print('No unique match for: {args.snapshot}'.format(args=args))
            for match in matches:
                print('  - {}'.format(match))

    # Process 'branch'
    if args.command == 'branch':
        pass

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


def find_unique(string, options):
    """Find a unique string in a list with a specified beginning"""
    return [opt for opt in options if opt.startwith(string)]
