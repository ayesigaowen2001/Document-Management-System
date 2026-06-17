# This file
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminProfileViewSet,
    AssignDocumentPermissionsView,
    AuthTokenLoginView,
    AuthTokenLogoutView,
    AuthTokenLogoutAllView,
    AuthUserViewSet,
    CreateUserView,
    DocumentPermissionListView,
    DocumentViewSet,
    SuperuserCreateAdminView,
    UserGroupViewSet,
    UserProfileViewSet,
)


router = DefaultRouter()
router.register('auth-users', AuthUserViewSet, basename='auth-user')
router.register('admin-profiles', AdminProfileViewSet, basename='admin-profile')
router.register('user-profiles', UserProfileViewSet, basename='user-profile')
router.register('groups', UserGroupViewSet, basename='group')
router.register('documents', DocumentViewSet, basename='document')


urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', AuthTokenLoginView.as_view(), name='auth-token'),
    path('auth/logout/', AuthTokenLogoutView.as_view(), name='auth-logout'),
    path('auth/logout-all/', AuthTokenLogoutAllView.as_view(), name='auth-logout-all'),
    path('auth/admins/', SuperuserCreateAdminView.as_view(), name='auth-create-admin'),
    path('auth/admins/<int:pk>/', SuperuserCreateAdminView.as_view(), name='auth-admin-detail'),
    path('auth/users/', CreateUserView.as_view(), name='auth-create-user'),
    path('auth/users/<int:pk>/', CreateUserView.as_view(), name='auth-user-detail'),
    path('auth/document-permissions/', DocumentPermissionListView.as_view(), name='auth-document-permissions'),
    path('auth/assign-document-permissions/', AssignDocumentPermissionsView.as_view(), name='auth-assign-document-permissions'),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]
