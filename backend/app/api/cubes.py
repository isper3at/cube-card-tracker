"""Cubes REST API."""
from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Cube, Card, CubeStatus

bp = Blueprint('cubes', __name__)


@bp.get('/')
def list_cubes():
    tournament_id = request.args.get('tournament_id', type=int)
    q = Cube.query
    if tournament_id:
        q = q.filter_by(tournament_id=tournament_id)
    cubes = q.order_by(Cube.created_at.desc()).all()
    return jsonify([c.to_dict() for c in cubes])


@bp.get('/<int:cube_id>')
def get_cube(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    return jsonify(cube.to_dict(include_relations=True))


@bp.get('/<int:cube_id>/cards')
def get_cube_cards(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    cards = Card.query.filter_by(cube_id=cube.id).order_by(Card.bbox_y, Card.bbox_x).all()
    return jsonify([c.to_dict() for c in cards])


@bp.delete('/<int:cube_id>')
def delete_cube(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    db.session.delete(cube)
    db.session.commit()
    return '', 204

