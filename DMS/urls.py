"""
URL configuration for the DMS project (root level).

This module defines the top-level URL patterns for the entire Document
Management System.  It delegates all API-related routes to the
Document_Management_System app's own `urls.py` module, keeping the
project-level configuration minimal.

Routes
------
- /admin/       → Django's built-in admin interface.
- /api/         → All DMS REST API endpoints (included from the app's urls.py).
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django admin site – accessible only to users with is_staff=True.
    path('admin/', admin.site.urls),

    # All custom REST API routes for the DMS (login, users, documents, etc.).
    path('api/', include('DMS.Document_Management_System.urls')),
]
