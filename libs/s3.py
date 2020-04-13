import boto3
import Crypto

from config.constants import DEFAULT_S3_RETRIES, RAW_DATA_FOLDER, KEYS_FOLDER
# from config.settings import (BEIWE_SERVER_AWS_ACCESS_KEY_ID, BEIWE_SERVER_AWS_SECRET_ACCESS_KEY,
#     S3_BUCKET, S3_REGION_NAME)
from libs import encryption
from botocore.exceptions import ClientError

class S3VersionException(Exception): pass

# conn = boto3.client('s3',
#                     aws_access_key_id=BEIWE_SERVER_AWS_ACCESS_KEY_ID,
#                     aws_secret_access_key=BEIWE_SERVER_AWS_SECRET_ACCESS_KEY,
#                     region_name=S3_REGION_NAME)


def s3_exists(key_path: str, study_object_id: str, raw_path=False) -> bool:
    """ Takes an S3 file path (key_path), and a study ID.  Takes an optional argument, raw_path,
    which defaults to false.  When set to false the path is prepended to place the file in the
    appropriate study_id folder. The function then checks to see if the key_path exists, and
    returning True if it does, and False otherwise"""
    # if not raw_path:
    #     key_path = '/'.join([RAW_DATA_FOLDER, study_object_id, key_path])
    # try:
    #     conn.head_object(Bucket=S3_BUCKET, Key=key_path)
    # except ClientError:
    #     return False
    return True

def s3_upload(key_path: str, data_string: bytes, study_object_id: str, raw_path=False) -> None:
    # if not raw_path:
    #     key_path = '/'.join([RAW_DATA_FOLDER, study_object_id, key_path])
    # data = encryption.encrypt_for_server(data_string, study_object_id)
    # conn.put_object(Body=data, Bucket=S3_BUCKET, Key=key_path)#, ContentType='string')
    pass


def s3_move(source_key_path, destination_key_path):
    """
    move a s3 object from source_key_path to destination_key_path, unlike other
    functions in this library, it doesn't automatically add anything to the paths."""
    pass
    # try:
    #     conn.copy_object(CopySource={'Bucket': S3_BUCKET, 'Key': source_key_path},
    #                      Bucket=S3_BUCKET, Key=destination_key_path)
    # except:
    #     print('Could not copy key {0} {1}'.format(S3_BUCKET, source_key_path))
    #     raise
    #
    # conn.delete_object(Bucket=S3_BUCKET, Key=source_key_path)


def s3_retrieve(key_path, study_object_id, raw_path=False, number_retries=DEFAULT_S3_RETRIES) -> bytes:
    """ Takes an S3 file path (key_path), and a study ID.  Takes an optional argument, raw_path,
    which defaults to false.  When set to false the path is prepended to place the file in the
    # appropriate study_id folder. """
    # if not raw_path:
    #     key_path = '/'.join([RAW_DATA_FOLDER, study_object_id, key_path])
    # encrypted_data = _do_retrieve(S3_BUCKET, key_path, number_retries=number_retries)['Body'].read()
    # return encryption.decrypt_server(encrypted_data, study_object_id)
    return b'123'


def _do_retrieve(bucket_name, key_path, number_retries=DEFAULT_S3_RETRIES):
    """ Run-logic to do a data retrieval for a file in an S3 bucket."""
    try:
        return conn.get_object(Bucket=bucket_name, Key=key_path, ResponseContentType='string')
    except Exception:
        if number_retries > 0:
            print("s3_retrieve failed, retrying on %s" % key_path)
            return _do_retrieve(bucket_name, key_path, number_retries=number_retries - 1)
        
        raise


def s3_list_files(prefix, as_generator=False):
    """ Method fetches a list of filenames with prefix.
        note: entering the empty string into this search without later calling
        the object results in a truncated/paginated view."""
    # return _do_list_files(S3_BUCKET, prefix, as_generator=as_generator)
    return []

def s3_list_versions(prefix, allow_multiple_matches=False):
    """
    Page structure - each page is a dictionary with these keys:
     Name, ResponseMetadata, Versions, MaxKeys, Prefix, KeyMarker, IsTruncated, VersionIdMarker
    We only care about 'Versions', which is a list of all object versions matching that prefix.
    Versions is a list of dictionaries with these keys:
     LastModified, VersionId, ETag, StorageClass, Key, Owner, IsLatest, Size

    returns a list of dictionaries.
    If allow_multiple_matches is False the keys are LastModified, VersionId, IsLatest.
    If allow_multiple_matches is True the key 'Key' is added, containing the s3 file path.
    """

    paginator = conn.get_paginator('list_object_versions')
    page_iterator = paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix)

    versions = []
    for page in page_iterator:
        # versions are not guaranteed, usually this means the file was deleted and only has deletion markers.
        if 'Versions' not in page:
            continue

        for s3_version in page['Versions']:
            if not allow_multiple_matches and s3_version['Key'] != prefix:
                raise S3VersionException("the prefix '%s' was not an exact match" % prefix)
            versions.append({
                'VersionId': s3_version["VersionId"],
                'Key': s3_version['Key'],
            })
    return versions


def _do_list_files(bucket_name, prefix, as_generator=False):
    paginator = conn.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    if as_generator:
        return _do_list_files_generator(page_iterator)
    else:
        items = []
        for page in page_iterator:
            if 'Contents' in page:
                for item in page['Contents']:
                    items.append(item['Key'].strip("/"))
        return items


def _do_list_files_generator(page_iterator):
    for page in page_iterator:
        if 'Contents' not in page:
            return
        for item in page['Contents']:
            yield item['Key'].strip("/")


def s3_delete(key_path):
    raise Exception("NO DONT DELETE")


def delete_versions(files_to_delete):
    print(f"Deleting many files, this could take a while... ")
    for s3_file_path in files_to_delete:
        file_args = s3_list_versions(s3_file_path)

        print(
            "Deleting %s version(s) of %s with the following VersionIds: %s" %
            (len(file_args), s3_file_path, ", ".join([f['VersionId'] for f in file_args]) )
        )

        delete_args = {
            "Bucket": S3_BUCKET,
            "Delete": {
                'Objects': file_args,
                'Quiet': False,
            },
        }

        conn.delete_objects(**delete_args)


################################################################################
######################### Client Key Management ################################
################################################################################

def check_for_client_key_pair(patient_id, study_id):
    """Generate key pairing, push to database, return sanitized key for client."""
    return s3_exists('/'.join([KEYS_FOLDER, study_id, patient_id + "_private"]), study_id, raw_path=True) and \
        s3_exists('/'.join([KEYS_FOLDER, study_id, patient_id + "_public"]), study_id, raw_path=True)


def create_client_key_pair(patient_id, study_id):
    """Generate key pairing, push to database, return sanitized key for client."""
    public, private = encryption.generate_key_pairing()
    s3_upload('/'.join([KEYS_FOLDER, study_id, patient_id + "_private"]), private, study_id, raw_path=True)
    s3_upload('/'.join([KEYS_FOLDER, study_id, patient_id + "_public"]), public, study_id, raw_path=True)


def get_client_public_key_string(patient_id, study_id) -> str:
    """Grabs a user's public key string from s3."""
    key_string = s3_retrieve('/'.join([KEYS_FOLDER, study_id, patient_id + "_public"]), study_id, raw_path=True)
    return encryption.prepare_X509_key_for_java(key_string).decode()


def get_client_public_key(patient_id, study_id):
    """Grabs a user's public key file from s3."""
    key = s3_retrieve('/'.join([KEYS_FOLDER, study_id, patient_id + "_public"]), study_id, raw_path=True)
    return encryption.get_RSA_cipher(key)


def get_client_private_key(patient_id, study_id):
    """Grabs a user's private key file from s3."""
    key = s3_retrieve('/'.join([KEYS_FOLDER, study_id, patient_id + "_private"]), study_id, raw_path=True)
    return encryption.get_RSA_cipher(key)
