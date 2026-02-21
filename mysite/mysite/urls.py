from django.contrib import admin
from django.urls import path, include
from authentication.views import guest_page
from authentication import views


urlpatterns = [
    path('', guest_page, name="guest_page"),
    path('home/', views.home, name="home"),
    path("admin/", admin.site.urls),
    path('login/', views.login_page, name='login_page'),
    path('register/', views.register_page, name='register'),

    path('symptoms/', include('symptom_checker.urls')),

]
