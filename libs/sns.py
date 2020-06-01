import boto3


def create_topic(applet_id, activity_id):
    client = boto3.client('sns')
    topic_name = 'mindlogger-applet-{}-activity-{}'.format(applet_id, activity_id)
    try:
        response = client.create_topic(Name=topic_name)
        return response['TopicArn']
    except:
        return None


def delete_topic(topic_arn):
    client = boto3.client('sns')
    try:
        client.delete_topic(TopicArn=topic_arn)
        return True
    except:
        return False


def create_user_endpoint(platform_arn, device_token):
    client = boto3.client('sns')
    try:
        response = client.create_platform_endpoint(
            PlatformApplicationArn=platform_arn,
            Token=device_token
        )
        return response['EndpointArn']
    except:
        return None


def delete_user_endpoint(endpoint_arn):
    client = boto3.client('sns')
    try:
        client.delete_endpoint(EndpointArn=endpoint_arn)
        return True
    except:
        return False


def subscribe_to_topic(topic_arn, endpoint_arn):
    client = boto3.client('sns')
    try:
        response = client.subscribe(
            TopicArn=topic_arn,
            Protocol='application',
            Endpoint=endpoint_arn
        )
        return response['SubscriptionArn']
    except:
        return None


def unsubscribe_topic(subscription_arn):
    client = boto3.client('sns')
    try:
        client.unsubscribe(
            SubscriptionArn=subscription_arn
        )
        return True
    except:
        return False
