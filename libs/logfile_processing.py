import codecs
from database.study_models import SurveyEvents
from config.constants import API_TIME_FORMAT
from datetime import datetime, timedelta
import re

def process_android_log_data(data: dict) -> dict:

    # attach to participant and study
    participant = data['ftp']['participant']
    study = data['ftp']['study']

    file_contents = data['file_contents'].decode()

    print(f'processing app log file for {study.name} {participant.patient_id}')

    for file_line in file_contents.split("\n"):
        line_values = file_line.rstrip().split(",")

        # process header to get a mapping between columns and the values that they contain
        if 'THIS LINE IS A LOG FILE HEADER' in file_line:
            continue
        else:
            match_object = re.search(r'([0-9]{13})\b Received Broadcast: Intent { act=([\w-]{24}\b)', file_line, re.M|re.I)
            if match_object:
                timestamp = match_object.group(1)
                survey_id = match_object.group(2)
                survey  = study.surveys.get(object_id=survey_id)
                 
                if not survey:
                    print(f'found match: {match_object.group(1)} but could not find the corresponding survey')
                else:
                    extracted_timestamp = int(timestamp[0:10])
                    extracted_datetime = datetime.utcfromtimestamp(extracted_timestamp)
                    print(f'found line for survey {survey.id}: {timestamp} {extracted_datetime}')
                    SurveyEvents.register_survey_event(study.id, survey.id, participant.id, extracted_datetime,
                            SurveyEvents.NOTIFIED)


def process_app_log_file(study, participant, survey_dict, file_contents: str) -> dict:
  
    print(f'processing app log file for {study.name} {participant.patient_id}')
    header_map = {}
    survey_results = []
    new_survey_results = {}

    file_contents = file_contents.decode()

    for file_line in file_contents.split("\n"):
        line_values = file_line.rstrip().split(",")

        # process header to get a mapping between columns and the values that they contain
        if 'THIS LINE IS A LOG FILE HEADER' in file_line:
            continue
        else:
            #print(file_line)
            match_object = re.search(r'([0-9]{13})\b Received Broadcast: Intent { act=([\w-]{24}\b)', file_line, re.M|re.I)
            if match_object:
                timestamp = match_object.group(1)
                survey_id = match_object.group(2)

                if survey_id not in survey_dict:
                    print(f'found match: {match_object.group(1)} but could not find the corresponding survey')
                else:
                    extracted_timestamp = int(timestamp[0:10])
                    extracted_datetime = datetime.utcfromtimestamp(extracted_timestamp)
                    print(f'found line for survey {survey_dict[survey_id]}: {timestamp} {extracted_datetime}')
                    SurveyEvents.register_survey_event(study.id, survey_dict[survey_id].id, participant.id, extracted_datetime,
                            SurveyEvents.NOTIFIED)

