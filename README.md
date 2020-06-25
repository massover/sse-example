# sse example

poetry install

poetry run gunicorn wsgi:application --workers 1
poetry run uvicorn asgi:application --workers 1