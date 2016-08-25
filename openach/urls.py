from django.conf.urls import url

from . import views

app_name = 'openach'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^boards/(?P<board_id>[0-9]+)/$', views.detail, name='detail'),
    url(r'^boards/create$', views.create_board, name='create_board'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/add', views.add_evidence, name='add_evidence'),
    url(r'^boards/(?P<board_id>[0-9]+)/hypotheses/add', views.add_hypothesis, name='add_hypothesis'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/(?P<evidence_id>[0-9]+)/evaluate$', views.evaluate, name='evaluate'),
    url(r'^about$', views.about, name='about'),
]
