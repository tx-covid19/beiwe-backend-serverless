# This file needs to populate all the other models in order for django to identify that it has
# all the models
from collections import Counter

from .common_models import *
from .study_models import *
from .user_models import *
from .profiling_models import *
from .data_access_models import *
from .system_integrations import *
from .pipeline_models import *
from .event_models import *
from .info_models import *
from .tracker_models import *
from .userinfo_models import *
from .redcap_models import *
from .fitbit_models import *
from .mindlogger_models import *
from .info_models import *
from .gps_models import *
from .notification_models import *


def get_and_summarize(patient_id: str):
    p = Participant.objects.get(patient_id=patient_id)
    byte_sum = sum(UploadTracking.objects.filter(participant=p).values_list("file_size", flat=True))
    print(f"Total Data Uploaded: {byte_sum/1024/1024}MB")

    counter = Counter(
        path.split("/")[3] for path in
        FileToProcess.objects.filter(participant=p).values_list("s3_file_path", flat=True)
    )
    return counter.most_common()


