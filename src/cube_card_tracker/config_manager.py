"""
Configuration management for loading and saving application configuration.

Supports both YAML and TOML formats.
"""

import json
import yaml
import toml
from pathlib import Path
from typing import Optional, Union
from datetime import datetime

from .config import AppConfig, CubeConfig, UserConfig, ImageSetConfig


class ConfigManager:
    """Manages loading and saving of application configuration."""
    
    DEFAULT_CONFIG_NAME = "cube_tracker_config.yaml"
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to the configuration file. If None, uses default.
        """
        if config_path is None:
            config_path = Path("config") / self.DEFAULT_CONFIG_NAME
        
        self.config_path = Path(config_path)
        self.config: Optional[AppConfig] = None
    
    def load(self) -> AppConfig:
        """
        Load configuration from file.
        
        Returns:
            AppConfig object
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file format is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        # Determine format from extension
        suffix = self.config_path.suffix.lower()
        
        with open(self.config_path, 'r') as f:
            if suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif suffix == '.toml':
                data = toml.load(f)
            elif suffix == '.json':
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {suffix}")
        
        # Convert datetime strings back to datetime objects
        data = self._deserialize_datetimes(data)
        
        self.config = AppConfig(**data)
        return self.config
    
    def save(self, config: Optional[AppConfig] = None) -> None:
        """
        Save configuration to file.
        
        Args:
            config: AppConfig object to save. If None, uses current config.
        """
        if config is None:
            config = self.config
        
        if config is None:
            raise ValueError("No configuration to save")
        
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict and serialize
        data = config.model_dump(mode='python')
        data = self._serialize_for_storage(data)
        
        # Determine format from extension
        suffix = self.config_path.suffix.lower()
        
        with open(self.config_path, 'w') as f:
            if suffix in ['.yaml', '.yml']:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            elif suffix == '.toml':
                toml.dump(data, f)
            elif suffix == '.json':
                json.dump(data, f, indent=2)
            else:
                raise ValueError(f"Unsupported config format: {suffix}")
        
        self.config = config
    
    def create_default(self, cube_name: str = "my_cube") -> AppConfig:
        """
        Create a default configuration.
        
        Args:
            cube_name: Name for the default cube
            
        Returns:
            AppConfig object with default settings
        """
        data_dir = Path("data")
        
        # Create default cube
        default_cube = CubeConfig(
            name=cube_name,
            description=f"Default cube configuration",
            database_path=data_dir / "databases" / f"{cube_name}.pkl",
            image_sets=[],
            owners=[],
            total_cards=0
        )
        
        config = AppConfig(
            active_cube=cube_name,
            cubes={cube_name: default_cube},
            users={},
            image_sets={},
            data_directory=data_dir
        )
        
        self.config = config
        return config
    
    def _serialize_for_storage(self, data: dict) -> dict:
        """
        Recursively convert Path and datetime objects to strings for storage.
        
        Args:
            data: Dictionary to serialize
            
        Returns:
            Serialized dictionary
        """
        if isinstance(data, dict):
            return {k: self._serialize_for_storage(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._serialize_for_storage(item) for item in data]
        elif isinstance(data, Path):
            return str(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            return data
    
    def _deserialize_datetimes(self, data: dict) -> dict:
        """
        Recursively convert ISO datetime strings back to datetime objects.
        
        Args:
            data: Dictionary to deserialize
            
        Returns:
            Deserialized dictionary
        """
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                # Known datetime fields
                if k in ['created_at', 'last_updated', 'registered_at']:
                    if isinstance(v, str):
                        try:
                            result[k] = datetime.fromisoformat(v)
                        except (ValueError, TypeError):
                            result[k] = v
                    else:
                        result[k] = v
                else:
                    result[k] = self._deserialize_datetimes(v)
            return result
        elif isinstance(data, list):
            return [self._deserialize_datetimes(item) for item in data]
        else:
            return data
    
    @classmethod
    def initialize_project(cls, project_dir: Path, cube_name: str = "my_cube") -> 'ConfigManager':
        """
        Initialize a new project with default configuration and directory structure.
        
        Args:
            project_dir: Root directory for the project
            cube_name: Name for the default cube
            
        Returns:
            ConfigManager instance with default configuration
        """
        project_dir = Path(project_dir)
        
        # Create directory structure
        (project_dir / "config").mkdir(parents=True, exist_ok=True)
        (project_dir / "data" / "cubes").mkdir(parents=True, exist_ok=True)
        (project_dir / "data" / "images").mkdir(parents=True, exist_ok=True)
        (project_dir / "data" / "databases").mkdir(parents=True, exist_ok=True)
        
        # Create config manager with path relative to project dir
        config_path = project_dir / "config" / cls.DEFAULT_CONFIG_NAME
        manager = cls(config_path)
        
        # Create and save default configuration
        config = manager.create_default(cube_name)
        manager.save(config)
        
        return manager
    
    def add_cube(self, name: str, description: Optional[str] = None) -> CubeConfig:
        """
        Add a new cube to the configuration.
        
        Args:
            name: Name of the new cube
            description: Optional description
            
        Returns:
            The created CubeConfig
        """
        if self.config is None:
            raise ValueError("No configuration loaded")
        
        database_path = self.config.data_directory / "databases" / f"{name}.pkl"
        
        cube = CubeConfig(
            name=name,
            description=description or f"Cube: {name}",
            database_path=database_path,
            image_sets=[],
            owners=[]
        )
        
        self.config.add_cube(cube)
        return cube
    
    def add_user(self, name: str, email: Optional[str] = None) -> UserConfig:
        """
        Add a new user to the configuration.
        
        Args:
            name: User's name
            email: User's email address
            
        Returns:
            The created UserConfig
        """
        if self.config is None:
            raise ValueError("No configuration loaded")
        
        user = UserConfig(
            name=name,
            email=email,
            image_sets=[],
            total_cards=0
        )
        
        self.config.add_user(user)
        return user
    
    def add_image_set(
        self,
        name: str,
        directory: Union[str, Path],
        owner: str
    ) -> ImageSetConfig:
        """
        Add a new image set to the configuration.
        
        Args:
            name: Name of the image set
            directory: Directory containing images
            owner: Owner's name
            
        Returns:
            The created ImageSetConfig
        """
        if self.config is None:
            raise ValueError("No configuration loaded")
        
        image_set = ImageSetConfig(
            name=name,
            directory=Path(directory),
            owner=owner
        )
        
        self.config.add_image_set(image_set)
        return image_set