"""
Configuration classes for different environments.
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / 'data'


class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f'sqlite:///{BASE_DIR / "cube_tracker.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # File storage
    UPLOAD_FOLDER = str(DATA_DIR / 'uploads')
    ANNOTATED_FOLDER = str(DATA_DIR / 'annotated')
    CARD_DB_FOLDER = str(DATA_DIR / 'cards')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # OCR
    TESSERACT_CMD = os.getenv('TESSERACT_CMD', 'tesseract')
    
    # Card detection
    MIN_CARD_AREA = 5000
    MAX_CARD_AREA = 300000
    FUZZY_MATCH_THRESHOLD = 70
    
    # CORS
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')


class DevelopmentConfig(Config):
    """Development configuration."""
    
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration."""
    
    DEBUG = False
    
    # Override with production database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://user:pass@localhost/cube_tracker'
    )


class TestingConfig(Config):
    """Testing configuration."""
    
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}