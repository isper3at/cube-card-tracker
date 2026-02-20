"""
Card database service.
Loads card names from JSON/text files and provides fuzzy matching.
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not available — fuzzy matching disabled")


class CardDatabaseService:
    """Manages the list of known card names and fuzzy-matches OCR output."""

    def __init__(self, card_db_folder: str):
        self.card_db_folder = Path(card_db_folder)
        self._card_names: List[str] = []
        self._loaded = False

    def ensure_loaded(self):
        """Load card names if not already loaded."""
        if not self._loaded:
            self._load()
            self._loaded = True

    def _load(self):
        """
        Load card names from the card DB folder.

        Supports:
          - oracle-cards.json  (Scryfall bulk data — list of objects with "name")
          - cards.json         (simple list of strings or objects)
          - cards.txt          (one name per line)
        """
        names = set()

        for path in self.card_db_folder.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            names.add(item.strip())
                        elif isinstance(item, dict) and 'name' in item:
                            # Handle split/transform cards — keep front face only
                            name = item['name'].split(' // ')[0].strip()
                            names.add(name)
                elif isinstance(data, dict) and 'data' in data:
                    for item in data['data']:
                        if isinstance(item, dict) and 'name' in item:
                            names.add(item['name'].split(' // ')[0].strip())
                logger.info(f"Loaded names from {path.name}")
            except Exception as exc:
                logger.warning(f"Failed to load {path}: {exc}")

        for path in self.card_db_folder.glob('*.txt'):
            try:
                for line in path.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        names.add(line)
            except Exception as exc:
                logger.warning(f"Failed to load {path}: {exc}")

        self._card_names = sorted(names)
        logger.info(f"Card database loaded: {len(self._card_names)} unique names")

    @property
    def card_names(self) -> List[str]:
        self.ensure_loaded()
        return self._card_names

    def fuzzy_match(
        self,
        query: str,
        threshold: int = 70
    ) -> Optional[Tuple[str, float]]:
        """
        Find the best matching card name for an OCR string.

        Returns (name, score) or None if no match above threshold.
        """
        if not query or not self._card_names:
            return None

        if not RAPIDFUZZ_AVAILABLE:
            return None

        result = process.extractOne(
            query,
            self._card_names,
            scorer=fuzz.WRatio,
            score_cutoff=threshold,
        )
        if result is None:
            return None

        name, score, _ = result
        return name, round(score / 100, 3)

    def search(self, query: str, limit: int = 10) -> List[str]:
        """Return top matching card names for autocomplete."""
        if not query or not RAPIDFUZZ_AVAILABLE:
            return []
        results = process.extract(
            query, self._card_names, scorer=fuzz.WRatio, limit=limit
        )
        return [r[0] for r in results]

