# How to contribute

We appreciate all pull requests. However, before working on an enhancement/feature, you should search to see if there's 
already a discussion on the [Issue Tracker](https://github.com/twschiller/open-synthesis/issues). If not, you should 
[start a new discussion](https://github.com/twschiller/open-synthesis/issues/new).

## Local Development

To perform local development, you'll need Python 3.5 and [pip](https://pip.pypa.io/en/stable/installing/).
For deployment, you'll also want the [Heroku Toolbelt](https://devcenter.heroku.com/articles/getting-started-with-python#introduction).

Create a virtual environment for the application, creating a project-specific Python package environment:

    virtualenv venv

Switch to the virtualenv. On Windows, run this command:

    venv\Scripts\activate.bat
    
On Mac/Linux, run this command:

    source venv/bin/activate

Install the project requirements:

    pip install -r requirements.txt

Create a local environment configuration by copying the defaults in `env.sample`:

    cp env.sample .env
    
Package the static files for the project:
    
    python manage.py collectstatic
 
Run the test suite the ensure your environment is properly configured:

    python manage.py test

Create the database schema, and load the initial application data:

    python manage.py migrate
    python manage.py loaddata source_tags 
    
Serve the Django application using [Gunicorn](http://gunicorn.org/):

    gunicorn -c conf.py openintel.wsgi --log-file -
    
If you are using Heroku, you can run the project with:    
    
    heroku local web
    
## Code Style

Python contributions should follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines, with the
following modifications:

- Maximum line length is 119 characters.

The `pep8` configuration for the project is maintained in the [tox.ini](tox.ini) file.

## Testing

New code should include tests that:

- Exercise each new line of code
- Have a reasonable set of test oracles (assertions) to determine whether or not the test passed
- If you use `#pragma: no cover`, you should include a comment explaining why the code should be excluded from coverage
reporting.

The code coverage configuration is maintained in the [.coveragerc](.coveragerc) file.

# Acknowledgements

We gratefully acknowledge this project's [3rd-party libraries and their contributors](requirements.txt). Additionally, 
we'd like to acknowledge the following:

* SSL/TLS certificate generated with [Let's Encrypt](https://letsencrypt.org/)
* Project hosting provided by [GitHub](https://github.com)
* Continuous Integration provided by [Travis CI](https://travis-ci.org/)
* Code Coverage Reporting provided by [Coveralls](https://coveralls.io/)
* Code Lint Reporting provided by [Code Climate](https://codeclimate.com/)
* FavIcon designed by [Freepik](http://www.freepik.com) from [Flaticon](http://www.flaticon.com)
and licensed by [Creative Commons BY 3.0](http://creativecommons.org/licenses/by/3.0/).
