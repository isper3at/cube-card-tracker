# Cube Card Tracker

A rotation-invariant card recognition system for tracking cube cards and returning them to their owners after tournaments.

## Features

- **Rotation-Invariant Recognition**: Uses ORB (Oriented FAST and Rotated BRIEF) feature detection
- **Configuration-Driven**: YAML/TOML/JSON configuration for managing multiple cubes
- **Multi-User Support**: Track cards from multiple owners
- **Persistent Storage**: Save card databases and configurations
- **CLI Interface**: Command-line tools for all operations
- **Poetry-Managed**: Modern Python packaging with Poetry

## Installation

### Using Poetry (Recommended)

```bash
# Clone or navigate to the project directory
cd cube_card_tracker

# Install dependencies
poetry install

# Activate the virtual environment
poetry shell
```

### Using pip

```bash
pip install -e .
```

## Quick Start

### 1. Initialize a New Project

```bash
# Initialize in current directory
cube-init --name my_cube

# Or specify a directory
cube-init --name my_cube --directory ~/my_cube_project
```

This creates:
```
my_cube_project/
├── config/
│   └── cube_tracker_config.yaml
├── data/
│   ├── cubes/
│   ├── images/
│   └── databases/
```

### 2. Add Users

```bash
# Add users who own cards
cube-register --add-user Alice --email alice@example.com
cube-register --add-user Bob --email bob@example.com
```

### 3. Register Card Images

```bash
# Register Alice's cards
cube-register --image-set ~/photos/alice_cards --owner Alice

# Register Bob's cards
cube-register --image-set ~/photos/bob_cards --owner Bob
```

### 4. Recognize Cards After Tournament

```bash
# Process all tournament photos
cube-recognize ~/photos/tournament_cards

# With visualizations
cube-recognize ~/photos/tournament_cards --visualize
```

## Configuration

The configuration file (`config/cube_tracker_config.yaml`) controls:

- **Active Cube**: Which cube is currently being used
- **Users**: Registered card owners
- **Image Sets**: Collections of card images
- **Recognition Settings**: Algorithm parameters

### Example Configuration

```yaml
active_cube: my_cube

recognition:
  min_matches: 20
  orb_features: 2000
  ratio_test_threshold: 0.75

cubes:
  my_cube:
    name: my_cube
    description: My Cube
    database_path: data/databases/my_cube.pkl
    owners:
      - Alice
      - Bob
    total_cards: 540

users:
  Alice:
    name: Alice
    email: alice@example.com
    total_cards: 270
  Bob:
    name: Bob
    email: bob@example.com
    total_cards: 270
```

See `config/example_config.yaml` for a complete example.

## CLI Reference

### cube-init

Initialize a new project with configuration and directory structure.

```bash
cube-init [OPTIONS]

Options:
  --name, -n NAME          Cube name (default: my_cube)
  --directory, -d DIR      Project directory (default: current)
  --config, -c PATH        Custom config file path
```

### cube-register

Register cards, users, or manage cubes.

```bash
# User management
cube-register --add-user NAME [--email EMAIL]
cube-register --list-users

# Cube management
cube-register --add-cube NAME [--description DESC]
cube-register --switch-cube NAME
cube-register --list-cubes

# Card registration
cube-register --image-set DIR --owner NAME [--set-name NAME]

# Information
cube-register --stats

Options:
  --config, -c PATH        Config file path
  --add-user NAME          Add a new user
  --email EMAIL            User's email
  --add-cube NAME          Add a new cube
  --description DESC       Cube description
  --switch-cube NAME       Switch active cube
  --image-set DIR          Register images from directory
  --owner NAME             Owner of the images
  --set-name NAME          Name for image set
  --no-add-to-cube         Don't add to active cube
  --list-cubes             List all cubes
  --list-users             List all users
  --stats                  Show statistics
```

### cube-recognize

Recognize cards from images.

```bash
cube-recognize IMAGE_DIR [OPTIONS]

Options:
  --config, -c PATH        Config file path
  --min-matches N          Minimum matches required
  --visualize, -v          Create match visualizations
  --viz-dir DIR            Visualization output directory
  --single, -s             Recognize single image
```

## Python API

You can also use the tracker programmatically:

```python
from cube_card_tracker import CubeCardTracker
from pathlib import Path

# Initialize tracker
tracker = CubeCardTracker()
tracker.initialize("my_cube")

# Add users
tracker.add_user("Alice", "alice@example.com")
tracker.add_user("Bob", "bob@example.com")

# Register image sets
tracker.register_image_set(
    name="alice_cards",
    image_directory=Path("photos/alice"),
    owner="Alice"
)

# Recognize cards
returns = tracker.process_tournament_returns(
    Path("photos/tournament"),
    output_visualization=True,
    viz_output_dir=Path("output/viz")
)

# Print results
for owner, cards in returns.items():
    print(f"{owner}: {len(cards)} cards")
```

## Project Structure

```
cube_card_tracker/
├── pyproject.toml              # Poetry configuration
├── README.md                   # This file
├── config/                     # Configuration files
│   └── example_config.yaml     # Example configuration
├── data/                       # Data directory
│   ├── cubes/                  # Cube metadata
│   ├── images/                 # Reference images
│   └── databases/              # Card databases
├── src/
│   └── cube_card_tracker/
│       ├── __init__.py         # Package initialization
│       ├── config.py           # Configuration models
│       ├── config_manager.py   # Config loading/saving
│       ├── recognition.py      # Recognition engine
│       ├── tracker.py          # Main tracker class
│       └── cli.py              # CLI interface
└── tests/                      # Test suite
    ├── __init__.py
    └── test_config.py
```

## Configuration Schema

### RecognitionConfig

- `min_matches` (int, 5-100): Minimum feature matches for positive ID
- `orb_features` (int, 500-10000): Number of ORB features to detect
- `ratio_test_threshold` (float, 0.5-0.95): Lowe's ratio test threshold

### CubeConfig

- `name` (str): Cube identifier
- `description` (str): Human-readable description
- `database_path` (Path): Path to card database file
- `image_sets` (list): Names of included image sets
- `owners` (list): Users with cards in this cube
- `total_cards` (int): Total number of cards

### UserConfig

- `name` (str): User's name
- `email` (str, optional): User's email
- `image_sets` (list): Names of user's image sets
- `total_cards` (int): Total cards registered

### ImageSetConfig

- `name` (str): Image set identifier
- `directory` (Path): Directory with card images
- `owner` (str): Owner's name
- `num_cards` (int): Number of cards in set

## Development

### Running Tests

```bash
poetry run pytest
```

### Code Formatting

```bash
poetry run black src tests
poetry run isort src tests
```

### Type Checking

```bash
poetry run mypy src
```

### Linting

```bash
poetry run flake8 src tests
```

## How It Works

### Feature Detection (ORB)

The system uses ORB (Oriented FAST and Rotated BRIEF):
- Detects distinctive keypoints in images
- Computes rotation-invariant descriptors
- Handles cards at any angle, including upside-down

### Matching Process

1. Extract features from query image
2. Compare against all registered cards using feature matching
3. Apply Lowe's ratio test to filter good matches
4. Return card with most matches above threshold

### Configuration Management

- Pydantic models for type-safe configuration
- Support for YAML, TOML, and JSON formats
- Automatic validation and serialization
- Persistent storage with datetime handling

## Best Practices

### Photography Tips

**Registration Photos:**
- Well-lit, even lighting
- Card upright and centered
- High resolution (≥1000x700 pixels)
- Minimal glare or reflections

**Tournament Photos:**
- Reasonable lighting
- Card fully visible
- Any orientation is fine

### Recognition Parameters

Adjust `min_matches` in config:
- **20-30**: Strict matching (high-quality photos)
- **15-20**: Balanced (default)
- **10-15**: Lenient (lower quality photos)

### Managing Multiple Cubes

```bash
# Create multiple cubes
cube-register --add-cube vintage_cube
cube-register --add-cube modern_cube

# Switch between them
cube-register --switch-cube vintage_cube
cube-recognize photos/vintage_tournament

cube-register --switch-cube modern_cube
cube-recognize photos/modern_tournament
```

## Troubleshooting

### "No features detected"
- Improve image quality and resolution
- Ensure adequate contrast
- Better lighting

### "Card not recognized"
- Lower `min_matches` threshold in config
- Re-register with better quality photo
- Verify card is fully visible

### Configuration errors
- Validate YAML syntax
- Check file paths are correct
- Ensure required fields are present

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request