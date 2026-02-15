# Getting Started with Cube Card Tracker

## What You Have

A complete, production-ready Poetry package for card recognition with:

✅ **Professional Project Structure**
- Conventional Poetry/Python package layout
- Proper `src/` layout for clean imports
- Separated tests, examples, and documentation

✅ **Complete Configuration System**
- Pydantic models for type-safe configuration
- Support for YAML, TOML, and JSON formats
- Multi-cube, multi-user support
- Example configuration included

✅ **Robust Recognition Engine**
- ORB-based rotation-invariant feature detection
- Configurable matching parameters
- Visualization generation
- Statistics and reporting

✅ **CLI Interface**
- Three main commands: init, register, recognize
- Comprehensive argument parsing
- Help documentation

✅ **Development Tools**
- pytest test suite
- Black/isort formatting
- flake8 linting
- mypy type checking
- Makefile for common tasks

✅ **Documentation**
- Comprehensive README
- API documentation in docstrings
- Contributing guide
- Changelog
- Project overview

## Quick Start

### 1. Install Dependencies

If Poetry is available:
```bash
cd cube_card_tracker
poetry install
poetry shell
```

If using pip:
```bash
cd cube_card_tracker
pip install -e .
```

### 2. Initialize a Project

```bash
# Using CLI
cube-init --name my_cube --directory ~/my_cube_project

# Or using Python API
python examples/quickstart.py
```

### 3. Add Your Cards

```bash
# Add users
cube-register --add-user Alice --email alice@example.com
cube-register --add-user Bob

# Register card images
cube-register --image-set ~/photos/alice_cards --owner Alice
cube-register --image-set ~/photos/bob_cards --owner Bob
```

### 4. Recognize Cards After Tournament

```bash
# Process tournament photos
cube-recognize ~/photos/tournament_cards

# With visualizations
cube-recognize ~/photos/tournament_cards --visualize --viz-dir visualizations
```

## Project Structure

```
cube_card_tracker/
├── pyproject.toml              # Poetry configuration & dependencies
├── README.md                   # Main user documentation
├── Makefile                    # Development commands
├── LICENSE                     # MIT license
│
├── config/
│   └── example_config.yaml     # Example configuration file
│
├── src/cube_card_tracker/      # Main package
│   ├── __init__.py            # Package exports
│   ├── config.py              # Configuration models (Pydantic)
│   ├── config_manager.py      # Config loading/saving
│   ├── recognition.py         # ORB recognition engine
│   ├── tracker.py             # Main tracker class
│   └── cli.py                 # Command-line interface
│
├── tests/                      # Test suite
│   ├── __init__.py
│   └── test_config.py         # Configuration tests
│
├── examples/
│   └── quickstart.py          # Usage example
│
├── docs/
│   └── PROJECT_OVERVIEW.md    # Architecture documentation
│
└── data/                       # Data directory (created on init)
    ├── cubes/
    ├── images/
    └── databases/
```

## Configuration Management

The configuration system uses Pydantic models and supports YAML/TOML/JSON:

```yaml
# config/cube_tracker_config.yaml
active_cube: my_cube

recognition:
  min_matches: 20              # Adjust for stricter/looser matching
  orb_features: 2000          # Number of features to detect
  ratio_test_threshold: 0.75  # Lowe's ratio test

cubes:
  my_cube:
    name: my_cube
    database_path: data/databases/my_cube.pkl
    owners: [Alice, Bob]
    total_cards: 540

users:
  Alice:
    name: Alice
    email: alice@example.com
    total_cards: 270
```

## Development Commands

```bash
# Install dependencies
make install

# Run tests
make test

# Format code
make format

# Lint code
make lint

# Type check
make type-check

# All checks
make all

# Clean build artifacts
make clean
```

## Using the Python API

```python
from pathlib import Path
from cube_card_tracker import CubeCardTracker

# Initialize
tracker = CubeCardTracker()
tracker.initialize("my_cube")

# Add users
tracker.add_user("Alice", "alice@example.com")

# Register cards
tracker.register_image_set(
    name="alice_vintage",
    image_directory=Path("photos/alice"),
    owner="Alice"
)

# Recognize cards
returns = tracker.process_tournament_returns(
    Path("tournament_photos"),
    output_visualization=True,
    viz_output_dir=Path("viz")
)

# View results
for owner, cards in returns.items():
    print(f"{owner}: {len(cards)} cards")
```

## Key Features to Note

### 1. Multi-Cube Support
You can manage multiple cubes with independent databases:
```bash
cube-register --add-cube vintage_cube
cube-register --add-cube modern_cube
cube-register --switch-cube vintage_cube
```

### 2. Configurable Recognition
Adjust recognition parameters in config:
- `min_matches`: Higher = stricter (fewer false positives)
- `orb_features`: More features = better accuracy but slower
- `ratio_test_threshold`: Lower = stricter matching

### 3. Visualization
Generate images showing feature matches:
```bash
cube-recognize --visualize --viz-dir output/
```

### 4. Statistics
Track registration and recognition stats:
```bash
cube-register --stats
```

## Next Steps

### For Users
1. Install the package
2. Initialize your cube project
3. Add users and register cards
4. Start using for tournaments

### For Developers
1. Read `CONTRIBUTING.md`
2. Set up development environment
3. Run tests: `make test`
4. Add features and submit PRs

### For Deployment
1. Build package: `poetry build`
2. Publish to PyPI: `poetry publish`
3. Or create Docker container
4. Or deploy as web service

## Common Workflows

### Initial Setup
```bash
cube-init --name my_cube
cube-register --add-user Alice
cube-register --image-set photos/alice --owner Alice
```

### Adding More Cards
```bash
cube-register --image-set photos/alice_new --owner Alice --set-name alice_2024
```

### Multiple Cubes
```bash
cube-register --add-cube powered_cube
cube-register --switch-cube powered_cube
cube-register --image-set photos/power_nine --owner Alice
```

### Tournament Processing
```bash
# Take photos of all cards
cube-recognize tournament_photos/

# Or process single card
cube-recognize single_card.jpg --single
```

## Tips & Best Practices

### Photography
- **Registration**: Well-lit, upright, high resolution
- **Recognition**: Any orientation is fine, but ensure card is fully visible

### Configuration
- Start with default parameters
- Adjust `min_matches` based on your needs:
  - 25-30: Very strict (tournament finals)
  - 15-20: Balanced (general use)
  - 10-15: Lenient (lower quality photos)

### Organization
- Use meaningful image set names
- Keep reference photos organized by owner
- Regular backups of database files

### Performance
- Process tournament photos in batches
- Use `--visualize` only when debugging
- Consider parallel processing for large tournaments

## Troubleshooting

**"No features detected"**
- Check image quality
- Ensure adequate lighting
- Verify card has distinctive features

**"Card not recognized"**
- Lower `min_matches` in config
- Re-register with better photo
- Check if card was registered

**"Configuration error"**
- Validate YAML syntax
- Check file paths exist
- Run with `--help` for options

## Support & Resources

- **Documentation**: See README.md
- **Examples**: Check examples/ directory
- **Issues**: GitHub issues
- **Contributing**: See CONTRIBUTING.md

## What Makes This Special

This is a **production-ready** package with:

1. **Type Safety**: Pydantic models throughout
2. **Flexibility**: Multiple config formats, multiple cubes
3. **Extensibility**: Easy to add new features
4. **Testing**: Comprehensive test coverage
5. **Documentation**: Complete docs and examples
6. **Modern Tooling**: Poetry, Black, mypy, pytest
7. **Best Practices**: Follows Python packaging standards

Ready to track your cube cards! 🎴