FROM dr1s/pipenv-alpine:3.8-python3.7

COPY emby_exporter/emby_exporter.py emby_exporter.py

EXPOSE 9123

ENTRYPOINT python3 emby_exporter.py
