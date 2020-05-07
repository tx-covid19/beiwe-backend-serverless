#!/bin/bash

cwd=$PWD

if [ "$1" == "" ]; then
    echo "Usage: $0 <zip file to deploy>" 
    exit
fi

if [ ! -f "$1" ]; then
    echo "File $1 does not exist"
    exit
fi

zip_file_path=$(readlink -f $1)

echo "Updating lambda with ${zip_file_path}"

aws lambda update-function-code \
                  --function-name beiwe-chunker-lambda \
		  --zip-file fileb://${zip_file_path} \
                  --publish
