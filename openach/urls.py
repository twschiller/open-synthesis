"""Analysis of Competing Hypotheses Django Application URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url

from . import views

# NOTE: Django's API doesn't follow constant naming convention for 'app_name' and 'urlpatterns'

app_name = 'openach'  # pylint: disable=invalid-name

urlpatterns = [  # pylint: disable=invalid-name
    url(r'^$', views.index, name='index'),
    url(r'^static/images/bitcoin\.svg$', views.bitcoin_qrcode, name='bitcoin_donate'),
    url(r'^boards/$', views.board_listing, name='boards'),
    url(r'^accounts/(?P<account_id>[0-9]+)/boards/', views.user_board_listing, name='user_boards'),
    url(r'^boards/(?P<board_id>[0-9]+)/$', views.detail, name='detail'),
    url(r'^boards/create$', views.create_board, name='create_board'),
    url(r'^boards/(?P<board_id>[0-9]+)/history/', views.board_history, name='board_history'),
    url(r'^boards/(?P<board_id>[0-9]+)/edit/', views.edit_board, name='edit_board'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/add', views.add_evidence, name='add_evidence'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)/sources/add', views.add_source, name='add_source'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)/edit/', views.edit_evidence, name='edit_evidence'),
    url(r'^hypotheses/(?P<hypothesis_id>[0-9]+)/edit/', views.edit_hypothesis, name='edit_hypothesis'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)/sources/(?P<source_id>[0-9]+)/tag',
        views.toggle_source_tag,
        name='tag_source'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)', views.evidence_detail, name='evidence_detail'),
    url(r'^boards/(?P<board_id>[0-9]+)/hypotheses/add', views.add_hypothesis, name='add_hypothesis'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/(?P<evidence_id>[0-9]+)/evaluate$', views.evaluate, name='evaluate'),
    url(r'^boards/(?P<board_id>[0-9]+)/(?P<dummy_board_slug>[A-Za-z0-9\-]+)/$', views.detail, name='detail_slug'),
    url(r'^about$', views.about, name='about'),
]
