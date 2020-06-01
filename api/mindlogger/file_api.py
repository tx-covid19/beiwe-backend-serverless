from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    jwt_required
)

file_api = Blueprint('file_api', __name__)


@file_api.route('', methods=['POST'])
@jwt_required
def upload_file():
    return jsonify({}), 200
