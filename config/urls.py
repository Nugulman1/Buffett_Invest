"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/dart/', include('apps.dart.urls')),
    path('api/ecos/', include('apps.ecos.urls')),
]

