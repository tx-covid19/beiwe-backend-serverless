# This file needs to populate all the other models in order for django to identify that it has
# all the models
from collections import Counter

from .common_models import *
from .study_models import *
from .user_models import *
from .profiling_models import *
from .data_access_models import *
from .applet_model import *
from .info_models import *


def get_and_summarize(patient_id: str):
    p = Participant.objects.get(patient_id=patient_id)
    byte_sum = sum(UploadTracking.objects.filter(participant=p).values_list("file_size", flat=True))
    print(f"Total Data Uploaded: {byte_sum/1024/1024}MB")

    counter = Counter(
        path.split("/")[3] for path in
        FileToProcess.objects.filter(participant=p).values_list("s3_file_path", flat=True)
    )
    return counter.most_common()



def watch_files_to_process():
    prior_users = []
    for i in range(2**64):
        now_dt = timezone.now()
        now = now_dt.isoformat()
        count = FileToProcess.objects.count()
        user_count = FileToProcess.objects.values_list("participant__patient_id",
                                                       flat=True).distinct().count()
        if prior_users != user_count:
            print(f"{now:} Number of participants with files to process: {user_count}")

        print(f"{now}: {count} files to process")

        if i % 8 == 0:
            first = FileProcessLock.objects.first()
            if first:
                duration = (now_dt - first.lock_time).total_seconds() / 3600
                print(f"{now}: processing has been running for {duration} hours.")
            else:
                print("processing does not appear to be active. (naive check)")
        sleep(4)
        prior_users = user_count


def watch_uploads():
    while True:
        start = timezone.now()
        data = list(UploadTracking.objects.filter(
            timestamp__gte=(start - timedelta(minutes=1))).values_list("file_size", flat=True))
        end = timezone.now()
        total = abs((start - end).total_seconds())

        # we will set a minimum time between prints at 2 seconds, database call can be slow.
        wait = 2 - total if 0 < (2 - total) < 2 else 0

        print("time delta: %ss, %s files, %.4fMB in the past minute" % (
            total + wait, len(data), (sum(data) / 1024.0 / 1024.0)))
        sleep(wait)
