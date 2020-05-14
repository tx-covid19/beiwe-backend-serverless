FROM python:3.8-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y libpq-dev gcc git

COPY ./requirements.txt /code/requirements.txt
RUN pip install -r /code/requirements.txt

COPY ./requirements_data_processing.txt /code/requirements_data_processing.txt
RUN pip install -r /code/requirements_data_processing.txt

WORKDIR /code