from django.contrib import admin
from .models import AdminProfile, Document, UserGroup, UserProfile


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'created_at')
	search_fields = ('user__username', 'user__email')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
	list_display = ('id', 'user', 'created_by', 'created_at')
	search_fields = ('user__username', 'user__email')
	list_filter = ('created_by',)


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'created_by', 'created_at')
	search_fields = ('name',)
	list_filter = ('created_by',)
	filter_horizontal = ('members',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ('id', 'title', 'uploaded_by', 'group', 'uploaded_at')
	search_fields = ('title',)
	list_filter = ('group', 'uploaded_at')
