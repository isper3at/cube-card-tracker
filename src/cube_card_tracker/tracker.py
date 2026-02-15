"""
Main Cube Card Tracker class that integrates configuration and recognition.

This module provides the high-level API for the application.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .config import AppConfig, CubeConfig, UserConfig, ImageSetConfig
from .config_manager import ConfigManager
from .recognition import CardRecognitionEngine, CardRecord


class CubeCardTracker:
    """
    Main application class for the Cube Card Tracker.
    
    Integrates configuration management and card recognition to provide
    a complete system for tracking cube cards and returning them to owners.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the tracker.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        self.config_manager = ConfigManager(config_path)
        self.config: Optional[AppConfig] = None
        self.recognition_engine: Optional[CardRecognitionEngine] = None
        
        # Try to load existing configuration
        try:
            self.config = self.config_manager.load()
            self._initialize_recognition_engine()
        except FileNotFoundError:
            # No config exists yet
            pass
    
    def initialize(self, cube_name: str = "my_cube") -> None:
        """
        Initialize a new tracker with default configuration.
        
        Args:
            cube_name: Name for the default cube
        """
        self.config = self.config_manager.create_default(cube_name)
        self.config_manager.save()
        self._initialize_recognition_engine()
    
    def _initialize_recognition_engine(self) -> None:
        """Initialize the recognition engine with the active cube's database."""
        if self.config is None:
            raise ValueError("Configuration not loaded")
        
        active_cube = self.config.get_active_cube()
        if active_cube is None:
            raise ValueError(f"Active cube '{self.config.active_cube}' not found")
        
        self.recognition_engine = CardRecognitionEngine(
            database_path=active_cube.database_path,
            config=self.config.recognition
        )
    
    def add_cube(self, name: str, description: Optional[str] = None) -> CubeConfig:
        """
        Add a new cube to the tracker.
        
        Args:
            name: Name of the new cube
            description: Optional description
            
        Returns:
            The created CubeConfig
        """
        if self.config is None:
            raise ValueError("Tracker not initialized")
        
        cube = self.config_manager.add_cube(name, description)
        self.config_manager.save()
        return cube
    
    def switch_cube(self, cube_name: str) -> None:
        """
        Switch to a different cube.
        
        Args:
            cube_name: Name of the cube to switch to
            
        Raises:
            ValueError: If cube doesn't exist
        """
        if self.config is None:
            raise ValueError("Tracker not initialized")
        
        if cube_name not in self.config.cubes:
            raise ValueError(f"Cube '{cube_name}' not found")
        
        self.config.active_cube = cube_name
        self._initialize_recognition_engine()
        self.config_manager.save()
    
    def add_user(self, name: str, email: Optional[str] = None) -> UserConfig:
        """
        Add a new user to the tracker.
        
        Args:
            name: User's name
            email: User's email address
            
        Returns:
            The created UserConfig
        """
        if self.config is None:
            raise ValueError("Tracker not initialized")
        
        user = self.config_manager.add_user(name, email)
        self.config_manager.save()
        return user
    
    def register_image_set(
        self,
        name: str,
        image_directory: Path,
        owner: str,
        add_to_active_cube: bool = True
    ) -> ImageSetConfig:
        """
        Register a new image set and optionally add to active cube.
        
        Args:
            name: Name of the image set
            image_directory: Directory containing card images
            owner: Owner's name
            add_to_active_cube: Whether to add this set to the active cube
            
        Returns:
            The created ImageSetConfig
        """
        if self.config is None or self.recognition_engine is None:
            raise ValueError("Tracker not initialized")
        
        # Ensure owner exists
        if owner not in self.config.users:
            self.add_user(owner)
        
        # Create image set config
        image_set = self.config_manager.add_image_set(name, image_directory, owner)
        
        # Register cards with recognition engine
        image_dir = Path(image_directory)
        if not image_dir.exists():
            raise ValueError(f"Image directory does not exist: {image_directory}")
        
        # Find all image files
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_files = []
        for ext in image_extensions:
            image_files.extend(image_dir.glob(f"*{ext}"))
            image_files.extend(image_dir.glob(f"*{ext.upper()}"))
        
        # Register each image
        cards_to_register = []
        for img_path in image_files:
            # Use filename (without extension) as card name
            card_name = img_path.stem
            # Create unique name with owner prefix
            unique_name = f"{owner}_{name}_{card_name}"
            cards_to_register.append((img_path, unique_name, owner))
        
        registered = self.recognition_engine.register_batch(cards_to_register)
        
        # Update image set with card count
        image_set.num_cards = len(registered)
        
        # Update user's total cards
        self.config.users[owner].total_cards += len(registered)
        
        # Add to active cube if requested
        if add_to_active_cube:
            active_cube = self.config.get_active_cube()
            if active_cube and name not in active_cube.image_sets:
                active_cube.image_sets.append(name)
                if owner not in active_cube.owners:
                    active_cube.owners.append(owner)
                active_cube.total_cards += len(registered)
                active_cube.last_updated = datetime.now()
        
        self.config_manager.save()
        return image_set
    
    def recognize_card(
        self,
        image_path: Path,
        min_matches: Optional[int] = None
    ) -> Optional[Tuple[str, str, int]]:
        """
        Recognize a card from an image.
        
        Args:
            image_path: Path to the card image
            min_matches: Minimum number of matches required
            
        Returns:
            Tuple of (card_name, owner, num_matches) or None
        """
        if self.recognition_engine is None:
            raise ValueError("Tracker not initialized")
        
        return self.recognition_engine.recognize_card(image_path, min_matches)
    
    def process_tournament_returns(
        self,
        image_directory: Path,
        output_visualization: bool = False,
        viz_output_dir: Optional[Path] = None
    ) -> Dict[str, List[str]]:
        """
        Process all cards in a directory and group by owner.
        
        Args:
            image_directory: Directory containing card images to process
            output_visualization: Whether to create visualizations
            viz_output_dir: Directory for visualizations (if enabled)
            
        Returns:
            Dictionary mapping owner names to lists of their cards
        """
        if self.recognition_engine is None:
            raise ValueError("Tracker not initialized")
        
        returns = {}
        unrecognized = []
        
        # Find all image files
        image_dir = Path(image_directory)
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_files = []
        for ext in image_extensions:
            image_files.extend(image_dir.glob(f"*{ext}"))
            image_files.extend(image_dir.glob(f"*{ext.upper()}"))
        
        print(f"\nProcessing {len(image_files)} images...")
        
        for img_path in image_files:
            result = self.recognition_engine.recognize_card(img_path)
            
            if result:
                card_name, owner, num_matches = result
                if owner not in returns:
                    returns[owner] = []
                returns[owner].append(card_name)
                print(f"✓ {img_path.name} -> {card_name} (belongs to {owner})")
                
                # Create visualization if requested
                if output_visualization and viz_output_dir:
                    viz_path = Path(viz_output_dir) / f"{img_path.stem}_match.jpg"
                    self.recognition_engine.create_match_visualization(
                        img_path,
                        card_name,
                        viz_path
                    )
            else:
                unrecognized.append(str(img_path))
                print(f"✗ {img_path.name} -> NOT RECOGNIZED")
        
        # Print summary
        self._print_tournament_summary(returns, unrecognized)
        
        return returns
    
    def _print_tournament_summary(
        self,
        returns: Dict[str, List[str]],
        unrecognized: List[str]
    ) -> None:
        """Print a formatted tournament return summary."""
        print("\n" + "="*60)
        print("TOURNAMENT CARD RETURN SUMMARY")
        print("="*60)
        
        for owner, cards in sorted(returns.items()):
            print(f"\n{owner}:")
            for card in sorted(cards):
                print(f"  - {card}")
        
        if unrecognized:
            print(f"\nUnrecognized cards ({len(unrecognized)}):")
            for path in unrecognized:
                print(f"  - {Path(path).name}")
    
    def get_stats(self) -> Dict:
        """
        Get comprehensive statistics about the tracker.
        
        Returns:
            Dictionary with tracker statistics
        """
        if self.config is None or self.recognition_engine is None:
            return {"error": "Tracker not initialized"}
        
        active_cube = self.config.get_active_cube()
        db_stats = self.recognition_engine.get_database_stats()
        
        return {
            'active_cube': self.config.active_cube,
            'total_cubes': len(self.config.cubes),
            'total_users': len(self.config.users),
            'total_image_sets': len(self.config.image_sets),
            'cube_info': {
                'name': active_cube.name if active_cube else None,
                'total_cards': active_cube.total_cards if active_cube else 0,
                'owners': active_cube.owners if active_cube else [],
            },
            'database_stats': db_stats
        }
    
    def list_cubes(self) -> List[str]:
        """List all configured cubes."""
        if self.config is None:
            return []
        return list(self.config.cubes.keys())
    
    def list_users(self) -> List[str]:
        """List all registered users."""
        if self.config is None:
            return []
        return list(self.config.users.keys())
    
    def list_image_sets(self) -> List[str]:
        """List all registered image sets."""
        if self.config is None:
            return []
        return list(self.config.image_sets.keys())