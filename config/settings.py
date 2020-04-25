from os import getenv

"""
To customize any of these values, append a line to config/remote_db_env.py such as:
os.environ['S3_BUCKET'] = 'bucket_name'
"""

BEIWE_SERVER_AWS_ACCESS_KEY_ID = getenv("BEIWE_SERVER_AWS_ACCESS_KEY_ID") or getenv("S3_ACCESS_CREDENTIALS_USER")
BEIWE_SERVER_AWS_SECRET_ACCESS_KEY = getenv("BEIWE_SERVER_AWS_SECRET_ACCESS_KEY") or getenv("S3_ACCESS_CREDENTIALS_KEY")

# This is the secret key for the website. Mostly it is used to sign cookies. You should provide a
#  cryptographically secure string to this value.
FLASK_SECRET_KEY = getenv("FLASK_SECRET_KEY")

# the name of the s3 bucket that will be used to store user generated data, and backups of local
# database information.
S3_BUCKET = getenv("S3_BUCKET")

# Domain name for the server
DOMAIN_NAME = getenv("DOMAIN_NAME")

# A list of email addresses that will receive error emails. This value must be a
# comma separated list; whitespace before and after addresses will be stripped.
SYSADMIN_EMAILS = getenv("SYSADMIN_EMAILS")

# Sentry DSNs
SENTRY_ANDROID_DSN = getenv("SENTRY_ANDROID_DSN")
SENTRY_DATA_PROCESSING_DSN = getenv("SENTRY_DATA_PROCESSING_DSN")
SENTRY_ELASTIC_BEANSTALK_DSN = getenv("SENTRY_ELASTIC_BEANSTALK_DSN")
SENTRY_JAVASCRIPT_DSN = getenv("SENTRY_JAVASCRIPT_DSN")

# Production/Staging: set to "TRUE" if staging
IS_STAGING = getenv("IS_STAGING") or "PRODUCTION"
IS_SERVERLESS = getenv("IS_SERVERLESS") == "TRUE"

# S3 region (not all regions have S3, so this value may need to be specified)
S3_REGION_NAME = getenv("S3_REGION_NAME", "us-east-1")

# Location of the downloadable Android APK file that'll be served from /download
DOWNLOADABLE_APK_URL = getenv("DOWNLOADABLE_APK_URL", "https://s3.amazonaws.com/beiwe-app-backups/release/Beiwe-2.4.1-onnelaLabServer-release.apk")

# Redcap credentials
REDCAP_SERVER_URL = getenv('REDCAP_SERVER_URL')
REDCAP_API_TOKEN = getenv('REDCAP_API_TOKEN')
