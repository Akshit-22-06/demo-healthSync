from django.urls import path

from community import views


urlpatterns = [
    path("", views.community_home, name="community"),
    path("request-access/", views.submit_community_access_request, name="community_request_access"),
    path("room/<slug:room_code>/", views.community_room_view, name="community_room"),
]

