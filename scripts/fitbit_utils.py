import argparse
import os

import config.load_django
from database.fitbit_models import FitbitCredentials
from database.user_models import Participant
from libs.fitbit import (delete_fitbit_records_trigger, get_fitbit_client,
                         get_fitbit_record)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Beiwe Fitbit tool")

    parser.add_argument(
        'participant_id',
        help='Participant id number (integer greater than 0).',
        type=int
    )

    parser.add_argument(
        'patient_id',
        help='Patient id number (string with 8 characters).',
        type=str
    )

    args = parser.parse_args()
