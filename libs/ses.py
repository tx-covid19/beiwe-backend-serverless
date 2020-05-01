import boto3
from config.settings import SYSADMIN_EMAILS
from botocore.exceptions import ClientError


def ses_send_email(message, subject, to_email):
    """
    Use Amazon's simple email service to send an email
    :param message: string including the body of the message
    :param subject: string including the subject of the message
    :param to_email: comma or space separated string or list of addresses for intended recipients of the email
    :return: nada
    """
    email_charset = "UTF-8"

    if ',' in to_email:
        to_email = to_email.split(',')

    if ' ' in to_email:
        to_email = to_email.split(' ')

    if not isinstance(to_email, list):
        to_email = [to_email]

    if not message and not subject:
        raise ValueError('Will not send email with an empty message or subject.')

    if not SYSADMIN_EMAILS:
        raise ValueError('SYSADMIN_EMAILS is not configured')

    sys_admin_emails = SYSADMIN_EMAILS
    if isinstance(sys_admin_emails, list):
            sys_admin_emails = sys_admin_emails[0]

    ses_client = boto3.client('ses', region_name='us-east-1')

    try:
        ses_client.send_email(
            Destination={
                'ToAddresses': to_email,
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': email_charset,
                        'Data': message,
                    },
                },
                'Subject': {
                    'Charset': email_charset,
                    'Data': subject,
                },
            },
            Source=sys_admin_emails,
        )
    except ClientError as e:
        print('Something went wrong sending email...')
        print(e.response['Error']['Message'])
    else:
        print(f'Email(s) sent to {", ".join(to_email)}!')

    return
