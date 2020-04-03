from config import load_django
import libs.s3 as libs_s3
import re
import csv
import json
import gzip

S3_LOG_BUCKET = 'beiwe-data-ut-wcwh-py3-logs'

bucket_keys = libs_s3._do_list_files(S3_LOG_BUCKET, 'inventory')

all_manifest_dict = {}
for key in bucket_keys:
    search_result = re.search("inventory/(?P<bucket>[\w-]+)/(?P<version_string>[\w-]+)/(?P<timestamp>[\w-]+)/manifest.json", key)
    if search_result:
        all_manifest_dict[key] = search_result.groupdict()

project_s3_file_sizes_dict = {}

for manifest_key, manifest_dict in all_manifest_dict.items():

    bucket_key = '_'.join([manifest_dict['version_string'], manifest_dict['bucket']])

    if bucket_key not in project_s3_file_sizes_dict:
        project_s3_file_sizes_dict[bucket_key] = {}

    if manifest_dict['timestamp'] in project_s3_file_sizes_dict[bucket_key]:
        print(f"Entry for {bucket_key} {manifest_dict['timestamp']} exits, skipping ...")
        continue

    print(f"Processing {bucket_key} {manifest_dict['timestamp']} ...")
    project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']] = {}

    manifest = json.loads(libs_s3._do_retrieve(S3_LOG_BUCKET, manifest_key)['Body'].read())

    file_schema = {}
    array_index = 0
    for value in manifest['fileSchema'].replace(' ','').split(','):
        file_schema[value.lower()] = array_index
        array_index += 1

    print(file_schema)
    inventory_size = 0
    for inventory_file in manifest['files']:

        print(f'downloading and processing {inventory_file}')
        inventory = gzip.decompress(libs_s3._do_retrieve(S3_LOG_BUCKET, inventory_file['key'])['Body'].read())
        for inventory_vals in csv.reader(inventory.decode().splitlines()):
            try:
                if inventory_vals:
                    key_vals = inventory_vals[file_schema['key']].split('/')
                    if key_vals:
                        if key_vals[0] in ['KEYS', 'RAW_DATA', 'CHUNKED_DATA']:
                            directory_type = key_vals[0].lower()
                            project_id = key_vals[1].lower()
                        elif 'keys' in key_vals[1]:
                            directory_type = key_vals[1].lower()
                            project_id = key_vals[0].lower()
                        elif re.match('\w{24}', key_vals[0]):
                            directory_type = 'raw_data'
                            project_id = key_vals[0].lower()
                        else:
                            continue

                        if project_id not in project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']]:
                            project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']][project_id] = {}

                        if directory_type not in project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']][project_id]:
                            project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']][project_id][directory_type] = \
                                    { 'file_count': 0, 'total_size': 0 }

                        project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']][project_id][directory_type]['total_size'] += \
                            int(inventory_vals[file_schema['size']])

                        project_s3_file_sizes_dict[bucket_key][manifest_dict['timestamp']][project_id][directory_type]['file_count'] += 1

            except:

                print(f"error processing {inventory_vals}")
                raise()

for bucket_key in project_s3_file_sizes_dict:
    for timestamp in project_s3_file_sizes_dict[bucket_key]:
        data_rows = []
        for project_id in project_s3_file_sizes_dict[bucket_key][timestamp]:
            for directory_type in project_s3_file_sizes_dict[bucket_key][timestamp][project_id]:
                data_rows.append([bucket_key, timestamp, project_id, directory_type, 
                    project_s3_file_sizes_dict[bucket_key][timestamp][project_id][directory_type]['total_size'],
                    project_s3_file_sizes_dict[bucket_key][timestamp][project_id][directory_type]['file_count']])

        with open(f"{bucket_key}_{timestamp}_s3_sizes.json", 'w') as ofd:
            json.dump(data_rows, ofd, indent=4)

    print(project_s3_file_sizes_dict)
