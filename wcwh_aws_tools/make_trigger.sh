aws lambda create-function --function-name beiwe-chunker-lambda \
                           --zip-file fileb:///home/ubuntu/lambda_deploy.zip \
                           --handler libs.file_processing.do_process_user_file_chunks_lambda_handler \
                           --runtime python3.6 \
                           --role arn:aws:iam::476402459683:role/lambda_s3 \
                           --vpc-config SubnetIds=subnet-8f74dfd3,subnet-882ed1b6,subnet-cdcf67aa,subnet-58563f57,SecurityGroupIds=sg-0c07d9ac55e63038e

aws lambda add-permission --function-name beiwe-chunker-lambda \
                          --statement-id 22  \
                          --action "lambda:InvokeFunction" \
                          --principal s3.amazonaws.com \
                          --source-arn arn:aws:s3:::beiwe-data-ut-wcwh-py3

aws s3api put-bucket-notification-configuration --notification-configuration file://s3_trigger_configuration.json \
                                                --bucket beiwe-data-ut-wcwh-py3
