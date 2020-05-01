import os
from os.path import abspath, dirname, join, exists as file_exists
from typing import Callable

# stick all errors into this list and raise a special exception at the end.
ERRORS = []

# Config constants. These are constants declared in this file, they are for configuration details.
DB_MODE_POSTGRES = "postgres"
DB_MODE_SQLITE = "sqlite"

# The explicit remote env file should be beiwe-backend/config/remote_db_env.py
CELERY_SERVER_ENV_FILE = join(abspath(dirname(__file__)), "remote_db_env.py")
ELASTIC_BEANSTALK_ENV_FILE = join(abspath(dirname(dirname(dirname(__file__)))), "env")
POSTGRES_DATABASE_SETTINGS = ("RDS_DB_NAME", "RDS_USERNAME", "RDS_PASSWORD", "RDS_HOSTNAME")
SENTRY_ENVS = ('SENTRY_ANDROID_DSN', 'SENTRY_DATA_PROCESSING_DSN', 'SENTRY_ELASTIC_BEANSTALK_DSN',
               'SENTRY_JAVASCRIPT_DSN')

# server modes
MODE_EB_SERVER = file_exists(ELASTIC_BEANSTALK_ENV_FILE)
MODE_CELERY_SERVER = file_exists(CELERY_SERVER_ENV_FILE)

# Evaluate the config.remote_db_env file if it exists.  This file is auto generated during the
# deploy process and populates the environment variables.
if MODE_CELERY_SERVER:
    import config.remote_db_env

# determine database
if MODE_CELERY_SERVER or MODE_EB_SERVER:
    DB_MODE = DB_MODE_POSTGRES
    # If you are running with a remote database (e.g. on a server in a beiwe cluster) you need
    # some extra environment variables to be set.
    for env_var in POSTGRES_DATABASE_SETTINGS:
        if env_var not in os.environ:
            ERRORS.append(f"Environment variable '{env_var}' was not found.")
else:
    # if you are not running on an elastic beanstalk server or a celery assume that this is a
    # development/local environment and use a sqlite database
    DB_MODE = DB_MODE_SQLITE


####################################################################################################
#### Start introspecting to validate parameters and inform user of missing required parameters. ####
####################################################################################################

from config import settings
PROVIDED_SETTINGS = vars(settings)

# Check that all values provided actually contain something
for env_setting_name, env_setting_value in PROVIDED_SETTINGS.items():
    if env_setting_name.startswith("_") or isinstance(env_setting_value, Callable) or env_setting_name in SENTRY_ENVS:
        continue
    if not env_setting_value:
        ERRORS.append(f"The setting '{env_setting_name}' was not provided with a value.")

# these variables are strictly required.
MANDATORY_VARS = {
    'DOMAIN_NAME',
    'FLASK_SECRET_KEY',
    'IS_STAGING',
    'S3_BUCKET',
    'SYSADMIN_EMAILS',
}

# this might be useful in the future
# SENTRY_PRESENT = sum(1 for sentry_env in SENTRY_ENVS if sentry_env in PROVIDED_SETTINGS)

# Check that all the mandatory variables exist...
for mandatory_var in MANDATORY_VARS:
    if mandatory_var not in PROVIDED_SETTINGS:
        ERRORS.append(f"'{mandatory_var}' was not provided in your settings.")

# Environment variable type can be unpredictable, sanitize the numerical ones.
settings.CONCURRENT_NETWORK_OPS = int(settings.CONCURRENT_NETWORK_OPS)
settings.FILE_PROCESS_PAGE_SIZE = int(settings.FILE_PROCESS_PAGE_SIZE)

# email addresses are parsed from a comma separated list, strip whitespace.
if settings.SYSADMIN_EMAILS:
    settings.SYSADMIN_EMAILS = [
        _email_address.strip() for _email_address in settings.SYSADMIN_EMAILS.split(",")
    ]

# IS_STAGING needs to resolve to False except under specific settings.
# The default needs to be production.
settings.IS_STAGING = True if settings.IS_STAGING is True or settings.IS_STAGING.upper() == "TRUE" else False

#
# Stick any warning about environment variables that may have changed here
#
old_credentials_warning = \
"WARNING: This runtime environment is be using the out-of-date environment variable '%s', " \
"please change it to the new environment variable '%s'. (The system will continue to work " \
"with the old environment variable).\n"

pipeline_warning = \
"(Due to the condition below you may need to update the access credentials in order to use " \
"the Data Pipeline feature of Beiwe.)"

if os.getenv("S3_ACCESS_CREDENTIALS_USER") and not os.getenv("BEIWE_SERVER_AWS_ACCESS_KEY_ID"):
    print(pipeline_warning)
    print(old_credentials_warning % ("S3_ACCESS_CREDENTIALS_USER", "BEIWE_SERVER_AWS_ACCESS_KEY_ID"))
    

if os.getenv("S3_ACCESS_CREDENTIALS_KEY") and not os.getenv("BEIWE_SERVER_AWS_SECRET_ACCESS_KEY"):
    print(pipeline_warning)
    print(old_credentials_warning % ("S3_ACCESS_CREDENTIALS_KEY", "BEIWE_SERVER_AWS_SECRET_ACCESS_KEY"))

#
# print a useful error and cease execution if any required environment variables showed up.
if ERRORS:
    class BadServerConfigurationError(Exception): pass
    raise BadServerConfigurationError("\n" + "\n".join(sorted(ERRORS)))
