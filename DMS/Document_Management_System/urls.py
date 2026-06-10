from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminProfileViewSet,
    AuthTokenLoginView,
    AuthTokenLogoutView,
    CreateUserView,
    DocumentViewSet,
    SuperuserCreateAdminView,
    UserGroupViewSet,
    UserProfileViewSet,
)


router = DefaultRouter()
router.register('admin-profiles', AdminProfileViewSet, basename='admin-profile')
router.register('user-profiles', UserProfileViewSet, basename='user-profile')
router.register('groups', UserGroupViewSet, basename='group')
router.register('documents', DocumentViewSet, basename='document')


urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', AuthTokenLoginView.as_view(), name='auth-token'),
    path('auth/logout/', AuthTokenLogoutView.as_view(), name='auth-logout'),
    path('auth/create-admin/', SuperuserCreateAdminView.as_view(), name='auth-create-admin'),
    path('auth/create-user/', CreateUserView.as_view(), name='auth-create-user'),
   # path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
]
