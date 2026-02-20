"""Tournaments REST API."""
from datetime import date
from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Tournament, TournamentStatus

bp = Blueprint('tournaments', __name__)


@bp.get('/')
def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
    return jsonify([t.to_dict() for t in tournaments])


@bp.post('/')
def create_tournament():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    date_str = data.get('date')

    if not name or not date_str:
        return jsonify({'error': 'name and date are required'}), 400

    try:
        tournament_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'date must be ISO format (YYYY-MM-DD)'}), 400

    tournament = Tournament(
        name=name,
        date=tournament_date,
        location=data.get('location', ''),
        notes=data.get('notes', ''),
        status=TournamentStatus.DRAFT,
    )
    db.session.add(tournament)
    db.session.commit()
    return jsonify(tournament.to_dict()), 201


@bp.get('/<int:tournament_id>')
def get_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    return jsonify(t.to_dict(include_relations=True))


@bp.patch('/<int:tournament_id>')
def update_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        t.name = data['name']
    if 'location' in data:
        t.location = data['location']
    if 'notes' in data:
        t.notes = data['notes']
    if 'status' in data:
        t.status = TournamentStatus(data['status'])

    db.session.commit()
    return jsonify(t.to_dict())


@bp.delete('/<int:tournament_id>')
def delete_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    db.session.delete(t)
    db.session.commit()
    return '', 204

