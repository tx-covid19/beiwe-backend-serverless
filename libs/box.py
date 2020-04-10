import boto3
import Crypto
import boxsdk
from boxsdk.exception import BoxOAuthException, BoxAPIException

from config.constants import DEFAULT_S3_RETRIES, RAW_DATA_FOLDER, KEYS_FOLDER
from config.settings import (BOX_clientID, BOX_clientSecret, BOX_enterpriseID, BOX_registration_callback)
from libs import encryption
from botocore.exceptions import ClientError


def get_registration_url(username):
    """ get a regstration url to box.com. First part of the Oauth 3-way handshake
    that will allow the user to give beiwe permssion to write data to box.com. """
    sdk = boxsdk.OAuth2(
        client_id=BOX_clientID,
        client_secret=BOX_clientSecret
    )
    #return sdk.get_authorization_url(BOX_registration_callback + username)[0]
    return sdk.get_authorization_url(BOX_registration_callback)[0]

def box_authenticate(code, box_integration):
    """ retrieves access and refresh tokens and saves them
    to the box_integration object """

    sdk = boxsdk.OAuth2(
        client_id=BOX_clientID,
        client_secret=BOX_clientSecret,
        store_tokens=box_integration.store_box_tokens
    )

    return sdk.authenticate(code)

def create_subfolder_path(path, box_integration):
    """ creates the subfolder path (i.e. nested folders) in
        the root directory """

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
    # what we want to know, and fortunately the excpetion error
    # includes the folder ID for the existing folder, if 
    # it was determined to exist
    subfolder = client.folder('0')
    for path_part in path.lstrip('/').rstrip('/').split('/'):
        try:
            subfolder=subfolder.create_subfolder(path_part)
        except BoxAPIException as e:
            if hasattr(e, 'context_info') and 'conflicts' in e.context_info:
                for conflict in e.context_info['conflicts']:
                    if conflict['name'] == path_part:
                        subfolder=client.folder(conflict['id'])
            else:
                raise
            pass
    return subfolder

def upload_stream_to_subfolder(box_subfolder, stream, target_filename):
    """ upload stream data to a box subfolder, box_subfolder is an object
    not a string """

    return box_subfolder.upload_stream(stream, target_filename, preflight_check=True,
            upload_using_accelerator=True)

