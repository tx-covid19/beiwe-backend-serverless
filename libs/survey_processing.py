import codecs
from database.study_models import Survey, SurveyEvents
from config.constants import API_TIME_FORMAT
from datetime import datetime, timedelta

#mapping timestamp to 0
#mapping UTC time to 1
#mapping question id to 2
#mapping survey id to 3
#mapping question type to 4
#mapping question text to 5
#mapping question answer options to 6
#mapping answer to 7
#mapping event to 8

def resolve_survey_id_from_file_name(name: str) -> str:
    return name.rsplit("/", 2)[1]

def process_survey_timings_data(data: dict) -> dict:

    print(data.keys())

    # attach to participant and study
    participant = data['ftp']['participant']
    study = data['ftp']['study']

    # find the survey corresponding to the content
    survey = Survey.objects.get(object_id=resolve_survey_id_from_file_name(data['ftp']['s3_file_path'])) 
    
    file_contents = data['file_contents'].decode()

    header_map = {}

    for file_line in file_contents.split("\n"):
        line_values = file_line.rstrip().split(",")

        # process header to get a mapping between columns and the values that they contain
        if 'timestamp' in file_line:

            if header_map:
                raise ValueError('Header line found even though header mapping has already been made')

            for column_index, variable_name in enumerate(line_values):
                if variable_name in header_map:
                    raise ValueError(f'{variable_name} already mapped to {head_map[variable_name]}, but also occurs at {column_index}')
                header_map[variable_name] = column_index

            if 'event' not in header_map:
                header_map['event'] = header_map['question id']

        elif header_map:

            if line_values[header_map["event"]] == SurveyEvents.ANDROID_COMPLETED:
                line_values[header_map["event"]] = SurveyEvents.COMPLETED

            if line_values[header_map["event"]] in [SurveyEvents.NOTIFIED, SurveyEvents.EXPIRED, SurveyEvents.COMPLETED]:
                extracted_timestamp = int(line_values[header_map["timestamp"]][0:10])
                extracted_datetime = datetime.utcfromtimestamp(extracted_timestamp)
                SurveyEvents.register_survey_event(study.id, survey.id, participant.id, extracted_datetime,
                    line_values[header_map["event"]])
                print(f'registered event {line_values[header_map["timestamp"]]} {line_values[header_map["event"]]}')

        else:
            print(f'error did not find mapping')


def process_survey_timings_file(study, participant, survey, file_contents: str) -> dict:
  
    #print(f'processing survey timings file for {study.name} {participant.patient_id} {survey.object_id}')
    header_map = {}

    file_contents = file_contents.decode()

    for file_line in file_contents.split("\n"):
        line_values = file_line.rstrip().split(",")

        # process header to get a mapping between columns and the values that they contain
        if 'timestamp' in file_line:

            if header_map:
                raise ValueError('Header line found even though header mapping has already been made')

            for column_index, variable_name in enumerate(line_values):
                if variable_name in header_map:
                    raise ValueError(f'{variable_name} already mapped to {head_map[variable_name]}, but also occurs at {column_index}')
                header_map[variable_name] = column_index

            if 'event' not in header_map:
                header_map['event'] = header_map['question id']

        elif header_map:

            if line_values[header_map["event"]] == SurveyEvents.ANDROID_COMPLETED:
                line_values[header_map["event"]] = SurveyEvents.COMPLETED

            if line_values[header_map["event"]] in [SurveyEvents.NOTIFIED, SurveyEvents.EXPIRED, SurveyEvents.COMPLETED]:
                extracted_timestamp = int(line_values[header_map["timestamp"]][0:10])
                extracted_datetime = datetime.utcfromtimestamp(extracted_timestamp)
                SurveyEvents.register_survey_event(study.id, survey.id, participant.id, extracted_datetime,
                    line_values[header_map["event"]])
                print(f'registered event {line_values[header_map["timestamp"]]} {line_values[header_map["event"]]}')

        else:
            print(f'error did not find mapping')
