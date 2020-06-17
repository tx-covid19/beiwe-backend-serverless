from os.path import abspath as _abspath
from sys import path as _path
_one_folder_up = _abspath(__file__).rsplit('/', 2)[0]
_path.insert(1, _one_folder_up)

import argparse
import os
import sys

import config.load_django
from database.user_models import Participant
from database.fitbit_models import (
    FitbitCredentials,
    FitbitInfo,
    FitbitRecord,
    FitbitIntradayRecord
)
from libs.fitbit import (
    create_fitbit_records_trigger,
    delete_fitbit_records_trigger,
    do_process_fitbit_records_lambda_handler,
    trigger_process_fitbit_records
)

def confirm(message):
    answer = ""
    while answer not in ["Y", "n"]:
        answer = input(f"{message} [Y/n]")
    return answer == "Y"

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Beiwe Fitbit tool")

    parser.add_argument(
        '--participant_id',
        help='Participant id number (integer greater than 0).',
        type=int
    )

    parser.add_argument(
        '--patient_id',
        help='Patient id number (string with 8 characters).',
        type=str
    )

    parser.add_argument('action', type=str, choices=[
        'list',
        'sync',
        'delete_credential',
        'wipe_credential',
        'recreate_trigger',
        'delete_trigger'
    ])

    args = parser.parse_args()

    if args.action == 'list':
        print(f"Participant patient_ids with Fitbit integration:")
        for participant in FitbitCredentials.objects.all().values('participant').values('participant'):
            print('- ' + Participant.objects.get(pk=participant['participant']).patient_id)

        sys.exit(0)

    elif args.action == 'recreate_trigger_all':
        for credential in FitbitCredentials.objects.all():
            create_fitbit_records_trigger(credential)

    if args.participant_id and args.patient_id:
        print("Please provide just one of them: participant_id or patient_id")

    if args.participant_id:
        participant = Participant.objects.filter(id=args.participant_id).get()
    if args.patient_id:
        participant = Participant.objects.filter(patient_id=args.patient_id).get()

    try:
        credential = FitbitCredentials.objects.filter(participant=participant).get()
    except:
        print(f"The participant '{participant.patient_id}' does not have a Fitbit credential")

    if args.action == 'sync':

        print(f"Fetching Fitbit data from '{participant.patient_id}'...")

        do_process_fitbit_records_lambda_handler(
            event={"credential": credential.id},
            context=None
        )

    elif args.action == 'sync_lambda':

        print(f"Invoking Fitbit lambda for '{participant.patient_id}'...")

        trigger_process_fitbit_records(credential)

    elif args.action == 'delete_credential':
        if confirm(f"Do you confirm you want to delete the Fitbit credential for '{participant.patient_id}'?"):
            credential.delete()

    elif args.action == 'wipe_credential':
        if confirm(f"Do you confirm you want to wipe the Fitbit credential for '{participant.patient_id}'? "
                    "It will erase all the recorded data, except the credential."):

            FitbitInfo.objects.filter(participant=participant)
            FitbitRecord.objects.filter(participant=participant)
            FitbitIntradayRecord.objects.filter(participant=participant)

    elif args.action == 'recreate_trigger':
        create_fitbit_records_trigger(credential)

    elif args.action == 'delete_trigger':
        delete_fitbit_records_trigger(credential)


