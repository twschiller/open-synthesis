# OPEN-INTEL

[![Build Status](https://travis-ci.org/twschiller/open-intel.svg?branch=master)](https://travis-ci.org/twschiller/open-intel)
[![Coverage Status](https://coveralls.io/repos/github/twschiller/open-intel/badge.svg?branch=master)](https://coveralls.io/github/twschiller/open-intel?branch=master)
[![Requirements Status](https://requires.io/github/twschiller/open-intel/requirements.svg?branch=master)](https://requires.io/github/twschiller/open-intel/requirements/?branch=master)

The purpose of the OPEN-INTEL project is to empower the public to synthesize vast amounts of information into actionable conclusions.

To this end, the platform and its governance aims to be:

1. Inclusive
2. Transparent
3. Meritocratic

Our approach is to take best practices from the intelligence and business communities and adapt them work with internet 
communities.

## Analysis of Competing Hypotheses (ACH)

Initially, the platform will support the [Analysis of Competing Hypotheses (ACH) framework.](https://en.wikipedia.org/wiki/Analysis_of_competing_hypotheses)
ACH was developed by Richards J. Heuer, Jr. for use at the United States Central Intelligence Agency (CIA).

The ACH framework is a good candidate for public discourse because:

* ACH's hypothesis generation and evidence cataloging benefit from a diversity of perspectives
* ACH's process for combining the viewpoints of participants is straightforward and robust
* ACH can account for unreliable evidence, e.g., due to deception

The initial implementation will be similar to [competinghypotheses.org](http://competinghypotheses.org/). However, we 
will adapt the implementation to address the challenges of public discourse.

## Platform Design Principles

The platform will host the analysis of politically sensitive topics. Therefore, its design must strike a balance between
freedom of speech, safety, and productivity. More specific concerns include:

* Open-Source Licensing and Governance
* Privacy
* Accessibility
* Internationalization and Localization
* Moderation vs. Censorship

## Deploying to Heroku

```sh
$ heroku create
$ git push heroku master

$ heroku run python manage.py migrate
$ heroku open
```
or

[![Deploy](https://www.herokucdn.com/deploy/button.png)](https://heroku.com/deploy)

Further Reading
----------

* [Psychology of Intelligence Analysis](https://www.cia.gov/library/center-for-the-study-of-intelligence/csi-publications/books-and-monographs/psychology-of-intelligence-analysis/PsychofIntelNew.pdf), Richards J. Heuer, Jr.



