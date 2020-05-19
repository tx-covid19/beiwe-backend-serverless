#!/bin/bash

cwd=$PWD

S3_BUCKET_NAME="beiwe-backend-serverless"

if [ "$1" == "" ]; then
    echo "Usage: $0 <zip file to deploy>" 
    exit
fi

if [ ! -f "$1" ]; then
    echo "File $1 does not exist"
    exit
fi

S3_KEY_NAME=$(basename ${1})

aws s3 cp $1 s3://${S3_BUCKET_NAME}/${S3_KEY_NAME}

aws lambda update-function-code \
                  --function-name beiwe-fitbit-lambda \
                  --s3-bucket "${S3_BUCKET_NAME}" \
                  --s3-key "${S3_KEY_NAME}" \
                  --publish
