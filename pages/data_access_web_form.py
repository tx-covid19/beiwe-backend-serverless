import json

from flask import Blueprint, flash, Markup, render_template, session, redirect, abort, request

from config.constants import ALL_DATA_STREAMS
from database.data_access_models import PipelineUploadTags
from database.user_models import Participant, Researcher
from database.system_integrations import BoxIntegration
from libs.admin_authentication import (authenticate_researcher_login,
    get_researcher_allowed_studies, get_researcher_allowed_studies_as_query_set,
    researcher_is_an_admin, SESSION_NAME)
from libs.box import get_registration_url, box_authenticate, BoxOAuthException

data_access_web_form = Blueprint('data_access_web_form', __name__)


@data_access_web_form.route("/data_access_web_form", methods=['GET'])
@authenticate_researcher_login
def data_api_web_form_page():
    researcher = Researcher.objects.get(username=session[SESSION_NAME])
    warn_researcher_if_hasnt_yet_generated_access_key(researcher)
    allowed_studies = get_researcher_allowed_studies_as_query_set()
    # dict of {study ids : list of user ids}
    users_by_study = {
        study.pk: [user.patient_id for user in study.participants.all()]
        for study in allowed_studies
    }
    return render_template(
        "data_api_web_form.html",
        allowed_studies=get_researcher_allowed_studies(),
        users_by_study=json.dumps(users_by_study),
        ALL_DATA_STREAMS=ALL_DATA_STREAMS,
        is_admin=researcher_is_an_admin()
    )


def warn_researcher_if_hasnt_yet_generated_access_key(researcher):
    if not researcher.access_key_id:
        msg = """You need to generate an <b>Access Key</b> and a <b>Secret Key </b> before you
        can download data. Go to <a href='/manage_credentials'> Manage Credentials</a> and click
        'Reset Data-Download API Access Credentials'. """
        flash(Markup(msg), 'danger')


@data_access_web_form.route("/pipeline_access_web_form", methods=['GET'])
@authenticate_researcher_login
def pipeline_download_page():
    researcher = Researcher.objects.get(username=session[SESSION_NAME])
    warn_researcher_if_hasnt_yet_generated_access_key(researcher)
    iteratable_studies = get_researcher_allowed_studies(as_json=False)
    # dict of {study ids : list of user ids}

    users_by_study = {str(study['id']):
                      [user.id for user in Participant.objects.filter(study__id=study['id'])]
                      for study in iteratable_studies}

    # it is a bit obnoxious to get this data, we need to deduplcate it and then turn it back into a list

    tags_by_study = {
        study['id']: list(set([tag for tag in PipelineUploadTags.objects.filter(
            pipeline_upload__study__id=study['id']
        ).values_list("tag", flat=True)]))
        for study in iteratable_studies
    }

    return render_template(
            "data_pipeline_web_form.html",
            allowed_studies=get_researcher_allowed_studies(),
            downloadable_studies=get_researcher_allowed_studies(),
            users_by_study=users_by_study,
            tags_by_study=json.dumps(tags_by_study),
            is_admin=researcher_is_an_admin()
    )

#@data_access_web_form.route("/box_redirect/<string:username>", methods=['GET'])
#def get_box_credentials(username):
@data_access_web_form.route("/box_redirect", methods=['GET', 'POST'])
def get_box_credentials():

    username = session[SESSION_NAME]
    print(f"get box credentials {username}")
    try:
        researcher = Researcher.objects.get(username=username)
    except:
        print(f"get_box_credentials: Researcher {username} does not exist.")
        return abort(404)

    if request and 'code' in request.args:
        code = request.args['code']
        box_integration = BoxIntegration(researcher=researcher)

        try:
            box_authenticate(request.args['code'], box_integration)
        except BoxOAuthException:
            box_integration.delete()
            print(f"authentication failed")
            msg = """<b>box.com Authentication failed!</b> This may happen when
            the system doesn't complete the authentication process quickly enough. 
            Pleae wait a few minutes and try again"""
            flash(Markup(msg), 'danger')
    else:
        print(f"url isn't formatted correctly, missing code")
        return abort(404)

    return redirect("/copy_data_to_box_form")

@data_access_web_form.route("/copy_data_to_box_form", methods=['GET'])
@authenticate_researcher_login
def copy_data_to_box_page():

    researcher = Researcher.objects.get(username=session[SESSION_NAME])

    if not researcher.has_box_integration():
        return render_template(
                "box_integration.html",
                registration_url=get_registration_url(researcher.username),
                username=researcher.username,
                is_admin=researcher_is_an_admin()
                )
    else:

        iteratable_studies = get_researcher_allowed_studies(as_json=False)
        # dict of {study ids : list of user ids}

        users_by_study = {str(study['id']):
                          sorted([user.patient_id for user in Participant.objects.filter(study__id=study['id'])])
                          for study in iteratable_studies}

        # it is a bit obnoxious to get this data, we need to deduplcate it and then turn it back into a list

        return render_template(
                "copy_data_to_box_web_form.html",
                username=session[SESSION_NAME],
                allowed_studies=get_researcher_allowed_studies(),
                downloadable_studies=get_researcher_allowed_studies(),
                users_by_study=users_by_study,
                ALL_DATA_STREAMS=ALL_DATA_STREAMS,
                is_admin=researcher_is_an_admin()
        )

