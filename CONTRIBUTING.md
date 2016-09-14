# How to contribute

We appreciate all pull requests. However, before working on an enhancement/feature, you should search to see if there's 
already a discussion on the [Issue Tracker](https://github.com/twschiller/open-synthesis/issues). If not, you should 
[start a new discussion](https://github.com/twschiller/open-synthesis/issues/new).

## Local Development

To perform local development, you'll need Python 3.5, [pip](https://pip.pypa.io/en/stable/installing/),
and [virtualenv](https://virtualenv.pypa.io/en/stable/), [node](https://nodejs.org/en/download/package-manager/), and 
[npm](https://www.npmjs.com/). To create your own deployment, you may also want
the [Heroku Toolbelt](https://devcenter.heroku.com/articles/getting-started-with-python#introduction).

Clone the repository and switch to the project directory:

    git clone https://github.com/twschiller/open-synthesis.git
    cd open-synthesis

Create a project-specific package environment using virtualenv:

    virtualenv venv

Switch to the virtualenv. On Windows, run this command:

    venv\Scripts\activate.bat
    
On Mac/Linux, run this command:

    source venv/bin/activate

Install the project requirements:

    pip install -r requirements.txt
    npm install

Create a local environment configuration by copying the defaults in `env.sample`:

    cp env.sample .env
    
Package the static files for the project:
    
    webpack --config webpack.config.js
    python manage.py collectstatic
 
Run the test suite to ensure your environment is properly configured:

    python manage.py test

Create the database schema, and load the initial application data:

    python manage.py migrate
    python manage.py loaddata source_tags 
    
Serve the Django application using [Gunicorn](http://gunicorn.org/):

    gunicorn -c conf.py openintel.wsgi --log-file -
    
If you are using Heroku, you can run the project with:    
    
    heroku local web
    
## Code Style and Testing

Before submitting a pull request, please review the 
[quality control wiki](https://github.com/twschiller/open-synthesis/wiki/Quality-Controls).

# Acknowledgements

We gratefully acknowledge this project's 3rd-party libraries and their contributors. See [here](requirements.txt) and 
[here](package.json). Additionally, we'd like to acknowledge the following:

* SSL/TLS certificate generated with [Let's Encrypt](https://letsencrypt.org/)
* Project hosting provided by [GitHub](https://github.com)
* Continuous Integration provided by [Travis CI](https://travis-ci.org/)
* Code Coverage Reporting provided by [Coveralls](https://coveralls.io/)
* Code Lint Reporting provided by [Code Climate](https://codeclimate.com/), [Codacy](https://www.codacy.com/), and 
[Landscape.io](https://landscape.io)
* [Responsible Disclosure Policy](SECURITY.md) adapted from Bugcrowd's 
[Open Source Responsible Disclosure Framework](https://github.com/bugcrowd/disclosure-policy) under a
[Creative Commons Attribution 4.0 International License](http://creativecommons.org/licenses/by/4.0/)
* FavIcon designed by [Freepik](http://www.freepik.com) from [Flaticon](http://www.flaticon.com)
and licensed by [Creative Commons BY 3.0](http://creativecommons.org/licenses/by/3.0/).
