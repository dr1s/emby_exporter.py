FROM alpine:3.8

RUN apk add --no-cache python3 && \
    pip3 install --upgrade pip setuptools && \
    pip3 install pipenv

WORKDIR /exporter

COPY emby_exporter/emby_exporter.py emby_exporter.py
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock

RUN set -ex && pipenv install --deploy --system

EXPOSE 9123

ENTRYPOINT python3 emby_exporter.py
