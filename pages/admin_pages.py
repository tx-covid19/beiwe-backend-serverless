from flask import abort, Blueprint, flash, Markup, redirect, render_template, request, session

from database.study_models import Study, StudyField
from database.user_models import Participant, ParticipantFieldValue, Researcher, ParticipantAliases
from database.pipeline_models import PipelineExecutionTracking
from database.fitbit_models import FitbitCredentials
from libs import admin_authentication
from libs.admin_authentication import (authenticate_researcher_login,
    authenticate_researcher_study_access, get_researcher_allowed_studies,
    get_researcher_allowed_studies_as_query_set, researcher_is_an_admin, SESSION_NAME)
from libs.security import check_password_requirements

admin_pages = Blueprint('admin_pages', __name__)

# TODO: Document.


@admin_pages.route('/choose_study', methods=['GET'])
@authenticate_researcher_login
def choose_study():
    allowed_studies = get_researcher_allowed_studies_as_query_set()

    # If the admin is authorized to view exactly 1 study, redirect to that study
    if allowed_studies.count() == 1:
        return redirect('/view_study/{:d}'.format(allowed_studies.values_list('pk', flat=True).get()))

    # Otherwise, show the "Choose Study" page
    allowed_studies_json = Study.query_set_as_native_json(allowed_studies)
    return render_template(
        'choose_study.html',
        studies=allowed_studies_json,
        allowed_studies=allowed_studies_json,
        is_admin=researcher_is_an_admin()
    )

@admin_pages.route('/create_new_alias/<string:study_id>', methods=['GET', 'POST'])
@authenticate_researcher_study_access
def create_new_alias(study_id=None):
    if request.method == 'GET':
        return render_template(
            'create_new_alias.html',
            study_id=study_id,
            allowed_studies=get_researcher_allowed_studies(),
            is_admin=researcher_is_an_admin()
        )

    # Drop any whitespace or special characters from the username
    reference_id = ''.join(e for e in request.form.get('reference_id', '') if e.isalnum())
    alias_id = ''.join(e for e in request.form.get('alias_id', '') if e.isalnum())

    for participant_id in [reference_id, alias_id]:
        if not Participant.objects.filter(patient_id=participant_id).exists():
            flash('ID {0} was not found in the Participant database, alias was not added to database'.format(participant_id), 'danger')
            return redirect('/create_new_alias/{:d}'.format(int(study_id)))

    if ParticipantAliases.objects.filter(reference_id=reference_id, alias_id=alias_id).exists():
        flash("There is already an alias {0} => {1}".format(reference_id, alias_id), 'danger')
        return redirect('/create_new_alias/{:d}'.format(int(study_id)))

    try:
        new_alias = ParticipantAliases(study_id=study_id, reference_id=reference_id, alias_id=alias_id)
        new_alias.save()
    except:
        flash("Error, There is a problem with one or both of the entered IDs ({0}, {1}). They should be 8 character alphanumeric strings.".format(reference_id, alias_id), 'danger')
        return redirect('/create_new_alias/{:d}'.format(int(study_id)))

    return redirect('/view_study/{:d}'.format(int(study_id)))

@admin_pages.route('/delete_alias', methods=["POST"])
@authenticate_researcher_study_access
def delete_alias():
    """
    Deletes an alias from the ParticipantsAlias table
    """

    alias_id = request.values['alias_id']
    study_id = request.values['study_id']
    try:
        ParticipantAliases.objects.filter(id=alias_id).delete()
    except:
        flash('Sorry, something went wrong when trying to delete the alias.', 'danger')

    return redirect('/view_study/{:s}'.format(study_id))

@admin_pages.route('/view_study/<string:study_id>', methods=['GET'])
@authenticate_researcher_study_access
def view_study(study_id=None):
    study = Study.objects.get(pk=study_id)
    tracking_survey_ids = study.get_survey_ids_and_object_ids_for_study('tracking_survey')
    audio_survey_ids = study.get_survey_ids_and_object_ids_for_study('audio_survey')
    image_survey_ids = study.get_survey_ids_and_object_ids_for_study('image_survey')
    participants = study.participants.all()
    fitbit_registrations = FitbitCredentials.objects.all().values_list('participant_id', flat=True)

    study_fields = list(study.fields.all().values_list('field_name', flat=True))
    study_fields.append('Fitbit')
    for p in participants:
        p.values_dict = {tag.field.field_name: tag.value for tag in p.field_values.all()}
        if p.id in fitbit_registrations:
            p.values_dict['Fitbit'] = 'Registered'
        else:
            p.values_dict['Fitbit'] = 'Not Registered'

    aliases = ParticipantAliases.objects.filter(study_id=study_id)

    return render_template(
        'view_study.html',
        study=study,
        patients=participants,
        aliases=aliases,
        audio_survey_ids=audio_survey_ids,
        image_survey_ids=image_survey_ids,
        tracking_survey_ids=tracking_survey_ids,
        allowed_studies=get_researcher_allowed_studies(),
        is_admin=researcher_is_an_admin(),
        study_fields=study_fields,
        page_location='study_landing',
        study_id=study_id,
    )


@admin_pages.route('/job-queue', methods=['GET'])
def view_job_queue(study_id=None):

    researcher = Researcher.objects.get(username=session[SESSION_NAME])
    if researcher.site_admin:
        pipelines = PipelineExecutionTracking.objects.filter(deleted=False)
    else:
        pipelines = researcher.researcher_pipelines.all()

    return render_template(
        'job-queue.html',
        username=researcher.username,
        pipelines=pipelines,
        allowed_studies=get_researcher_allowed_studies(),
    )

@admin_pages.route('/data-pipeline/<string:study_id>', methods=['GET'])
@authenticate_researcher_study_access
def view_study_data_pipeline(study_id=None):
    study = Study.objects.get(pk=study_id)
    pipelines = study.study_pipelines.all()
    study_participants = [str(user.patient_id) for user in study.participants.exclude(device_id__isnull=True, os_type__exact='')]

    return render_template(
        'data-pipeline.html',
        study=study,
        pipelines=pipelines,
        study_participants=study_participants,
        allowed_studies=get_researcher_allowed_studies(),
    )


@admin_pages.route('/view_study/<string:study_id>/patient_fields/<string:patient_id>', methods=['GET', 'POST'])
@authenticate_researcher_study_access
def patient_fields(study_id, patient_id=None):
    try:
        patient = Participant.objects.get(pk=patient_id)
    except Participant.DoesNotExist:
        return abort(404)

    patient.values_dict = {tag.field.field_name: tag.value for tag in patient.field_values.all()}
    study = patient.study
    if request.method == 'GET':
        return render_template(
            'view_patient_custom_field_values.html',
            fields=study.fields.all(),
            study=study,
            patient=patient,
            allowed_studies=get_researcher_allowed_studies(),
            is_admin=researcher_is_an_admin(),
        )

    fields = list(study.fields.values_list('field_name', flat=True))
    for key, value in request.values.items():
        if key in fields:
            pfv, created = ParticipantFieldValue.objects.get_or_create(participant=patient, field=StudyField.objects.get(study=study, field_name=key))
            pfv.value = value
            pfv.save()

    return redirect('/view_study/{:d}'.format(study.id))


"""########################## Login/Logoff ##################################"""


@admin_pages.route('/')
@admin_pages.route('/admin')
def render_login_page():
    if admin_authentication.is_logged_in():
        return redirect("/choose_study")
    return render_template('admin_login.html')


@admin_pages.route("/logout")
def logout():
    admin_authentication.logout_researcher()
    return redirect("/")


@admin_pages.route("/validate_login", methods=["GET", "POST"])
def login():
    """ Authenticates administrator login, redirects to login page if authentication fails. """
    if request.method == 'POST':
        username = request.values["username"]
        password = request.values["password"]
        if Researcher.check_password(username, password):
            admin_authentication.log_in_researcher(username)
            return redirect("/choose_study")
        else:
            flash("Incorrect username & password combination; try again.", 'danger')

    return redirect("/")


@admin_pages.route('/manage_credentials')
@authenticate_researcher_login
def manage_credentials():
    return render_template('manage_credentials.html',
                           allowed_studies=get_researcher_allowed_studies(),
                           is_admin=researcher_is_an_admin())


@admin_pages.route('/reset_admin_password', methods=['POST'])
@authenticate_researcher_login
def reset_admin_password():
    username = session[SESSION_NAME]
    current_password = request.values['current_password']
    new_password = request.values['new_password']
    confirm_new_password = request.values['confirm_new_password']
    if not Researcher.check_password(username, current_password):
        flash("The Current Password you have entered is invalid", 'danger')
        return redirect('/manage_credentials')
    if not check_password_requirements(new_password, flash_message=True):
        return redirect("/manage_credentials")
    if new_password != confirm_new_password:
        flash("New Password does not match Confirm New Password", 'danger')
        return redirect('/manage_credentials')
    Researcher.objects.get(username=username).set_password(new_password)
    flash("Your password has been reset!", 'success')
    return redirect('/manage_credentials')


@admin_pages.route('/reset_download_api_credentials', methods=['POST'])
@authenticate_researcher_login
def reset_download_api_credentials():
    researcher = Researcher.objects.get(username=session[SESSION_NAME])
    access_key, secret_key = researcher.reset_access_credentials()
    msg = """<h3>Your Data-Download API access credentials have been reset!</h3>
        <p>Your new <b>Access Key</b> is:
          <div class="container-fluid">
            <textarea rows="1" cols="85" readonly="readonly" onclick="this.focus();this.select()">%s</textarea></p>
          </div>
        <p>Your new <b>Secret Key</b> is:
          <div class="container-fluid">
            <textarea rows="1" cols="85" readonly="readonly" onclick="this.focus();this.select()">%s</textarea></p>
          </div>
        <p>Please record these somewhere; they will not be shown again!</p>""" \
        % (access_key, secret_key)
    flash(Markup(msg), 'warning')
    return redirect("/manage_credentials")
