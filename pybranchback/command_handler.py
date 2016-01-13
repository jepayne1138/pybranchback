import argparse


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
        '-l', '--label', type=str, help='Assigns a label to the snapshot'
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

    # Process 'init'
    if args.command == 'init':
        pass

    # Process 'save'
    if args.command == 'save':
        pass

    # Process 'load'
    if args.command == 'load':
        pass

    # Process 'branch'
    if args.command == 'branch':
        pass

    # Process 'list'
    if args.command == 'list':
        pass


def find_unique(string, options):
    """Find a unique string in a list with a specified beginning"""
    return [opt for opt in options if opt.startwith(string)]
