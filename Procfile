web: gunicorn -c conf.py openintel.wsgi --log-file -
worker: celery worker --app=openintel.celery.app
