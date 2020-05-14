import boto3


def create_or_update_event(event_rule_name, cron_expr, target_id, target_arn, msg=''):
    events_client = boto3.client('events')
    try:
        events_client.put_rule(Name=event_rule_name, ScheduleExpression='cron({})'.format(cron_expr))
        response = events_client.put_targets(Rule=event_rule_name,
                                             Targets=[{
                                                 'Id': target_id,
                                                 'Arn': target_arn,
                                                 'Input': msg,
                                             }])
        if response['FailedEntryCount'] != 0:
            return False

        return True

    except:
        raise