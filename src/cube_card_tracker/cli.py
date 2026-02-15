"""
Command-line interface for Cube Card Tracker.

Provides commands for initializing, registering, and recognizing cards.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from .tracker import CubeCardTracker
from .config_manager import ConfigManager


def init_cube() -> None:
    """Initialize a new cube project."""
    parser = argparse.ArgumentParser(
        description="Initialize a new Cube Card Tracker project"
    )
    parser.add_argument(
        '--name',
        '-n',
        default='my_cube',
        help='Name of the cube (default: my_cube)'
    )
    parser.add_argument(
        '--directory',
        '-d',
        default='.',
        help='Project directory (default: current directory)'
    )
    parser.add_argument(
        '--config',
        '-c',
        help='Path to config file (default: config/cube_tracker_config.yaml)'
    )
    
    args = parser.parse_args(sys.argv[2:])
    
    # Initialize project structure
    project_dir = Path(args.directory).resolve()
    print(f"Initializing Cube Card Tracker in {project_dir}...")
    
    config_path = None
    if args.config:
        config_path = Path(args.config)
    
    manager = ConfigManager.initialize_project(project_dir, args.name)
    
    print(f"✓ Created project structure")
    print(f"✓ Created cube '{args.name}'")
    print(f"✓ Saved configuration to {manager.config_path}")
    print(f"\nNext steps:")
    print(f"  1. Add users: cube-register --add-user <name>")
    print(f"  2. Register cards: cube-register --image-set <dir> --owner <name>")
    print(f"  3. Recognize cards: cube-recognize <image-dir>")


def register_cards() -> None:
    """Register cards or add users/cubes."""
    parser = argparse.ArgumentParser(
        description="Register cards, users, or cubes"
    )
    parser.add_argument(
        '--config',
        '-c',
        help='Path to config file'
    )
    
    # User management
    parser.add_argument(
        '--add-user',
        metavar='NAME',
        help='Add a new user'
    )
    parser.add_argument(
        '--email',
        help='Email for the new user'
    )
    
    # Cube management
    parser.add_argument(
        '--add-cube',
        metavar='NAME',
        help='Add a new cube'
    )
    parser.add_argument(
        '--description',
        help='Description for the new cube'
    )
    parser.add_argument(
        '--switch-cube',
        metavar='NAME',
        help='Switch to a different cube'
    )
    
    # Card registration
    parser.add_argument(
        '--image-set',
        metavar='DIR',
        help='Directory containing card images to register'
    )
    parser.add_argument(
        '--owner',
        help='Owner of the cards (required with --image-set)'
    )
    parser.add_argument(
        '--set-name',
        help='Name for the image set (default: directory name)'
    )
    parser.add_argument(
        '--no-add-to-cube',
        action='store_true',
        help="Don't add this image set to the active cube"
    )
    
    # Info commands
    parser.add_argument(
        '--list-cubes',
        action='store_true',
        help='List all cubes'
    )
    parser.add_argument(
        '--list-users',
        action='store_true',
        help='List all users'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show tracker statistics'
    )
    
    args = parser.parse_args(sys.argv[2:])
    
    # Initialize tracker
    tracker = CubeCardTracker(args.config)
    
    if tracker.config is None:
        print("Error: No configuration found. Run 'cube-init' first.")
        sys.exit(1)
    
    # Handle different operations
    if args.add_user:
        user = tracker.add_user(args.add_user, args.email)
        print(f"✓ Added user '{user.name}'")
        if user.email:
            print(f"  Email: {user.email}")
    
    elif args.add_cube:
        cube = tracker.add_cube(args.add_cube, args.description)
        print(f"✓ Added cube '{cube.name}'")
    
    elif args.switch_cube:
        tracker.switch_cube(args.switch_cube)
        print(f"✓ Switched to cube '{args.switch_cube}'")
    
    elif args.image_set:
        if not args.owner:
            print("Error: --owner is required when registering an image set")
            sys.exit(1)
        
        image_dir = Path(args.image_set)
        set_name = args.set_name or image_dir.name
        
        print(f"Registering image set '{set_name}' for {args.owner}...")
        
        image_set = tracker.register_image_set(
            name=set_name,
            image_directory=image_dir,
            owner=args.owner,
            add_to_active_cube=not args.no_add_to_cube
        )
        
        print(f"✓ Registered {image_set.num_cards} cards")
        print(f"  Owner: {image_set.owner}")
        print(f"  Directory: {image_set.directory}")
    
    elif args.list_cubes:
        cubes = tracker.list_cubes()
        print("Configured cubes:")
        for cube_name in cubes:
            marker = " (active)" if cube_name == tracker.config.active_cube else ""
            print(f"  - {cube_name}{marker}")
    
    elif args.list_users:
        users = tracker.list_users()
        print("Registered users:")
        for user_name in users:
            user = tracker.config.users[user_name]
            print(f"  - {user_name} ({user.total_cards} cards)")
    
    elif args.stats:
        stats = tracker.get_stats()
        print("\nCube Card Tracker Statistics")
        print("=" * 60)
        print(f"Active cube: {stats['active_cube']}")
        print(f"Total cubes: {stats['total_cubes']}")
        print(f"Total users: {stats['total_users']}")
        print(f"Total image sets: {stats['total_image_sets']}")
        print(f"\nCurrent cube:")
        print(f"  Cards: {stats['cube_info']['total_cards']}")
        print(f"  Owners: {', '.join(stats['cube_info']['owners'])}")
        print(f"\nDatabase:")
        print(f"  Total cards: {stats['database_stats']['total_cards']}")
        if stats['database_stats']['total_cards'] > 0:
            print(f"  Average features: {stats['database_stats']['average_features']:.0f}")
    
    else:
        parser.print_help()


def recognize_cards() -> None:
    """Recognize cards from images."""
    parser = argparse.ArgumentParser(
        description="Recognize cards and return them to owners"
    )
    parser.add_argument(
        'image_directory',
        help='Directory containing card images to recognize'
    )
    parser.add_argument(
        '--config',
        '-c',
        help='Path to config file'
    )
    parser.add_argument(
        '--min-matches',
        type=int,
        help='Minimum number of feature matches required'
    )
    parser.add_argument(
        '--visualize',
        '-v',
        action='store_true',
        help='Create visualization images showing matches'
    )
    parser.add_argument(
        '--viz-dir',
        default='visualizations',
        help='Directory for visualization output (default: visualizations)'
    )
    parser.add_argument(
        '--single',
        '-s',
        action='store_true',
        help='Recognize a single image instead of a directory'
    )
    
    args = parser.parse_args(sys.argv[2:])
    
    # Initialize tracker
    tracker = CubeCardTracker(args.config)
    
    if tracker.config is None or tracker.recognition_engine is None:
        print("Error: Tracker not initialized. Run 'cube-init' first.")
        sys.exit(1)
    
    if args.single:
        # Recognize single image
        image_path = Path(args.image_directory)
        result = tracker.recognize_card(image_path, args.min_matches)
        
        if result:
            card_name, owner, num_matches = result
            print(f"\nRecognized: {card_name}")
            print(f"Owner: {owner}")
            print(f"Match confidence: {num_matches} feature matches")
            
            if args.visualize:
                viz_path = Path(args.viz_dir) / f"{image_path.stem}_match.jpg"
                tracker.recognition_engine.create_match_visualization(
                    image_path,
                    card_name,
                    viz_path
                )
                print(f"Visualization saved to {viz_path}")
        else:
            print("\nCard not recognized")
    else:
        # Process directory
        viz_dir = Path(args.viz_dir) if args.visualize else None
        
        returns = tracker.process_tournament_returns(
            Path(args.image_directory),
            output_visualization=args.visualize,
            viz_output_dir=viz_dir
        )
        
        if args.visualize:
            print(f"\nVisualizations saved to {viz_dir}")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Cube Card Tracker - Card recognition for cube tournaments",
        usage="""cube-tracker <command> [<args>]

Available commands:
   init       Initialize a new cube project
   register   Register cards, users, or cubes
   recognize  Recognize cards and return them to owners
"""
    )
    parser.add_argument('command', help='Command to run')
    
    # Parse just the command
    args = parser.parse_args(sys.argv[1:2])
    
    # Dispatch to command
    commands = {
        'init': init_cube,
        'register': register_cards,
        'recognize': recognize_cards,
    }
    
    if args.command not in commands:
        print(f"Error: Unknown command '{args.command}'")
        parser.print_help()
        sys.exit(1)
    
    commands[args.command]()


if __name__ == '__main__':
    main()