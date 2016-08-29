from django.conf.urls import url

from . import views

app_name = 'openach'
urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^boards/(?P<board_id>[0-9]+)/$', views.detail, name='detail'),
    url(r'^boards/create$', views.create_board, name='create_board'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/add', views.add_evidence, name='add_evidence'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)/sources/add', views.add_source, name='add_source'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)/sources/(?P<source_id>[0-9]+)/tag',
        views.add_source_tag,
        name='tag_source'),
    url(r'^evidence/(?P<evidence_id>[0-9]+)', views.evidence_detail, name='evidence_detail'),
    url(r'^boards/(?P<board_id>[0-9]+)/hypotheses/add', views.add_hypothesis, name='add_hypothesis'),
    url(r'^boards/(?P<board_id>[0-9]+)/evidence/(?P<evidence_id>[0-9]+)/evaluate$', views.evaluate, name='evaluate'),
    url(r'^boards/(?P<board_id>[0-9]+)/(?P<board_slug>[A-Za-z0-9\-]+)/$', views.detail, name='detail_slug'),
    url(r'^about$', views.about, name='about'),
]
