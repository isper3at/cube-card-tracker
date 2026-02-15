"""
Tests for configuration models and manager.
"""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

from cube_card_tracker.config import (
    AppConfig,
    CubeConfig,
    UserConfig,
    ImageSetConfig,
    RecognitionConfig
)
from cube_card_tracker.config_manager import ConfigManager


class TestConfigModels:
    """Test configuration models."""
    
    def test_recognition_config_defaults(self):
        """Test RecognitionConfig default values."""
        config = RecognitionConfig()
        assert config.min_matches == 20
        assert config.orb_features == 2000
        assert config.ratio_test_threshold == 0.75
    
    def test_recognition_config_validation(self):
        """Test RecognitionConfig validation."""
        # Valid config
        config = RecognitionConfig(min_matches=15, orb_features=1500)
        assert config.min_matches == 15
        
        # Invalid min_matches (too low)
        with pytest.raises(ValueError):
            RecognitionConfig(min_matches=3)
    
    def test_cube_config_creation(self):
        """Test CubeConfig creation."""
        cube = CubeConfig(
            name="test_cube",
            description="Test cube",
            database_path=Path("data/databases/test.pkl")
        )
        assert cube.name == "test_cube"
        assert cube.total_cards == 0
        assert isinstance(cube.created_at, datetime)
    
    def test_user_config_creation(self):
        """Test UserConfig creation."""
        user = UserConfig(name="Alice", email="alice@example.com")
        assert user.name == "Alice"
        assert user.email == "alice@example.com"
        assert user.total_cards == 0
        assert user.image_sets == []
    
    def test_image_set_config_creation(self):
        """Test ImageSetConfig creation."""
        img_set = ImageSetConfig(
            name="alice_set_1",
            directory=Path("data/images/alice"),
            owner="Alice"
        )
        assert img_set.name == "alice_set_1"
        assert img_set.owner == "Alice"
        assert isinstance(img_set.registered_at, datetime)
    
    def test_app_config_operations(self):
        """Test AppConfig helper methods."""
        config = AppConfig(
            active_cube="test_cube",
            cubes={},
            users={},
            image_sets={}
        )
        
        # Add cube
        cube = CubeConfig(
            name="test_cube",
            description="Test",
            database_path=Path("test.pkl")
        )
        config.add_cube(cube)
        assert "test_cube" in config.cubes
        
        # Add user
        user = UserConfig(name="Alice")
        config.add_user(user)
        assert "Alice" in config.users
        
        # Add image set
        img_set = ImageSetConfig(
            name="alice_set",
            directory=Path("images"),
            owner="Alice"
        )
        config.add_image_set(img_set)
        assert "alice_set" in config.image_sets
        assert "alice_set" in config.users["Alice"].image_sets


class TestConfigManager:
    """Test configuration manager."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)
    
    def test_create_default_config(self, temp_dir):
        """Test creating default configuration."""
        config_path = temp_dir / "config" / "test.yaml"
        manager = ConfigManager(config_path)
        
        config = manager.create_default("test_cube")
        assert config.active_cube == "test_cube"
        assert "test_cube" in config.cubes
    
    def test_save_and_load_yaml(self, temp_dir):
        """Test saving and loading YAML configuration."""
        config_path = temp_dir / "config.yaml"
        manager = ConfigManager(config_path)
        
        # Create and save config
        config = manager.create_default("test_cube")
        manager.save(config)
        
        # Load config
        loaded_config = manager.load()
        assert loaded_config.active_cube == "test_cube"
        assert "test_cube" in loaded_config.cubes
    
    def test_save_and_load_json(self, temp_dir):
        """Test saving and loading JSON configuration."""
        config_path = temp_dir / "config.json"
        manager = ConfigManager(config_path)
        
        # Create and save config
        config = manager.create_default("test_cube")
        manager.save(config)
        
        # Load config
        loaded_config = manager.load()
        assert loaded_config.active_cube == "test_cube"
    
    def test_initialize_project(self, temp_dir):
        """Test project initialization."""
        manager = ConfigManager.initialize_project(temp_dir, "my_cube")
        
        # Check directories were created
        assert (temp_dir / "config").exists()
        assert (temp_dir / "data" / "cubes").exists()
        assert (temp_dir / "data" / "images").exists()
        assert (temp_dir / "data" / "databases").exists()
        
        # Check config was created
        assert manager.config_path.exists()
        assert manager.config is not None
    
    def test_add_operations(self, temp_dir):
        """Test add_cube, add_user, add_image_set operations."""
        config_path = temp_dir / "config.yaml"
        manager = ConfigManager(config_path)
        manager.create_default("test_cube")
        
        # Add cube
        cube = manager.add_cube("new_cube", "New test cube")
        assert cube.name == "new_cube"
        assert "new_cube" in manager.config.cubes
        
        # Add user
        user = manager.add_user("Bob", "bob@example.com")
        assert user.name == "Bob"
        assert "Bob" in manager.config.users
        
        # Add image set
        img_set = manager.add_image_set(
            "bob_set",
            temp_dir / "images",
            "Bob"
        )
        assert img_set.name == "bob_set"
        assert "bob_set" in manager.config.image_sets