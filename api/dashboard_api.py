import json
import pytz
from collections import OrderedDict
from datetime import date, datetime, timedelta

from flask import abort, Blueprint, render_template, request

from config.constants import (ALL_DATA_STREAMS, complete_data_stream_dict,
    processed_data_stream_dict, REDUCED_API_TIME_FORMAT)
from database.data_access_models import ChunkRegistry, PipelineRegistry
from database.study_models import (DashboardColorSetting, DashboardGradient, DashboardInflection,
    Study, Survey)
from database.user_models import Participant
from database.study_models import SurveyEvents
from libs.admin_authentication import (authenticate_researcher_study_access,
    get_researcher_allowed_studies, researcher_is_an_admin)
from config.settings import TIMEZONE

dashboard_api = Blueprint('dashboard_api', __name__)

DATETIME_FORMAT_ERROR = \
    f"Dates and times provided to this endpoint must be formatted like this: 2010-11-22 ({REDUCED_API_TIME_FORMAT})"


@dashboard_api.route("/dashboard/<string:study_id>", methods=["GET"])
@authenticate_researcher_study_access
def dashboard_page(study_id):
    study = get_study_or_404(study_id)
    """ information for the general dashboard view for a study"""
    participants = list(Participant.objects.filter(study=study_id, device_id__isnull=False).exclude(device_id='').\
            values_list("patient_id", flat=True).order_by('patient_id'))

    all_survey_streams = {}
    for survey in Survey.objects.filter(study=study_id):
        for event in ['notified', 'submitted', 'expired']:
            all_survey_streams.update({f'survey_{survey.object_id}_{event}': f'{survey.name} {event}'})

    ## update the total list of streams
    data_stream_dict = {}
    data_stream_dict.update(complete_data_stream_dict)
    data_stream_dict.update(all_survey_streams)

    return render_template(
        'dashboard/dashboard.html',
        study=study,
        participants=participants,
        study_id=study_id,
        data_stream_dict=data_stream_dict,
        allowed_studies=get_researcher_allowed_studies(),
        is_admin=researcher_is_an_admin(),
        page_location='dashboard_landing',
    )

@dashboard_api.route("/dashboard/<string:study_id>/data_stream/<string:data_stream>", methods=["GET", "POST"])
@authenticate_researcher_study_access
def get_data_for_dashboard_datastream_display(study_id, data_stream):

    """ parses information for the data stream dashboard view GET and POST requests"""
    # left the post and get requests in the same function because the body of the get request relies on the variables
    # set in the post request if a post request is sent --thus if a post request is sent we don't want all of the get
    # request running
    study = get_study_or_404(study_id)

    # -------------------------- for a POST request --------------------------------------
    if request.method == "POST":
        color_low_range, color_high_range, all_flags_list = set_default_settings_post_request(study, data_stream)
        if color_low_range == 0 and color_high_range == 0:
            show_color = "false"
        else:
            show_color = "true"

    # ------------------ below is for a GET request - POST requests will ALSO run this code! ------------------------
    else:
        color_low_range, color_high_range, show_color = extract_range_args_from_request()
        all_flags_list = extract_flag_args_from_request()

    default_filters = ""
    if DashboardColorSetting.objects.filter(data_type=data_stream, study=study).exists():
        settings = DashboardColorSetting.objects.get(data_type=data_stream, study=study)
        default_filters = DashboardColorSetting.get_dashboard_color_settings(settings)

    # -------------------------------- dealing with color settings -------------------------------------------------
    # test if there are default settings saved,
    # and if there are, test if the default filters should be used or if the user has overridden them
    if default_filters != "":
        inflection_info = default_filters["inflections"]
        if all_flags_list == [] and color_high_range is None and color_low_range is None:
            # since none of the filters are set, parse default filters to pass in the default settings
            # set the values for gradient filter
            # backend: color_range_min, color_range_max --> frontend: color_low_range, color_high_range
            # the above is consistent throughout the back and front ends
            if settings.gradient_exists():
                gradient_info = default_filters["gradient"]
                color_low_range = gradient_info["color_range_min"]
                color_high_range = gradient_info["color_range_max"]
                show_color = "true"
            else:
                color_high_range = 0
                color_low_range = 0
                show_color = "false"

            # set the values for the flag/inflection filter*s*
            # the html is expecting a list of lists for the flags [[operator, value], ... ]
            all_flags_list = []
            for flag_info in inflection_info:
                single_flag = [flag_info["operator"].encode("utf-8"), flag_info["inflection_point"]]
                all_flags_list.append(single_flag)

    # change the url params from jinja t/f to python understood T/F
    if show_color == "true":
        show_color = True
    elif show_color == "false":
        show_color = False

    # -----------------------------------  general data fetching --------------------------------------------
    start, end = extract_date_args_from_request()
    unique_dates = []
    next_url = ""
    past_url = ""
    byte_streams = {}
    data_exists = None

    if start:
        start = start.replace(tzinfo=pytz.timezone(TIMEZONE))

    if end:
        end = end.replace(tzinfo=pytz.timezone(TIMEZONE))
    # --------------------- decide whether data is in Processed DB or Bytes DB -----------------------------

    # calculate stream names for the study's surveys
    all_survey_streams = {}
    for survey in Survey.objects.filter(study=study_id):
        for event in ['notified', 'submitted', 'expired']:
            all_survey_streams.update({f'survey_{survey.object_id}_{event}': f'{survey.name} {event}'})

    data_stream_dict = {}
    data_stream_dict.update(complete_data_stream_dict)
    data_stream_dict.update(all_survey_streams)

    if data_stream in ALL_DATA_STREAMS:
        first_data_date, last_data_date, stream_data = \
                parse_data_stream_chunk_data(study_id, data_stream)

    elif data_stream in all_survey_streams:
        first_data_date, last_data_date, stream_data = \
                parse_data_stream_survey_data(study_id, data_stream)

    else:
        first_data_date, last_data_date, stream_data = \
                parse_data_stream_processed_data(data_stream, study_id, participant_objects)

    if first_data_date and last_data_date:
        unique_dates, _, _ = get_unique_dates(start, end, first_data_date, last_data_date)
        next_url, past_url = create_next_past_urls(first_data_date, last_data_date, start=start, end=end)

    # check if there is data to display
    stream_data_summary = {}
    if stream_data:
        data_exists = True
        for pt, data_dict in stream_data.items():
            for dt in data_dict:
                if pt not in stream_data_summary:
                    stream_data_summary[pt] = 0
                stream_data_summary[pt] += stream_data[pt][dt]

    # ---------------------------------- base case if there is no data ------------------------------------------
    if first_data_date is None or (not data_exists and past_url == ""):
        unique_dates = []
        next_url = ""
        past_url = ""
        byte_streams = {}

    return render_template(
        'dashboard/data_stream_dashboard.html',
        study=study,
        data_stream=data_stream_dict.get(data_stream),
        times=unique_dates,
        byte_streams=stream_data,
        byte_streams_summary=stream_data_summary,
        base_next_url=next_url,
        base_past_url=past_url,
        study_id=study_id,
        data_stream_dict=data_stream_dict,
        color_low_range=color_low_range,
        color_high_range=color_high_range,
        first_day=first_data_date,
        last_day=last_data_date,
        show_color=show_color,
        all_flags_list=all_flags_list,
        allowed_studies=get_researcher_allowed_studies(),
        is_admin=researcher_is_an_admin(),
        page_location='dashboard_data',
    )


@dashboard_api.route("/dashboard/<string:study_id>/patient/<string:patient_id>", methods=["GET"])
@authenticate_researcher_study_access
def get_data_for_dashboard_patient_display(study_id, patient_id):
    """ parses data to be displayed for the singular participant dashboard view """
    study = get_study_or_404(study_id)
    participant = get_participant(patient_id, study_id)
    first_date, last_date = extract_date_args_from_request()
    patient_ids = list(Participant.objects
                       .filter(study=study_id, device_id__isnull=False)
                       .exclude(patient_id=patient_id)
                       .values_list("patient_id", flat=True)
                       )

    if first_date:
        first_date = first_date.replace(tzinfo=pytz.timezone(TIMEZONE))

    if last_date:
        last_date = last_date.replace(tzinfo=pytz.timezone(TIMEZONE))

    # ---- get data from the ChunkRegistry, PipelineRegistry, and SurveyEvents tables, data returned in a nested dictionary
    #      of the form { stream_name: {time_bin: value} }
    chunk_first_date, chunk_last_date, chunk_data = parse_participant_chunk_data(study_id, participant)
    processed_data_first_date, processed_data_last_date, processed_data = parse_patient_processed_data(study_id, participant)
    survey_data_first_date, survey_data_last_date, survey_data = parse_participant_survey_data(study_id, participant)

    # determine the first and last dates for which data is available
    all_boundary_dates = [time_bin for time_bin in [chunk_first_date, chunk_last_date, processed_data_first_date,
        processed_data_last_date, survey_data_first_date, survey_data_last_date] if time_bin]

    if all_boundary_dates:
        first_data_date = min(all_boundary_dates)
        last_data_date  = max(all_boundary_dates)
    else:
        first_data_date = None
        last_data_date = None 

    # ---------------------- get next/past urls and unique dates, as long as data has been entered -------------------
    if first_data_date and last_data_date:
        next_url, past_url = create_next_past_urls(first_data_date, last_data_date, start=first_date, end=last_date)
        unique_dates, _, _ = get_unique_dates(first_date, last_date, first_data_date, last_data_date)

    # combine the data, do not impute missing values or throughout data corresponding to out of bound dates, 
    # that can be done in the jinja template
    byte_streams = OrderedDict()
    byte_streams.update(processed_data)
    byte_streams.update(chunk_data)
    byte_streams.update(survey_data)

    # calculate summary information across all measures
    byte_stream_summary = {}
    for stream, stream_dict in byte_streams.items():
        for time_bin, value in stream_dict.items():
            if stream not in byte_stream_summary:
                byte_stream_summary[stream] = 0
            byte_stream_summary[stream] += value

    # calculate stream names for the study's surveys
    all_survey_streams = {}
    for survey in Survey.objects.filter(study=study_id):
        for event in ['notified', 'submitted', 'expired']:
            all_survey_streams.update({f'survey_{survey.object_id}_{event}': f'Survey {survey.object_id} {event}'})

    ## update the total list of streams
    data_stream_dict = {}
    data_stream_dict.update(complete_data_stream_dict)
    data_stream_dict.update(all_survey_streams)

    # -------------------------  edge case if no data has been entered -----------------------------------
    if not byte_streams:
        byte_streams = {}
        unique_dates = []
        next_url = ""
        past_url = ""
        first_data_date = ""
        last_data_date = ""

    return render_template(
        'dashboard/participant_dashboard.html',
        study=study,
        patient_id=patient_id,
        participant=participant,
        times=unique_dates,
        byte_streams=byte_streams,
        byte_stream_summary=byte_stream_summary,
        next_url=next_url,
        past_url=past_url,
        patient_ids=patient_ids,
        study_id=study_id,
        first_date_data=first_data_date,
        last_date_data=last_data_date,
        data_stream_dict=data_stream_dict,
        allowed_studies=get_researcher_allowed_studies(),
        is_admin=researcher_is_an_admin(),
        page_location='dashboard_patient',
    )

### Utilities

def parse_data_stream_chunk_data(study_id, data_stream):

    # we will parse the chunk registry information into a nested dictionary
    # of the form {participant_id: {time_bin: value}}
    chunks_summary_dict = {}
    time_bins = []
    start_time = None
    end_time = None

    try:
        chunk_array = list(ChunkRegistry.objects.filter(study=study_id, data_type=data_stream)
                .values("participant__patient_id", "file_size", "time_bin"))
    except ChunkRegistry.DoesNotExist:
        return abort(404)

    for chunk in chunk_array:
        time_bin = chunk["time_bin"].astimezone(pytz.timezone(TIMEZONE)).date()
        time_bins.append(time_bin)

        participant_id = chunk["participant__patient_id"]

        if participant_id not in chunks_summary_dict:
            chunks_summary_dict[participant_id] = {}

        if time_bin not in chunks_summary_dict[participant_id]:
            chunks_summary_dict[participant_id][time_bin] = 0

        chunks_summary_dict[participant_id][time_bin] += chunk["file_size"]

    if time_bins:
        start_time = min(time_bins)
        end_time = max(time_bins)

    return start_time, end_time, chunks_summary_dict

def parse_participant_chunk_data(study_id, participant):

    try:
        chunk_array = ChunkRegistry.objects.filter(participant=participant)
    except ChunkRegistry.DoesNotExist:
        return abort(404)

    chunks_summary_dict = {}
    time_bins = []
    start_time = None
    end_time = None

    for chunk in chunk_array:

        time_bin = chunk.time_bin.astimezone(pytz.timezone(TIMEZONE)).date()
        time_bins.append(time_bin)

        stream_key = chunk.data_type

        if stream_key not in chunks_summary_dict:
            chunks_summary_dict[stream_key] = {}

        if time_bin not in chunks_summary_dict[stream_key]:
            chunks_summary_dict[stream_key][time_bin] = 0

        chunks_summary_dict[stream_key][time_bin] += chunk.file_size

    if time_bins:
        start_time = min(time_bins)
        end_time = max(time_bins)

    return start_time, end_time, chunks_summary_dict

def parse_data_stream_survey_data(study_id, data_stream):

    survey_events_summary_dict = {}
    time_bins = []
    start_time = None
    end_time = None

    data_stream_values = data_stream.split('_')
    survey_object_id = data_stream_values[1]
    event_type = data_stream_values[2]

    try:
        survey_event_array = list(SurveyEvents.objects.
                filter(study=study_id, survey__object_id=survey_object_id, event_type=event_type).
                values("participant__patient_id", "timestamp"))
    except SurveyEvents.DoesNotExist:
        return abort(404)


    for survey_event in survey_event_array:

        time_bin = survey_event["timestamp"].astimezone(pytz.timezone(TIMEZONE)).date()
        time_bins.append(time_bin)

        participant_id = survey_event["participant__patient_id"]

        if participant_id not in survey_events_summary_dict:
            survey_events_summary_dict[participant_id] = {}

        if time_bin not in survey_events_summary_dict[participant_id]:
            survey_events_summary_dict[participant_id][time_bin] = 0

        survey_events_summary_dict[participant_id][time_bin] += 1

    if time_bins:
        start_time = min(time_bins)
        end_time = max(time_bins)

    return start_time, end_time, survey_events_summary_dict

def parse_participant_survey_data(study_id, participant):

    try:
        survey_event_array = SurveyEvents.objects.filter(participant=participant)
    except SurveyEvents.DoesNotExist:
        return abort(404)

    survey_events_summary_dict = {}
    time_bins = []
    start_time = None
    end_time = None

    for survey_event in survey_event_array:

        time_bin = survey_event.timestamp.astimezone(pytz.timezone(TIMEZONE)).date()
        time_bins.append(time_bin)

        stream_key = f'survey_{survey_event.survey.object_id}_{survey_event.event_type}'

        if stream_key not in survey_events_summary_dict:
            survey_events_summary_dict[stream_key] = {}

        if time_bin not in survey_events_summary_dict[stream_key]:
            survey_events_summary_dict[stream_key][time_bin] = 0

        survey_events_summary_dict[stream_key][time_bin] += 1

    if time_bins:
        start_time = min(time_bins)
        end_time = max(time_bins)

    return start_time, end_time, survey_events_summary_dict


def parse_processed_data(study_id, participant_objects, data_stream):
    """
    get a list of dicts (pipeline_chunks) of the patient's data and extract the data for the data stream we want
    stream_data = OrderedDict(participant.patient_id: {"time_bin":time_bin, "processed_data": processed_data}, ...)
    this structure is similar to the stream_data structure in get_data_for_dashboard_data_stream_display
    since they perform similar functions
    """
    first = True
    data_exists = False
    first_day = None
    last_day = None
    stream_data = OrderedDict()
    for participant in participant_objects:
        pipeline_chunks = dashboard_pipelineregistry_query(study_id, participant.id)
        list_of_dicts_data = []
        if pipeline_chunks is not None:
            for chunk in pipeline_chunks:
                if data_stream in chunk and "day" in chunk and chunk[data_stream] != "NA":
                    time_bin = datetime.strptime(chunk["day"].encode("utf-8"), REDUCED_API_TIME_FORMAT).date()
                    data_exists = True
                    if first:
                        first_day = time_bin
                        last_day = time_bin
                        first = False
                    else:
                        if (time_bin - first_day).days < 0:
                            first_day = time_bin
                        elif (time_bin - last_day).days > 0:
                            last_day = time_bin
                    # check to see if the data should be a float or an int
                    if chunk[data_stream].encode("utf-8").find(".") == -1:
                        processed_data = int(chunk[data_stream])
                    else:
                        processed_data = float(chunk[data_stream])
                    list_of_dicts_data.append({"time_bin": time_bin, "processed_data": processed_data})

        stream_data[participant.patient_id] = None if not data_exists else list_of_dicts_data
        data_exists = False  # you need to reset this
    return first_day, last_day, stream_data


def parse_patient_processed_data(study_id, participant):
    """    create a list of dicts of processed data for one patient.
    [{"time_bin": , "processed_data": , "data_stream": ,}...]
    if there is no data for a patient, first_day and last_day will be None, and all_data will be an empty list
    """
    first = True
    first_day = None
    last_day = None
    pipeline_chunks = dashboard_pipelineregistry_query(study_id, participant.id)
    all_data = []
    if pipeline_chunks is not None:
        for chunk in pipeline_chunks:
            if "day" in chunk:
                time_bin = datetime.strptime(chunk["day"].encode("utf-8"), REDUCED_API_TIME_FORMAT).date()
                if first:
                    first_day = time_bin
                    last_day = time_bin
                    first = False
                else:
                    if (time_bin - first_day).days < 0:
                        first_day = time_bin
                    elif (time_bin - last_day).days > 0:
                        last_day = time_bin
                for stream_key in chunk:
                    if stream_key in processed_data_stream_dict and chunk[stream_key] != "NA":
                        if chunk[stream_key].encode("utf-8").find(".") == -1:
                            processed_data = int(chunk[stream_key])
                        else:
                            processed_data = float(chunk[stream_key])
                        all_data.append({"time_bin": time_bin, "processed_data": processed_data, "data_stream": stream_key})
    return first_day, last_day, all_data


def set_default_settings_post_request(study, data_stream):
    # get all of the variables
    all_flags_list = request.form.get("all_flags_list", "[]")
    color_high_range = request.form.get("color_high_range", 0)
    color_low_range = request.form.get("color_low_range", 0)

    # convert parameters from unicode to correct types
    # if they didn't save a gradient we don't want to save garbage
    all_flags_list = json.loads(all_flags_list)
    if color_high_range == "0" and color_low_range == "0":
        color_low_range = 0
        color_high_range = 0
        bool_create_gradient = False
    else:
        bool_create_gradient = True
        color_low_range = int(json.loads(color_low_range))
        color_high_range = int(json.loads(color_high_range))

    # make the operator a string
    for flag in all_flags_list:
        flag[0] = flag[0].encode("utf-8")

    # try to get a DashboardColorSetting object and check if it exists
    if DashboardColorSetting.objects.filter(data_type=data_stream, study=study).exists():
        # in this case, a default settings model already exists
        # now we delete the inflections associated with it
        settings = DashboardColorSetting.objects.get(data_type=data_stream, study=study)
        settings.inflections.all().delete()
        if settings.gradient_exists():
            settings.gradient.delete()

        if bool_create_gradient:
            # create new gradient
            gradient, _ = DashboardGradient.objects.get_or_create(dashboard_color_setting=settings)
            gradient.color_range_max = color_high_range
            gradient.color_range_min = color_low_range
            gradient.save()

        # create new inflections
        for flag in all_flags_list:
            # all_flags_list looks like this: [[operator, inflection_point], ...]
            inflection = DashboardInflection.objects.create(dashboard_color_setting=settings, operator=flag[0])
            inflection.operator = flag[0]
            inflection.inflection_point = flag[1]
            inflection.save()
        settings.save()
    else:
        # this is the case if a default settings does not yet exist
        # create a new dashboard color setting in memory
        settings = DashboardColorSetting.objects.create(data_type=data_stream, study=study)

        # create new gradient
        if bool_create_gradient:
            gradient = DashboardGradient.objects.create(dashboard_color_setting=settings)
            gradient.color_range_max = color_high_range
            gradient.color_range_min = color_low_range

        # create new inflections
        for flag in all_flags_list:
            inflection = DashboardInflection.objects.create(dashboard_color_setting=settings, operator=flag[0])
            inflection.operator = flag[0]
            inflection.inflection_point = flag[1]

        # save the dashboard color setting to the backend (currently is just in memory)
        settings.save()

    return color_low_range, color_high_range, all_flags_list


def get_study_or_404(study_id):
    try:
        return Study.objects.get(pk=study_id)
    except Study.DoesNotExist:
        return abort(404)


def get_unique_dates(start, end, first_day, last_day, chunks=None):
    """ create a list of all the unique days in which data was recorded for this study """
    first_date_data_entry = None
    last_date_data_entry = None
    if chunks:
        all_dates = sorted(
            chunk["time_bin"].date() for chunk in chunks if chunk["time_bin"].date() >= first_day
            # must be >= first day bc there are some point for 1970 that get filtered out bc obv are garbage
        )

        # create a list of all of the valid days in this study
        first_date_data_entry = all_dates[0]
        last_date_data_entry = all_dates[-1]

    # validate start date is before end date
    if (start and end) and (end.date() - start.date()).days < 0:
        temp = start
        start = end
        end = temp

    # unique_dates is all of the dates for the week we are showing
    if start is None: # if start is none default to end
        end_num = min((last_day - first_day).days + 1, 7)
        unique_dates = [(last_day - timedelta(days=end_num - 1)) + timedelta(days=date) for date in range(end_num)]
        # unique_dates = [(first_day + timedelta(days=date)) for date in range(end_num)]
    elif end is None:  # if end if none default to 7 days
        end_num = min((last_day - start.date()).days + 1, 7)
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]
    elif (start.date() - first_day).days < 0:
        # this is the edge case for out of bounds at beginning to keep the duration the same
        end_num = (end.date() - first_day).days + 1
        unique_dates = [(first_day + timedelta(days=date)) for date in range(end_num)]
    elif (last_day - end.date()).days < 0:
        # this is the edge case for out of bounds at end to keep the duration the same
        end_num = (last_day - start.date()).days + 1
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]
    else:  # this is if they specify both start and end
        end_num = (end.date() - start.date()).days + 1
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]

    return unique_dates, first_date_data_entry, last_date_data_entry


def create_next_past_urls(first_day, last_day, start=None, end=None):
    """ set the URLs of the next/past pages for patient and data stream dashboard """
    # note: in the "if" cases, the dates are intentionally allowed outside the data collection date
    # range so that the duration stays the same if you page backwards instead of resetting
    # to the number currently shown

    if start and end:
        duration = (end.date() - start.date()).days
    else:
        duration = 6
        start = datetime.combine(last_day - timedelta(days=6), datetime.min.time())
        end = datetime.combine(last_day, datetime.min.time())

    if 0 < (start.date() - first_day).days < duration:
        past_url = "?start=" + (start.date() - timedelta(days=(duration + 1))).strftime(REDUCED_API_TIME_FORMAT) + \
                   "&end=" + (start.date() - timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT)

    elif (start.date() - first_day).days <= 0:
        past_url = ""
    else:
        past_url = "?start=" + (start.date() - timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT) + \
                    "&end=" + (start.date() - timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT)
    if (last_day - timedelta(days=duration + 1)) < end.date() < (last_day - timedelta(days=1)):
        next_url = "?start=" + (end.date() + timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT) + "&end=" + \
                   (end.date() + timedelta(days=(duration + 1))).strftime(REDUCED_API_TIME_FORMAT)
    elif (last_day - end.date()).days <= 0:
        next_url = ""
    else:
        next_url = "?start=" + \
                   (start.date() + timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT) + "&end=" + \
                   (end.date() + timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT)
    return next_url, past_url


def get_bytes_data_stream_match(chunks, date, stream):
    """ returns byte value for correct chunk based on data stream and type comparisons"""
    all_bytes = None
    for chunk in chunks:
        if (chunk["time_bin"]).date() == date and chunk["data_stream"] == stream:
            if all_bytes is None:
                all_bytes = chunk.get("bytes", 0)
            else:
                all_bytes += chunk.get("bytes", 0)
    if all_bytes is not None:
        return all_bytes
    else:
        return None


def get_bytes_participant_match(stream_data, date):
    all_bytes = None
    for data_point in stream_data:
        if (data_point["time_bin"]).date() == date:
            if all_bytes is None:
                all_bytes = data_point.get("bytes", 0)
            else:
                all_bytes += data_point.get("bytes", 0)
    if all_bytes is not None:
        return all_bytes
    else:
        return None


def get_bytes_processed_data_match(participant_data, date):
    # participant_data is a list of dicts which hold {time_bin: , processed_data: }
    # there should only ever be one data_point corresponding to a specific date per patient
    # if no data exists, return None -- if the participant_data object is none, there is no data for this data
    # stream for this participant
    if participant_data is not None:
        for data_point in participant_data:
            if(data_point["time_bin"]) == date:
                return data_point["processed_data"]
    return None


def get_bytes_patient_processed_match(participant_data, date, stream):
    # participant_data is a list of dicts which hold {time_bin: , processed_data: , stream:, }
    # there should only ever be one data_point corresponding to a specific date per patient
    # if no data exists, return None -- if the participant_data object is none, there is no data for this data
    # stream for this participant
    if participant_data is not None:
        for data_point in participant_data:
            if(data_point["time_bin"]) == date and data_point["data_stream"] == stream:
                return data_point["processed_data"]
    return None


def dashboard_chunkregistry_date_query(study_id, data_stream=None):
    """ gets the first and last days in the study excluding 1/1/1970 bc that is obviously an error and makes
    the frontend annoying to use """
    kwargs = {"study_id": study_id}
    if data_stream:
        kwargs["data_type"] = data_stream
    first = ChunkRegistry.objects.filter(**kwargs).exclude(time_bin__date=date(1970, 1, 1)).order_by("time_bin").values_list("time_bin", flat=True).first()
    last = ChunkRegistry.objects.filter(**kwargs).order_by("time_bin").values_list("time_bin", flat=True).last()
    if first is None or last is None:
        return None, None
    else:
        return first.date(), last.date()


def dashboard_chunkregistry_query(participant_id, data_stream=None, start=None, end=None):
    """ Queries ChunkRegistry based on the provided parameters and returns a list of dictionaries
    with 3 keys: bytes, data_stream, and time_bin. """
    kwargs = {"participant__id": participant_id}
    if start:
        kwargs["time_bin__gte"] = start
    if end:
        kwargs["time_bin__lte"] = end
    if data_stream:
        kwargs["data_type"] = data_stream

    # on a (good) test device running on sqlite, for 12,200 chunks, this takes ~135ms
    # sticking the query_set directly into a list is a slight speedup. (We need it all in memory anyway.)
    chunks = list(
        ChunkRegistry.objects.filter(**kwargs)
        .extra(
            select={
                # rename the data_type and file_size fields in the db query itself for speed
                'data_stream': 'data_type',
                'bytes': 'file_size',
            }
        ).values("bytes", "data_stream", "time_bin")
    )

    return chunks


def dashboard_pipelineregistry_query(study_id, participant_id):
    """ Queries Pipeline based on the provided parameters and returns a list of dicts with
    an id (which is ignored), a "day", and a bunch of strings which are data streams """
    # pipeline_chunks looks like this: [{day: 3/4/4, "data_stream1": 36634, "data_stream2": 2525}, ... ]
    pipeline_data = PipelineRegistry.objects.filter(study_id=study_id, participant__id=participant_id).order_by(
        "uploaded_at").last()
    if pipeline_data is not None:
        pipeline_chunks = json.loads(json.dumps(pipeline_data.processed_data)) # I feel like this shouldn't work but idk
        if pipeline_chunks:
            return pipeline_chunks

    return None


def extract_date_args_from_request():
    """ Gets start and end arguments from GET/POST params, throws 400 on date formatting errors. """
    start = request.values.get("start", None)
    end = request.values.get("end", None)
    try:
        if start:
            start = datetime.strptime(start, REDUCED_API_TIME_FORMAT)
        if end:
            end = datetime.strptime(end, REDUCED_API_TIME_FORMAT)
    except ValueError as e:
        return abort(400, DATETIME_FORMAT_ERROR)

    return start, end


def extract_range_args_from_request():
    """ Gets minimum and maximum arguments from GET/POST params """
    color_low_range = request.values.get("color_low", None)
    color_high_range = request.values.get("color_high", None)
    show_color = request.values.get("show_color", True)

    return color_low_range, color_high_range, show_color


def extract_flag_args_from_request():
    """ Gets minimum and maximum arguments from GET/POST params, returns None if the object is None or empty """
    all_flags_string = request.values.get("flags", "")
    all_flags_list = []
    # parse to create a dict of flags
    flags_seperated = all_flags_string.split('*')
    for flag in flags_seperated:
        if flag != "":
            flag_apart = flag.split(',')
            string = flag_apart[0].encode("utf-8")
            all_flags_list.append([string, int(flag_apart[1])])
    return all_flags_list


def extract_data_stream_args_from_request():
    """ Gets data stream if it is provided as a request POST or GET parameter,
    throws 400 errors on unknown data streams. """
    data_stream = request.values.get("data_stream", None)
    if data_stream:
        if data_stream not in ALL_DATA_STREAMS:
            return abort(400, f"unrecognized data stream '{data_stream}'")
    return data_stream


def get_participant(patient_id, study_id):
    """ Just factoring out a common abort operation. """
    try:
        return Participant.objects.get(study=study_id, patient_id=patient_id)
    except Participant.DoesNotExist:
        # 2 useful error messages
        if not Participant.objects.get(patient_id=patient_id).exists():
            return abort(400, "No such user exists.")
        else:
            return abort(400, "No such user exists in this study.")

