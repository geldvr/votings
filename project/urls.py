"""project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from .voting.views import VotingsView, VotingDetailsView, SendVoteView

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^votings/(?P<status>active|finished|all|)/?$', VotingsView.as_view()),
    re_path(r'^votings/(?P<voting_id>\d+)/$', VotingDetailsView.as_view(), name='voting_detail'),
    re_path(r'^votings/vote/(?P<voting_id>\d+)/(?P<candidate_id>\d+)$', SendVoteView.as_view(), name='send_vote')
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
