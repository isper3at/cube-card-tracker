"""
Card recognition engine using ORB feature detection and matching.

This module handles the core image recognition functionality.
"""

import cv2
import numpy as np
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from .config import RecognitionConfig


@dataclass
class CardRecord:
    """Stores information about a registered card."""
    
    card_name: str
    owner: str
    descriptors: np.ndarray
    image_path: str
    num_features: int = 0


class CardRecognitionEngine:
    """
    Core recognition engine for identifying cards using ORB features.
    
    This class handles:
    - Feature detection and descriptor computation
    - Card registration and database management
    - Card recognition with rotation invariance
    """
    
    def __init__(
        self,
        database_path: Path,
        config: Optional[RecognitionConfig] = None
    ):
        """
        Initialize the recognition engine.
        
        Args:
            database_path: Path to save/load the card database
            config: Recognition configuration. Uses defaults if None.
        """
        self.database_path = Path(database_path)
        self.config = config or RecognitionConfig()
        self.card_database: Dict[str, CardRecord] = {}
        
        # Initialize ORB detector
        self.orb = cv2.ORB_create(nfeatures=self.config.orb_features)
        
        # Initialize matcher
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        
        # Load existing database if it exists
        self.load_database()
    
    def load_database(self) -> bool:
        """
        Load card database from disk.
        
        Returns:
            True if database was loaded, False if no database exists
        """
        if not self.database_path.exists():
            return False
        
        try:
            with open(self.database_path, 'rb') as f:
                self.card_database = pickle.load(f)
            return True
        except Exception as e:
            print(f"Warning: Could not load database: {e}")
            return False
    
    def save_database(self) -> None:
        """Save card database to disk."""
        # Ensure directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.database_path, 'wb') as f:
            pickle.dump(self.card_database, f)
    
    def register_card(
        self,
        image_path: Path,
        card_name: str,
        owner: str
    ) -> CardRecord:
        """
        Register a new card with the system.
        
        Args:
            image_path: Path to the card image (should be upright)
            card_name: Name/identifier for the card
            owner: Name of the card owner
            
        Returns:
            The created CardRecord
            
        Raises:
            ValueError: If image cannot be read or no features detected
        """
        # Read and preprocess image
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect keypoints and compute descriptors
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        
        if descriptors is None:
            raise ValueError(f"No features detected in {image_path}")
        
        # Create card record
        card_record = CardRecord(
            card_name=card_name,
            owner=owner,
            descriptors=descriptors,
            image_path=str(image_path),
            num_features=len(keypoints)
        )
        
        # Store in database
        self.card_database[card_name] = card_record
        
        return card_record
    
    def register_batch(
        self,
        cards_info: List[Tuple[Path, str, str]]
    ) -> Dict[str, CardRecord]:
        """
        Register multiple cards at once.
        
        Args:
            cards_info: List of (image_path, card_name, owner) tuples
            
        Returns:
            Dictionary of successfully registered cards
        """
        registered = {}
        
        for image_path, card_name, owner in cards_info:
            try:
                record = self.register_card(image_path, card_name, owner)
                registered[card_name] = record
            except Exception as e:
                print(f"Error registering {card_name}: {e}")
        
        # Save database after batch registration
        if registered:
            self.save_database()
        
        return registered
    
    def recognize_card(
        self,
        image_path: Path,
        min_matches: Optional[int] = None
    ) -> Optional[Tuple[str, str, int]]:
        """
        Recognize a card from an image (can be any orientation).
        
        Args:
            image_path: Path to the card image to recognize
            min_matches: Minimum number of good matches required.
                        Uses config default if None.
            
        Returns:
            Tuple of (card_name, owner, num_matches) or None if not recognized
            
        Raises:
            ValueError: If image cannot be read
        """
        if min_matches is None:
            min_matches = self.config.min_matches
        
        # Read and preprocess query image
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Detect features in query image
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        
        if descriptors is None:
            return None
        
        best_match = None
        best_match_count = 0
        
        # Compare against all registered cards
        for card_name, card_record in self.card_database.items():
            # Match descriptors
            matches = self.matcher.knnMatch(
                descriptors,
                card_record.descriptors,
                k=2
            )
            
            # Apply Lowe's ratio test
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < self.config.ratio_test_threshold * n.distance:
                        good_matches.append(m)
            
            # Check if this is the best match so far
            if len(good_matches) > best_match_count:
                best_match_count = len(good_matches)
                best_match = (card_name, card_record.owner, len(good_matches))
        
        # Return best match if it meets minimum threshold
        if best_match and best_match_count >= min_matches:
            return best_match
        
        return None
    
    def create_match_visualization(
        self,
        query_path: Path,
        matched_card_name: str,
        output_path: Path,
        max_matches_shown: int = 50
    ) -> None:
        """
        Create a visualization showing feature matches.
        
        Args:
            query_path: Path to the query image
            matched_card_name: Name of the matched card
            output_path: Where to save the visualization
            max_matches_shown: Maximum number of matches to draw
        """
        query_img = cv2.imread(str(query_path))
        card_record = self.card_database[matched_card_name]
        ref_img = cv2.imread(card_record.image_path)
        
        # Detect features
        query_gray = cv2.cvtColor(query_img, cv2.COLOR_BGR2GRAY)
        ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
        
        query_kp, query_desc = self.orb.detectAndCompute(query_gray, None)
        ref_kp, ref_desc = self.orb.detectAndCompute(ref_gray, None)
        
        # Match features
        matches = self.matcher.knnMatch(query_desc, ref_desc, k=2)
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < self.config.ratio_test_threshold * n.distance:
                    good_matches.append(m)
        
        # Draw matches
        result_img = cv2.drawMatches(
            query_img, query_kp,
            ref_img, ref_kp,
            good_matches[:max_matches_shown],
            None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
        )
        
        # Add text annotations
        cv2.putText(
            result_img,
            f"Matched: {matched_card_name}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )
        cv2.putText(
            result_img,
            f"Owner: {card_record.owner}",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )
        cv2.putText(
            result_img,
            f"{len(good_matches)} matches",
            (10, 110),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )
        
        # Save visualization
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), result_img)
    
    def get_database_stats(self) -> Dict[str, any]:
        """
        Get statistics about the current database.
        
        Returns:
            Dictionary with database statistics
        """
        if not self.card_database:
            return {
                'total_cards': 0,
                'owners': [],
                'cards_by_owner': {}
            }
        
        owners = {}
        for card_name, record in self.card_database.items():
            if record.owner not in owners:
                owners[record.owner] = []
            owners[record.owner].append(card_name)
        
        return {
            'total_cards': len(self.card_database),
            'owners': list(owners.keys()),
            'cards_by_owner': owners,
            'average_features': np.mean([
                r.num_features for r in self.card_database.values()
            ])
        }