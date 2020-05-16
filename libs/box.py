import boto3
import Crypto
import boxsdk
from boxsdk.exception import BoxOAuthException, BoxAPIException

from config.constants import DEFAULT_S3_RETRIES, RAW_DATA_FOLDER, KEYS_FOLDER
from config.settings import (BOX_clientID, BOX_clientSecret, BOX_enterpriseID, BOX_registration_callback)
from libs import encryption
from botocore.exceptions import ClientError


def get_registration_url():
    """
    get a registration url to box.com. First part of the Oauth2 3-way handshake that will allow
    the user to give beiwe permission to write data to box.com
    :return: registration url to use
    """

    sdk = boxsdk.OAuth2(
        client_id=BOX_clientID,
        client_secret=BOX_clientSecret
    )

    return sdk.get_authorization_url(BOX_registration_callback)[0]


def box_authenticate(code, box_integration):
    """
    last phase of the Oauth2 3-way handshake to allow the user to give beiwe permission to write
    data to their box.com account

    :param code: code provided by the previous stages of the handshake
    :param box_integration: object that stores the box integration details
    :return:
    """

    sdk = boxsdk.OAuth2(
        client_id=BOX_clientID,
        client_secret=BOX_clientSecret,
        store_tokens=box_integration.store_box_tokens
    )

    return sdk.authenticate(code)


def create_subfolder_path(path, box_integration):
    """
    creates the subfolder path (i.e. nested folders) in
        the root directory
    :param path: the path that should be created in the box directory, some or all of the elements
        of this path may already exist on box
    :param box_integration: object containing credentials for accessing the box.com account
    :return: the path that was created on box.com
    """

    sdk = boxsdk.OAuth2(
        client_id=BOX_clientID,
        client_secret=BOX_clientSecret,
        access_token=box_integration.access_token,
        refresh_token=box_integration.refresh_token,
        store_tokens=box_integration.store_box_tokens
    )

    client = boxsdk.Client(sdk)

    # there doesn't seem to be a good way to query box
    # based on folder names, instead you have to get a list
    # of items and the search for the one you want. instead
    # of doing this, lets just let an exception tell us
    # what we want to know, and fortunately the exception error
    # includes the folder ID for the existing folder, if 
    # it was determined to exist
    subfolder = client.folder('0')
    for path_part in path.lstrip('/').rstrip('/').split('/'):
        try:
            subfolder = subfolder.create_subfolder(path_part)
        except BoxAPIException as e:
            if hasattr(e, 'context_info') and 'conflicts' in e.context_info:
                for conflict in e.context_info['conflicts']:
                    if conflict['name'] == path_part:
                        subfolder = client.folder(conflict['id'])
            else:
                # if the exception is not due to the subfolder already existing,
                # pass it on
                raise
            # otherwise we handled everything, lets keep going
            pass

    return subfolder


def upload_stream_to_subfolder(box_subfolder, stream, target_filename):
    """
    upload data from a stream (e.g. file stream, or bytestream) to a subfolder on box.com

    :param box_subfolder: subfolder on box.com to copy data to
    :param stream: file stream or byte stream to copy data from
    :param target_filename: the name of the file that the data should be written to
    :return: return whatever we receive from the api call
    """

    retval = None
    try:
        retval = box_subfolder.upload_stream(stream, target_filename, preflight_check=True,
                                             upload_using_accelerator=True)
    except BoxAPIException as e:
        print(f'Error writing {target_filename} to box.com: {e.message()}')

    return retval
