"""
Cube Card Tracker - Card recognition system for cube tournaments.

A rotation-invariant card recognition system for tracking cube cards
and returning them to their owners after tournaments.
"""

__version__ = "0.1.0"

from .tracker import CubeCardTracker
from .config import (
    AppConfig,
    CubeConfig,
    UserConfig,
    ImageSetConfig,
    RecognitionConfig
)
from .config_manager import ConfigManager
from .recognition import CardRecognitionEngine, CardRecord

__all__ = [
    'CubeCardTracker',
    'AppConfig',
    'CubeConfig',
    'UserConfig',
    'ImageSetConfig',
    'RecognitionConfig',
    'ConfigManager',
    'CardRecognitionEngine',
    'CardRecord',
]