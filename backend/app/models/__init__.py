"""
Core domain models for the cube card tracking system.

Models:
  - Tournament: Top-level event container
  - Cube: A collection of cards owned by someone
  - Card: Individual card detected in a cube
  - Player: Player at a table
  - Table: Draft table in a tournament
  - CardAssignment: Tracks which player has which card
"""
from enum import Enum
from .base import db, BaseModel


# ── Enums ─────────────────────────────────────────────────────────────────────

class TournamentStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    COMPLETE = 'complete'
    CANCELLED = 'cancelled'


class CubeStatus(str, Enum):
    PENDING_CHECKIN = 'pending_checkin'
    CHECKED_IN = 'checked_in'
    IN_USE = 'in_use'
    RETURNED = 'returned'
    FLAGGED = 'flagged'


class TableStatus(str, Enum):
    WAITING = 'waiting'
    DRAFTING = 'drafting'
    PLAYING = 'playing'
    COMPLETE = 'complete'


class CardStatus(str, Enum):
    DETECTED = 'detected'      # OCR detected, not confirmed
    CONFIRMED = 'confirmed'    # Admin confirmed the name
    DRAFTED = 'drafted'        # Assigned to a player
    RETURNED = 'returned'      # Player returned it


# ── Models ────────────────────────────────────────────────────────────────────

class Tournament(BaseModel):
    """Top-level tournament/event."""
    
    __tablename__ = 'tournaments'
    
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    status = db.Column(db.Enum(TournamentStatus), nullable=False, default=TournamentStatus.DRAFT)
    notes = db.Column(db.Text)
    
    # Relationships
    cubes = db.relationship('Cube', back_populates='tournament', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='tournament', cascade='all, delete-orphan')
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        if include_relations:
            data['cubes'] = [c.to_dict() for c in self.cubes]
            data['tables'] = [t.to_dict() for t in self.tables]
        return data


class Cube(BaseModel):
    """A cube checked in to the tournament."""
    
    __tablename__ = 'cubes'
    
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    owner_name = db.Column(db.String(200), nullable=False)
    owner_email = db.Column(db.String(200))
    cube_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Enum(CubeStatus), nullable=False, default=CubeStatus.PENDING_CHECKIN)
    
    # Check-in data
    source_image_path = db.Column(db.String(500))
    annotated_image_path = db.Column(db.String(500))
    session_id = db.Column(db.String(100), unique=True)  # For in-progress check-ins
    
    # Metadata
    total_cards = db.Column(db.Integer, default=0)
    cards_confirmed = db.Column(db.Integer, default=0)
    
    # Relationships
    tournament = db.relationship('Tournament', back_populates='cubes')
    cards = db.relationship('Card', back_populates='cube', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='cube')
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data['status'] = self.status.value
        if include_relations:
            data['cards'] = [c.to_dict() for c in self.cards]
        return data


class Card(BaseModel):
    """Individual card in a cube."""
    
    __tablename__ = 'cards'
    
    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'), nullable=False)
    
    # Detection data
    raw_ocr_text = db.Column(db.String(200))       # Raw Tesseract output
    recognized_name = db.Column(db.String(200))    # Fuzzy-matched name
    confirmed_name = db.Column(db.String(200))     # Admin-confirmed name
    match_score = db.Column(db.Float)              # Fuzzy match confidence
    status = db.Column(db.Enum(CardStatus), nullable=False, default=CardStatus.DETECTED)
    
    # Position in source image
    bbox_x = db.Column(db.Integer)
    bbox_y = db.Column(db.Integer)
    bbox_width = db.Column(db.Integer)
    bbox_height = db.Column(db.Integer)
    polygon_json = db.Column(db.JSON)              # [[x,y], [x,y], [x,y], [x,y]]
    
    # Image data
    thumbnail_base64 = db.Column(db.Text)
    
    # Relationships
    cube = db.relationship('Cube', back_populates='cards')
    assignments = db.relationship('CardAssignment', back_populates='card', cascade='all, delete-orphan')
    
    @property
    def display_name(self):
        """Get the best available name."""
        return self.confirmed_name or self.recognized_name or self.raw_ocr_text or 'Unknown Card'
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data['status'] = self.status.value
        data['display_name'] = self.display_name
        if include_relations:
            data['assignments'] = [a.to_dict() for a in self.assignments]
        return data


class Table(BaseModel):
    """A draft table in a tournament."""
    
    __tablename__ = 'tables'
    
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'))
    table_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(TableStatus), nullable=False, default=TableStatus.WAITING)
    
    # Relationships
    tournament = db.relationship('Tournament', back_populates='tables')
    cube = db.relationship('Cube', back_populates='tables')
    players = db.relationship('Player', back_populates='table', cascade='all, delete-orphan')
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data['status'] = self.status.value
        if include_relations:
            data['players'] = [p.to_dict() for p in self.players]
        return data


class Player(BaseModel):
    """A player at a table."""
    
    __tablename__ = 'players'
    
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)
    
    # Draft tracking
    draft_submitted = db.Column(db.Boolean, default=False)
    cards_returned = db.Column(db.Boolean, default=False)
    
    # Relationships
    table = db.relationship('Table', back_populates='players')
    assignments = db.relationship('CardAssignment', back_populates='player', cascade='all, delete-orphan')
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        if include_relations:
            data['assignments'] = [a.to_dict() for a in self.assignments]
        return data


class CardAssignment(BaseModel):
    """Tracks which player has which card."""
    
    __tablename__ = 'card_assignments'
    
    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    
    # Assignment metadata
    assigned_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)
    
    # Relationships
    card = db.relationship('Card', back_populates='assignments')
    player = db.relationship('Player', back_populates='assignments')
    
    def to_dict(self, include_relations=False):
        data = super().to_dict()
        if include_relations:
            data['card'] = self.card.to_dict()
            data['player'] = self.player.to_dict()
        return data