import json
from datetime import datetime, timedelta
from json import JSONDecodeError

from firebase_admin import (delete_app as delete_firebase_instance,
    get_app as get_firebase_app, initialize_app as initialize_firebase_app)
from firebase_admin.credentials import Certificate as FirebaseCertificate

from config.constants import (ANDROID_FIREBASE_CREDENTIALS, BACKEND_FIREBASE_CREDENTIALS,
    FIREBASE_APP_TEST_NAME, IOS_FIREBASE_CREDENTIALS)
from database.schedule_models import ArchivedEvent, ScheduledEvent, WeeklySchedule
from database.study_models import Study
from database.survey_models import Survey
from database.system_models import FileAsText
from database.user_models import Participant


class FirebaseMisconfigured(Exception): pass
class NoSchedulesException(Exception): pass


def safely_get_db_credential(credential_type: str) -> str or None:
    """ just a wrapper to handle ugly code """
    credentials = FileAsText.objects.filter(tag=credential_type).first()
    if credentials:
        return credentials.text
    else:
        return None


def get_firebase_credential_errors(credentials: str):
    """ Wrapper to get error strings for test_firebase_credential_errors because otherwise the
        code is gross.  Returns None if no errors occurred. """
    try:
        test_firebase_credential_errors(credentials)
        return None
    except Exception as e:
        return str(e)


def test_firebase_credential_errors(credentials: str) -> None:
    """ Tests credentials by creating a temporary otherwise unused credential. """
    try:
        encoded_credentials = json.loads(credentials)
    except JSONDecodeError:
        # need clean error message
        raise Exception("The credentials provided are not valid JSON.")

    # both of these raise ValueErrors, delete only fails if cert and app objects pass.
    cert = FirebaseCertificate(encoded_credentials)
    app = initialize_firebase_app(cert, name=FIREBASE_APP_TEST_NAME)
    delete_firebase_instance(app)


def check_firebase_instance(require_android=False, require_ios=False) -> bool:
    """ Test the database state for the various creds. If creds are present determine whether
    the firebase app is already instantiated, if not call update_firebase_instance. """
    active_creds = list(FileAsText.objects.filter(
        tag__in=[BACKEND_FIREBASE_CREDENTIALS, ANDROID_FIREBASE_CREDENTIALS, IOS_FIREBASE_CREDENTIALS]
    ).values_list("tag", flat=True))

    if (    # keep those parens.
            BACKEND_FIREBASE_CREDENTIALS not in active_creds
            or (require_android and ANDROID_FIREBASE_CREDENTIALS not in active_creds)
            or (require_ios and IOS_FIREBASE_CREDENTIALS not in active_creds)
    ):
        return False

    if get_firebase_credential_errors(safely_get_db_credential(BACKEND_FIREBASE_CREDENTIALS)):
        return False

    # avoid calling update so we never delete and then recreate the app (we get thrashed
    # during push notification send from calling this, its not thread-safe), overhead is low.
    try:
        get_firebase_app()
    except ValueError:
        # we don't care about extra work inside calling update_firebase_instance, it shouldn't be
        # hit too heavily.
        update_firebase_instance()

    return True


def update_firebase_instance(rucur_depth=3) -> None:
    """ Creates or destroys the firebase app, handling basic credential errors. """
    junk_creds = False
    encoded_credentials = None  # IDE complains

    try:
        encoded_credentials = json.loads(safely_get_db_credential(BACKEND_FIREBASE_CREDENTIALS))
    except (JSONDecodeError, TypeError) as e:
        junk_creds = True

    try:
        delete_firebase_instance(get_firebase_app())
    except ValueError:
        # occurs when get_firebase_app() fails, delete_firebase_instance is only called if it succeeds.
        pass

    if junk_creds:
        return

    # can now ~safely initialize the firebase app, re-casting any errors for runime scenarios
    # errors at this point should only occur if the app has somehow gotten broken credentials.
    try:
        cert = FirebaseCertificate(encoded_credentials)
    except ValueError as e:
        raise FirebaseMisconfigured(str(e))

    try:
        initialize_firebase_app(cert)
    except ValueError as e:
        # occasionally we do hit a race condition, handle that with 3 tries, comment in error message.
        if rucur_depth >= 0:
            return update_firebase_instance(rucur_depth - 1)
        raise FirebaseMisconfigured(
            "This error is usually caused by a race condition, please report it if this happens frequently: "
            + str(e)
        )


def set_next_weekly(participant: Participant, survey: Survey) -> None:
    ''' Create a next ScheduledEvent for a survey for a particular participant. Uses get_or_create. '''
    schedule_date, schedule = get_next_weekly_event_and_schedule(survey)

    # this handles the case where the schedule was deleted. This is a corner case that shouldn't happen
    if schedule_date is not None and schedule is not None:
        ScheduledEvent.objects.get_or_create(
            survey=survey,
            participant=participant,
            weekly_schedule=schedule,
            relative_schedule=None,
            absolute_schedule=None,
            scheduled_time=schedule_date,
        )


def repopulate_all_survey_scheduled_events(study: Study, participant: Participant = None):
    """ Runs all the survey scheduled event generations on the provided entities. """

    for survey in study.surveys.all():
        # remove any scheduled events on surveys that have been deleted.
        if survey.deleted:
            survey.scheduled_events.all().delete()
            continue

        repopulate_weekly_survey_schedule_events(survey, participant)
        repopulate_absolute_survey_schedule_events(survey, participant)
        # there are some cases where we can logically exclude relative surveys.
        # Don't. Do. That. Just. Run. Everything. Always.
        repopulate_relative_survey_schedule_events(survey, participant)


def repopulate_weekly_survey_schedule_events(survey: Survey, single_participant: Participant = None) -> None:
    """ Clear existing schedules, get participants, bulk create schedules Weekly events are
    calculated in a way that we don't bother checking for survey archives, because they only
    exist in the future. """
    events = survey.scheduled_events.filter(relative_schedule=None, absolute_schedule=None)
    if single_participant:
        events = events.filter(participant=single_participant)
        participant_ids = [single_participant.pk]
    else:
        participant_ids = survey.study.participants.values_list("pk", flat=True)

    events.delete()

    try:
        # get_next_weekly_event forces tz-aware schedule_date datetime object
        schedule_date, schedule = get_next_weekly_event_and_schedule(survey)
    except NoSchedulesException:
        return

    ScheduledEvent.objects.bulk_create(
        [
            ScheduledEvent(
                survey=survey,
                participant_id=participant_id,
                weekly_schedule=schedule,
                relative_schedule=None,
                absolute_schedule=None,
                scheduled_time=schedule_date,
            ) for participant_id in participant_ids
        ]
    )


def repopulate_absolute_survey_schedule_events(survey: Survey, single_participant: Participant = None) -> None:
    """
    Creates new ScheduledEvents for the survey's AbsoluteSchedules while deleting the old
    ScheduledEvents related to the survey
    """
    # if the event is from an absolute schedule, relative and weekly schedules will be None
    events = survey.scheduled_events.filter(relative_schedule=None, weekly_schedule=None)
    if single_participant:
        events = events.filter(participant=single_participant)
    events.delete()

    new_events = []
    for abs_sched in survey.absolute_schedules.all():
        scheduled_time = abs_sched.event_time
        # if one participant
        if single_participant:
            archive_exists = ArchivedEvent.objects.filter(
                survey_archive__survey=survey,
                scheduled_time=scheduled_time,
                participant_id=single_participant.pk
            ).exists()
            relevant_participants = [] if archive_exists else [single_participant.pk]

        # if many participants
        else:
            # don't create events for already sent notifications
            irrelevant_participants = ArchivedEvent.objects.filter(
                survey_archive__survey=survey, scheduled_time=scheduled_time,
            ).values_list("participant_id", flat=True)
            relevant_participants = survey.study.participants.exclude(
                pk__in=irrelevant_participants
            ).values_list("pk", flat=True)

        # populate
        for participant_id in relevant_participants:
            new_events.append(ScheduledEvent(
                survey=survey,
                weekly_schedule=None,
                relative_schedule=None,
                absolute_schedule_id=abs_sched.pk,
                scheduled_time=scheduled_time,
                participant_id=participant_id
            ))
    # instantiate
    ScheduledEvent.objects.bulk_create(new_events)


def repopulate_relative_survey_schedule_events(survey: Survey, single_participant: Participant = None) -> None:
    """ Creates new ScheduledEvents for the survey's RelativeSchedules while deleting the old
    ScheduledEvents related to the survey. """
    # Clear out existing events.
    events = survey.scheduled_events.filter(absolute_schedule=None, weekly_schedule=None)
    if single_participant:
        events = events.filter(participant=single_participant)
    events.delete()

    # This is per schedule, and a participant can't have more than one intervention date per
    # intervention per schedule.  It is also per survey and all we really care about is
    # whether an event ever triggered on that survey.
    new_events = []
    for relative_schedule in survey.relative_schedules.all():
        # only interventions that have been marked (have a date), restrict single user case, get data points.
        interventions_query = relative_schedule.intervention.intervention_dates.exclude(date=None)
        if single_participant:
            interventions_query = interventions_query.filter(participant=single_participant)
        interventions_query = interventions_query.values_list("participant_id", "date")

        for participant_id, intervention_date in interventions_query:
            # + below is correct, 'days_after' is negative or 0 for days before and day of.
            scheduled_date = intervention_date + timedelta(days=relative_schedule.days_after)
            schedule_time = relative_schedule.scheduled_time(scheduled_date, survey.study.timezone)
            # skip if already sent (archived event matching participant, survey, and schedule time)
            if ArchivedEvent.objects.filter(
                participant_id=participant_id,
                survey_archive__survey_id=survey.id,
                scheduled_time=schedule_time,
            ).exists():
                continue

            new_events.append(ScheduledEvent(
                survey=survey,
                participant_id=participant_id,
                weekly_schedule=None,
                relative_schedule=relative_schedule,
                absolute_schedule=None,
                scheduled_time=schedule_time,
            ))

    ScheduledEvent.objects.bulk_create(new_events)


def get_next_weekly_event_and_schedule(survey: Survey) -> (datetime, WeeklySchedule):
    """ Determines the next time for a particular survey, provides the relevant weekly schedule. """
    now = survey.study.now()
    timing_list = []
    # our possible next weekly event may be this week, or next week; get this week if it hasn't
    # happened, next week if it has.  A survey can have many weekly schedules, grab them all.
    for weekly_schedule in survey.weekly_schedules.all():
        this_week, next_week = weekly_schedule.get_prior_and_next_event_times(now)
        timing_list.append((this_week if now < this_week else next_week, weekly_schedule))

    if not timing_list:
        raise NoSchedulesException()

    # get the earliest next schedule_date
    timing_list.sort(key=lambda date_and_schedule: date_and_schedule[0])
    schedule_date, schedule = timing_list[0]
    return schedule_date, schedule
