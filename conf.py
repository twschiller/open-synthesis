"""Configuration for the gunicorn server.

For more information, please see:
    http://docs.gunicorn.org/en/stable/configure.html#configuration-file
"""
import gunicorn

gunicorn.SERVER_SOFTWARE = "gunicorn"
