aws lambda create-function --function-name beiwe-fitbit-lambda \
                           --zip-file fileb:///home/ubuntu/lambda_deploy.zip \
                           --handler libs.fitbit.do_process_fitbit_records_lambda_handler \
                           --runtime python3.6 \
                           --role arn:aws:iam::476402459683:role/lambda_s3 \
                           --vpc-config SubnetIds=subnet-8f74dfd3,subnet-882ed1b6,subnet-cdcf67aa,subnet-58563f57,SecurityGroupIds=sg-0c07d9ac55e63038e
