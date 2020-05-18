import calendar
import time
import datetime

from flask import abort, Blueprint, json, render_template, request, redirect, flash, jsonify
from flask_cors import cross_origin
from flask_jwt_extended import (create_access_token, decode_token, jwt_required)

from config.constants import ALLOWED_SELFIE_EXTENSIONS, DEVICE_IDENTIFIERS_HEADER
from config.settings import (FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET,
                             FITBIT_REDIRECT_URL)

from database.user_models import Participant

import libs.fitbit as fitbit


fitbit_web_form = Blueprint('fitbit_web_form', __name__)


def return_response(should_redirect=True, message='', error=0):
    if should_redirect:
        if message:
            flash(message, 'danger' if error > 0 else 'info')
        return render_template('fitbit.html')
    else:
        return jsonify({'msg': message}), error if error > 0 else 200


@fitbit_web_form.route('/', methods=['GET', 'POST', 'OPTIONS'])
def fitbit_form():

    if request.method == 'GET':
            
        code = request.args.get('code', '')
        state = request.args.get('state', '')

        if code:
            try:
                fitbit.authorize(code, state)

            except Exception as e:
                message = 'There was an error. Please, try again later.'
                if str(e) == 'INVALID_USER':
                    message = 'Invalid application state. Please, try again later.'
                flash(message, 'danger')

            else:
                flash('Fitbit Authorization complete!', 'info')

        return render_template('fitbit.html')

    try:

        patient_id = request.values.get('username').lower()
        password = request.values.get('password')
        if not patient_id or not password:
            raise

        user = Participant.objects.get(patient_id=patient_id)
        if not user.debug_validate_password(password):
            raise

    except:
        message = 'Username or password incorrect'
        flash(message, 'danger')
        return render_template('fitbit.html')

    url = fitbit.redirect(patient_id)
    return redirect(url)
