from django.contrib import admin
from django.urls import path, include
from authentication.views import guest_page
from authentication import views
from articles import views as articles
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", guest_page, name="guest"),
    path("home/", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("doctor/request-status/", views.doctor_request_status, name="doctor_request_status"),
    path("doctor/portal/", views.doctor_portal, name="doctor_portal"),
    path("generate-blog/", articles.gemini_blog_generate, name="gemini_blog_generate"),
    path("dashboard/", include("dashboard.urls")),
    path("articles/", include("articles.urls")),
    path("community/", include("community.urls")),
    path("symptoms/", include("symptom_checker.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
