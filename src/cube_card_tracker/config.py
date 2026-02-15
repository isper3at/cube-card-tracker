"""
Configuration models for the Cube Card Tracker system.

This module defines the configuration structure using Pydantic for validation.
"""

from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class ImageSetConfig(BaseModel):
    """Configuration for a set of reference images."""
    
    name: str = Field(..., description="Name of this image set")
    directory: Path = Field(..., description="Directory containing reference images")
    owner: str = Field(..., description="Owner of these cards")
    registered_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        description="When this image set was registered"
    )
    num_cards: Optional[int] = Field(None, description="Number of cards in this set")
    
    @field_validator('directory')
    @classmethod
    def validate_directory(cls, v: Path) -> Path:
        """Ensure directory path is a Path object."""
        return Path(v) if not isinstance(v, Path) else v


class UserConfig(BaseModel):
    """Configuration for a user/player."""
    
    name: str = Field(..., description="User's name")
    email: Optional[str] = Field(None, description="User's email")
    image_sets: List[str] = Field(
        default_factory=list,
        description="Names of image sets owned by this user"
    )
    total_cards: int = Field(0, description="Total number of cards registered")


class RecognitionConfig(BaseModel):
    """Configuration for the recognition algorithm."""
    
    min_matches: int = Field(
        20,
        ge=5,
        le=100,
        description="Minimum number of feature matches required for positive identification"
    )
    orb_features: int = Field(
        2000,
        ge=500,
        le=10000,
        description="Number of ORB features to detect per image"
    )
    ratio_test_threshold: float = Field(
        0.75,
        ge=0.5,
        le=0.95,
        description="Lowe's ratio test threshold for filtering matches"
    )


class CubeConfig(BaseModel):
    """Configuration for a specific cube."""
    
    name: str = Field(..., description="Name of the cube")
    description: Optional[str] = Field(None, description="Description of the cube")
    database_path: Path = Field(..., description="Path to the card database file")
    image_sets: List[str] = Field(
        default_factory=list,
        description="Image sets included in this cube"
    )
    owners: List[str] = Field(
        default_factory=list,
        description="Users who have cards in this cube"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When this cube was created"
    )
    last_updated: Optional[datetime] = Field(None, description="Last update time")
    total_cards: int = Field(0, description="Total number of cards in the cube")
    
    @field_validator('database_path')
    @classmethod
    def validate_database_path(cls, v: Path) -> Path:
        """Ensure database_path is a Path object."""
        return Path(v) if not isinstance(v, Path) else v


class AppConfig(BaseModel):
    """Main application configuration."""
    
    active_cube: str = Field(..., description="Name of the currently active cube")
    cubes: dict[str, CubeConfig] = Field(
        default_factory=dict,
        description="Dictionary of all configured cubes"
    )
    users: dict[str, UserConfig] = Field(
        default_factory=dict,
        description="Dictionary of all registered users"
    )
    image_sets: dict[str, ImageSetConfig] = Field(
        default_factory=dict,
        description="Dictionary of all registered image sets"
    )
    recognition: RecognitionConfig = Field(
        default_factory=RecognitionConfig,
        description="Recognition algorithm configuration"
    )
    data_directory: Path = Field(
        Path("data"),
        description="Base directory for all data files"
    )
    
    @field_validator('data_directory')
    @classmethod
    def validate_data_directory(cls, v: Path) -> Path:
        """Ensure data_directory is a Path object."""
        return Path(v) if not isinstance(v, Path) else v
    
    def get_active_cube(self) -> Optional[CubeConfig]:
        """Get the currently active cube configuration."""
        return self.cubes.get(self.active_cube)
    
    def add_cube(self, cube: CubeConfig) -> None:
        """Add a new cube to the configuration."""
        self.cubes[cube.name] = cube
        if not self.active_cube:
            self.active_cube = cube.name
    
    def add_user(self, user: UserConfig) -> None:
        """Add a new user to the configuration."""
        self.users[user.name] = user
    
    def add_image_set(self, image_set: ImageSetConfig) -> None:
        """Add a new image set to the configuration."""
        self.image_sets[image_set.name] = image_set
        
        # Update user's image sets
        if image_set.owner in self.users:
            if image_set.name not in self.users[image_set.owner].image_sets:
                self.users[image_set.owner].image_sets.append(image_set.name)
    
    def get_user_cards(self, username: str) -> List[str]:
        """Get all image sets for a specific user."""
        user = self.users.get(username)
        if not user:
            return []
        return user.image_sets
    
    def get_cube_users(self, cube_name: str) -> List[str]:
        """Get all users who have cards in a specific cube."""
        cube = self.cubes.get(cube_name)
        if not cube:
            return []
        return cube.owners