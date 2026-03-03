from django.urls import path

from community import views


urlpatterns = [
    path("", views.community, name="community"),
    path("request-access/", views.community_request_access, name="community_request_access"),
    path("room/<slug:room_code>/", views.community_room, name="community_room"),
]

