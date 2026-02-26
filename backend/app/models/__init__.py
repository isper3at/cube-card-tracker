"""
Core domain models for the cube card tracking system.
"""
from enum import Enum
from datetime import datetime
from ..extensions import db


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseModel(db.Model):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


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
    DETECTED = 'detected'
    CONFIRMED = 'confirmed'
    DRAFTED = 'drafted'
    RETURNED = 'returned'
    REMOVED = 'removed'


# ── Models ────────────────────────────────────────────────────────────────────

class Tournament(BaseModel):
    __tablename__ = 'tournaments'

    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    status = db.Column(db.Enum(TournamentStatus), nullable=False, default=TournamentStatus.DRAFT)
    notes = db.Column(db.Text)

    cubes = db.relationship('Cube', back_populates='tournament', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='tournament', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'name': self.name,
            'date': self.date.isoformat() if self.date else None,
            'location': self.location,
            'status': self.status.value,
            'notes': self.notes,
        })
        if include_relations:
            data['cubes'] = [c.to_dict() for c in self.cubes]
            data['tables'] = [t.to_dict() for t in self.tables]
        return data


class Cube(BaseModel):
    __tablename__ = 'cubes'

    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    owner_name = db.Column(db.String(200), nullable=False)
    owner_email = db.Column(db.String(200))
    cube_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Enum(CubeStatus), nullable=False, default=CubeStatus.PENDING_CHECKIN)

    source_image_path = db.Column(db.String(500))
    annotated_image_path = db.Column(db.String(500))
    session_id = db.Column(db.String(100), unique=True)

    total_cards = db.Column(db.Integer, default=0)
    cards_confirmed = db.Column(db.Integer, default=0)

    tournament = db.relationship('Tournament', back_populates='cubes')
    cards = db.relationship('Card', back_populates='cube', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='cube')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'tournament_id': self.tournament_id,
            'owner_name': self.owner_name,
            'owner_email': self.owner_email,
            'cube_name': self.cube_name,
            'status': self.status.value,
            'session_id': self.session_id,
            'total_cards': self.total_cards,
            'cards_confirmed': self.cards_confirmed,
            'annotated_image_path': self.annotated_image_path,
        })
        if include_relations:
            data['cards'] = [c.to_dict() for c in self.cards]
        return data


class Card(BaseModel):
    __tablename__ = 'cards'

    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'), nullable=False)

    raw_ocr_text = db.Column(db.String(200))
    recognized_name = db.Column(db.String(200))
    confirmed_name = db.Column(db.String(200))
    match_score = db.Column(db.Float)
    status = db.Column(db.Enum(CardStatus), nullable=False, default=CardStatus.DETECTED)

    bbox_x = db.Column(db.Integer)
    bbox_y = db.Column(db.Integer)
    bbox_width = db.Column(db.Integer)
    bbox_height = db.Column(db.Integer)
    polygon_json = db.Column(db.JSON)

    thumbnail_base64 = db.Column(db.Text)

    cube = db.relationship('Cube', back_populates='cards')
    assignments = db.relationship('CardAssignment', back_populates='card', cascade='all, delete-orphan')

    @property
    def display_name(self):
        return self.confirmed_name or self.recognized_name or self.raw_ocr_text or 'Unknown Card'

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'cube_id': self.cube_id,
            'raw_ocr_text': self.raw_ocr_text,
            'recognized_name': self.recognized_name,
            'confirmed_name': self.confirmed_name,
            'match_score': self.match_score,
            'status': self.status.value,
            'display_name': self.display_name,
            'bbox_x': self.bbox_x,
            'bbox_y': self.bbox_y,
            'bbox_width': self.bbox_width,
            'bbox_height': self.bbox_height,
            'polygon_json': self.polygon_json,
            'thumbnail_base64': self.thumbnail_base64,
        })
        if include_relations:
            data['assignments'] = [a.to_dict() for a in self.assignments]
        return data


class Table(BaseModel):
    __tablename__ = 'tables'

    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'))
    table_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(TableStatus), nullable=False, default=TableStatus.WAITING)

    tournament = db.relationship('Tournament', back_populates='tables')
    cube = db.relationship('Cube', back_populates='tables')
    players = db.relationship('Player', back_populates='table', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'tournament_id': self.tournament_id,
            'cube_id': self.cube_id,
            'table_number': self.table_number,
            'status': self.status.value,
        })
        if include_relations:
            data['players'] = [p.to_dict() for p in self.players]
        return data


class Player(BaseModel):
    __tablename__ = 'players'

    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)

    draft_submitted = db.Column(db.Boolean, default=False)
    cards_returned = db.Column(db.Boolean, default=False)

    table = db.relationship('Table', back_populates='players')
    assignments = db.relationship('CardAssignment', back_populates='player', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'table_id': self.table_id,
            'name': self.name,
            'seat_number': self.seat_number,
            'draft_submitted': self.draft_submitted,
            'cards_returned': self.cards_returned,
        })
        return data


class CardAssignment(BaseModel):
    __tablename__ = 'card_assignments'

    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)

    assigned_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)

    card = db.relationship('Card', back_populates='assignments')
    player = db.relationship('Player', back_populates='assignments')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'card_id': self.card_id,
            'player_id': self.player_id,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'returned_at': self.returned_at.isoformat() if self.returned_at else None,
        })
        if include_relations:
            data['card'] = self.card.to_dict()
            data['player'] = self.player.to_dict()
        return data

