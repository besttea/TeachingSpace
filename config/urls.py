"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),

    # Home page
    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    # App URLs
    path('accounts/', include('apps.accounts.urls')),
    path('learning/', include('apps.learning.urls')),
    path('training/', include('apps.training.urls')),
    path('chat/', include('apps.chat.urls')),
    path('examination/', include('apps.examination.urls')),
]

# Serve media/static files in development (production uses WhiteNoise)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # T24: serve ALL static dirs, not just the first (was STATICFILES_DIRS[0])
    for static_dir in settings.STATICFILES_DIRS:
        urlpatterns += static(settings.STATIC_URL, document_root=static_dir)
