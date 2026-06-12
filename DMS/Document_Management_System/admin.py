# =============================================================================
# DMS/Document_Management_System/admin.py — Django Admin Registration
# =============================================================================
# This module registers all DMS models with Django's built-in admin interface.
#
# Each ModelAdmin class customises the admin list display, search fields,
# and list filters for better usability within the /admin/ panel.
# =============================================================================

from django.contrib import admin

from .models import AdminProfile, Document, DocumentShare, UserGroup, UserProfile


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    """
    Admin configuration for the AdminProfile model.

    List display columns: id, user, created_at
    Searchable by:       username and email (via the related User)
    """
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__username', 'user__email')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin configuration for the UserProfile model.

    List display columns: id, user, created_by, created_at
    Searchable by:       username and email (via the related User)
    Filterable by:       created_by (AdminProfile)
    """
    list_display = ('id', 'user', 'created_by', 'created_at')
    search_fields = ('user__username', 'user__email')
    list_filter = ('created_by',)


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    """
    Admin configuration for the UserGroup model.

    List display columns: id, name, created_by, created_at
    Searchable by:       name
    Filterable by:       created_by (AdminProfile)
    Uses filter_horizontal for the members M2M widget.
    """
    list_display = ('id', 'name', 'created_by', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_by',)
    filter_horizontal = ('members',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Document model.

    List display columns: id, title, uploaded_by, group, uploaded_at
    Searchable by:       title
    Filterable by:       group (UserGroup) and uploaded_at date
    """
    list_display = ('id', 'title', 'uploaded_by', 'group', 'uploaded_at')
    search_fields = ('title',)
    list_filter = ('group', 'uploaded_at')


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    """
    Admin configuration for the DocumentShare model.

    List display columns: id, document, shared_by, shared_with_user,
                          shared_with_group, created_at
    Searchable by:       document title and sharer's username
    Filterable by:       created_at date
    """
    
    list_display = (
        'id', 'document', 'shared_by',
        'shared_with_user', 'shared_with_group', 'created_at',
    )
    search_fields = ('document__title', 'shared_by__user__username')
    list_filter = ('created_at',)
