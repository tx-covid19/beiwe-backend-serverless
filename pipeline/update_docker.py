"""
A script to update the docker image in AWS. This exists because running docker_script directly
causes import errors.
"""

import pipeline.docker_script as docker_script


if __name__ == '__main__':
    docker_script.run()
