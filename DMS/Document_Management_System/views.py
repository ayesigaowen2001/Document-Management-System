# This file defines the API views for the Document Management System (DMS) application.
# It includes viewsets for admin profiles, user profiles, user groups, and documents, as well as custom API views for authentication and user creation.
# Each viewset and API view is configured with appropriate authentication and permission classes to ensure that only authorized users can access the endpoints. 
# The viewsets also include custom actions for managing group memberships and handling user authentication tokens. 
# The API views for creating admins and users include validation to ensure that only superusers and admins can perform these actions, and that the provided data is valid.

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated, IsAdminUser, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.fields import empty
from rest_framework.views import APIView

from .models import AdminProfile, Document, DocumentShare, UserGroup, UserProfile
from .serializers import (
	AccountCreateSerializer,
	AdminProfileSerializer,
	DocumentSerializer,
	DocumentPermissionAssignmentSerializer,
	DocumentShareSerializer,
	UserGroupAddMemberSerializer,
	UserGroupSerializer,
	UserProfileSerializer,
	UserUpdateSerializer,
)


User = get_user_model()

DOCUMENT_PERMISSION_APP_LABEL = 'Document_Management_System'
DOCUMENT_PERMISSION_MODEL = 'document'


def get_request_user_profile(user):
	return getattr(user, 'user_profile', None)


def is_admin_actor(user) -> bool:
	return bool(user.is_superuser or getattr(user, 'is_staff', False) or hasattr(user, 'admin_profile'))


class DocumentAccessPermission(BasePermission):
	message = 'You do not have the required document permission.'

	def has_permission(self, request, view) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
		user = request.user
		if not user or not user.is_authenticated:
			return False

		if is_admin_actor(user):
			return True

		permission_codename = self._get_permission_codename(request.method, getattr(view, 'action', None))
		if permission_codename is None:
			return True

		return bool(user.has_perm(f'{DOCUMENT_PERMISSION_APP_LABEL}.{permission_codename}'))

	def has_object_permission(self, request, view, obj) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
		user = request.user
		if is_admin_actor(user):
			return True

		if request.method in SAFE_METHODS:
			return self._can_view_document(user, obj)

		return bool(obj.uploaded_by.user_id == user.id)

	def _can_view_document(self, user, document) -> bool:
		user_profile = get_request_user_profile(user)
		if user_profile is None:
			return False

		if document.uploaded_by_id == user_profile.id:
			return True

		return bool(document.shares.filter(
			Q(shared_with_user=user_profile) | Q(shared_with_group__members=user_profile)
		).exists())

	def _get_permission_codename(self, method, action):
		if action == 'share':
			return 'share_document'

		return {
			'GET': 'view_document',
			'HEAD': 'view_document',
			'OPTIONS': None,
			'POST': 'add_document',
			'PUT': 'change_document',
			'PATCH': 'change_document',
			'DELETE': 'delete_document',
		}.get(method)


class AdminProfileViewSet(viewsets.ModelViewSet):
	queryset = AdminProfile.objects.select_related('user').all()
	serializer_class = AdminProfileSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]


class UserProfileViewSet(viewsets.ModelViewSet):
	queryset = UserProfile.objects.select_related('user', 'created_by').all()
	serializer_class = UserProfileSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]


class UserGroupViewSet(viewsets.ModelViewSet):
	queryset = UserGroup.objects.select_related('created_by').prefetch_related('members').all()
	serializer_class = UserGroupSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]

	@action(detail=True, methods=['post'], url_path='add-member')
	def add_member(self, request, pk=None):
		serializer = UserGroupAddMemberSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		group = self.get_object()
		user_profile = serializer.validated_data['user_profile']
		group.members.add(user_profile)
		return Response(
			{'detail': 'User added to group successfully.'},
			status=status.HTTP_200_OK,
		)


class DocumentViewSet(viewsets.ModelViewSet):
	queryset = Document.objects.select_related('uploaded_by', 'group').prefetch_related('shares').all()
	serializer_class = DocumentSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [DocumentAccessPermission]

	def get_queryset(self):
		queryset = super().get_queryset()
		user = self.request.user

		if not user.is_authenticated:
			return queryset.none()

		if is_admin_actor(user):
			return queryset

		user_profile = get_request_user_profile(user)
		if user_profile is None:
			return queryset.none()

		return queryset.filter(
			Q(uploaded_by=user_profile)
			| Q(shares__shared_with_user=user_profile)
			| Q(shares__shared_with_group__members=user_profile)
		).distinct()

	def perform_create(self, serializer):
		user_profile = get_request_user_profile(self.request.user)
		if user_profile is None:
			raise ValidationError({'detail': 'A user profile is required to upload documents.'})

		serializer.save(uploaded_by=user_profile)

	@action(detail=True, methods=['post'], url_path='share')
	def share(self, request, pk=None):
		document = self.get_object()
		self.check_object_permissions(request, document)

		shared_by = get_request_user_profile(request.user)
		if shared_by is None:
			return Response({'detail': 'A user profile is required to share documents.'}, status=status.HTTP_400_BAD_REQUEST)

		serializer = DocumentShareSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid share payload.'}, status=status.HTTP_400_BAD_REQUEST)

		shared_with_user = validated_data.get('shared_with_user')
		shared_with_group = validated_data.get('shared_with_group')
		share, created = DocumentShare.objects.get_or_create(
			document=document,
			shared_with_user=shared_with_user,
			shared_with_group=shared_with_group,
			defaults={'shared_by': shared_by},
		)

		if not created:
			share.shared_by = shared_by
			share.save(update_fields=['shared_by'])

		response_serializer = DocumentShareSerializer(share)
		return Response(
			response_serializer.data,
			status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
		)


class AuthTokenLoginView(ObtainAuthToken):
	permission_classes = [AllowAny]

	def post(self, request, *args, **kwargs):
		serializer = AuthTokenSerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if validated_data in (None, empty) or not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)
		user = validated_data.get('user')
		if user is None:
			return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_400_BAD_REQUEST)
		token, _ = Token.objects.get_or_create(user=user)
		return Response(
			{
				'token': token.key,
				'user_id': user.pk,
				'username': user.get_username(),
			}
		)


class AuthTokenLogoutView(APIView):
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class SuperuserCreateAdminView(APIView):
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, pk=None):
		if not request.user.is_superuser:
			return Response({'detail': 'Only superusers can view admins.'}, status=status.HTTP_403_FORBIDDEN)

		if pk is not None:
			admin_profile = get_object_or_404(AdminProfile.objects.select_related('user'), pk=pk)
			serializer = AdminProfileSerializer(admin_profile)
			return Response(serializer.data, status=status.HTTP_200_OK)

		admin_profiles = AdminProfile.objects.select_related('user').all()
		serializer = AdminProfileSerializer(admin_profiles, many=True)
		return Response(serializer.data, status=status.HTTP_200_OK)

	@transaction.atomic
	def patch(self, request, pk=None):
		if not request.user.is_superuser:
			return Response({'detail': 'Only superusers can update admins.'}, status=status.HTTP_403_FORBIDDEN)

		if pk is None:
			return Response({'detail': 'Admin ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

		admin_profile = get_object_or_404(AdminProfile.objects.select_related('user'), pk=pk)
		target_user = admin_profile.user

		serializer = UserUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		username = validated_data.get('username')
		email = validated_data.get('email')
		password = validated_data.get('password')

		if username is not None:
			if not isinstance(username, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			if User.objects.filter(username=username).exclude(pk=target_user.pk).exists():
				return Response({'detail': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.username = username

		if email is not None:
			if not isinstance(email, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.email = email

		target_user.save()

		if password is not None:
			if not isinstance(password, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.set_password(password)
			target_user.save()

		return Response(
			{
				'detail': 'Admin updated successfully.',
				'admin_profile_id': admin_profile.pk,
				'user_id': target_user.pk,
				'username': target_user.get_username(),
			},
			status=status.HTTP_200_OK,
		)

	@transaction.atomic
	def post(self, request):
		if not request.user.is_superuser:
			return Response({'detail': 'Only superusers can create admins.'}, status=status.HTTP_403_FORBIDDEN)

		serializer = AccountCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if validated_data in (None, empty) or not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		username = validated_data.get('username')
		email = validated_data.get('email')
		password = validated_data.get('password')
		if not isinstance(username, str) or not isinstance(email, str) or not isinstance(password, str):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		if User.objects.filter(username=username).exists():
			return Response({'detail': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

		user = User.objects.create_user(
			username=username,
			email=email,
			password=password,
			is_staff=True,
		)
		admin_profile = AdminProfile.objects.create(user=user)

		return Response(
			{
				'detail': 'Admin created successfully.',
				'admin_profile_id': admin_profile.pk,
				'user_id': user.pk,
				'username': user.get_username(),
			},
			status=status.HTTP_201_CREATED,
		)


class CreateUserView(APIView):
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, pk=None):
		if not (request.user.is_superuser or hasattr(request.user, 'admin_profile')):
			return Response(
				{'detail': 'Only superusers and admins can view users.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		if pk is not None:
			user_profile = get_object_or_404(UserProfile.objects.select_related('user', 'created_by'), pk=pk)
			serializer = UserProfileSerializer(user_profile)
			return Response(serializer.data, status=status.HTTP_200_OK)

		user_profiles = UserProfile.objects.select_related('user', 'created_by').all()
		serializer = UserProfileSerializer(user_profiles, many=True)
		return Response(serializer.data, status=status.HTTP_200_OK)

	@transaction.atomic
	def patch(self, request, pk=None):
		if not (request.user.is_superuser or hasattr(request.user, 'admin_profile')):
			return Response(
				{'detail': 'Only superusers and admins can update users.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		if pk is None:
			return Response({'detail': 'User profile ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

		user_profile = get_object_or_404(UserProfile.objects.select_related('user'), pk=pk)
		target_user = user_profile.user

		serializer = UserUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		username = validated_data.get('username')
		email = validated_data.get('email')
		password = validated_data.get('password')

		if username is not None:
			if not isinstance(username, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			if User.objects.filter(username=username).exclude(pk=target_user.pk).exists():
				return Response({'detail': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.username = username

		if email is not None:
			if not isinstance(email, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.email = email

		target_user.save()

		if password is not None:
			if not isinstance(password, str):
				return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)
			target_user.set_password(password)
			target_user.save()

		return Response(
			{
				'detail': 'User updated successfully.',
				'user_profile_id': user_profile.pk,
				'user_id': target_user.pk,
				'username': target_user.get_username(),
			},
			status=status.HTTP_200_OK,
		)

	@transaction.atomic
	def post(self, request):
		if not (request.user.is_superuser or hasattr(request.user, 'admin_profile')):
			return Response(
				{'detail': 'Only superusers and admins can create users.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		serializer = AccountCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if validated_data in (None, empty) or not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		username = validated_data.get('username')
		email = validated_data.get('email')
		password = validated_data.get('password')
		if not isinstance(username, str) or not isinstance(email, str) or not isinstance(password, str):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		if User.objects.filter(username=username).exists():
			return Response({'detail': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)

		user = User.objects.create_user(
			username=username,
			email=email,
			password=password,
		)

		created_by = getattr(request.user, 'admin_profile', None)
		user_profile = UserProfile.objects.create(user=user, created_by=created_by)

		return Response(
			{
				'detail': 'User created successfully.',
				'user_profile_id': user_profile.pk,
				'user_id': user.pk,
				'username': user.get_username(),
			},
			status=status.HTTP_201_CREATED,
		)


class AssignDocumentPermissionsView(APIView):
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, user_id=None):
		if not is_admin_actor(request.user):
			return Response(
				{'detail': 'Only superusers and admins can view document permissions.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		document_permissions = Permission.objects.filter(
			content_type__app_label=DOCUMENT_PERMISSION_APP_LABEL,
			content_type__model=DOCUMENT_PERMISSION_MODEL,
		)

		if user_id is not None:
			target_user = get_object_or_404(User, pk=user_id)
			user_permissions = target_user.user_permissions.filter(
				content_type__app_label=DOCUMENT_PERMISSION_APP_LABEL,
				content_type__model=DOCUMENT_PERMISSION_MODEL,
			)
			user_permission_codenames = set(user_permissions.values_list('codename', flat=True))

			return Response(
				{
					'user_id': target_user.pk,
					'username': target_user.get_username(),
					'permissions': [
						{
							'id': perm.pk,
							'codename': perm.codename,
							'name': perm.name,
							'assigned': perm.codename in user_permission_codenames,
						}
						for perm in document_permissions
					],
				},
				status=status.HTTP_200_OK,
			)

		return Response(
			[
				{
					'id': perm.pk,
					'codename': perm.codename,
					'name': perm.name,
				}
				for perm in document_permissions
			],
			status=status.HTTP_200_OK,
		)

	def post(self, request):
		if not is_admin_actor(request.user):
			return Response(
				{'detail': 'Only superusers and admins can assign document permissions.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		serializer = DocumentPermissionAssignmentSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		target_user = validated_data.get('user')
		permissions = validated_data.get('permissions')
		if target_user is None or not isinstance(permissions, list):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		if target_user.is_staff or target_user.is_superuser:
			return Response({'detail': 'Permissions can only be assigned to regular users.'}, status=status.HTTP_400_BAD_REQUEST)

		document_permissions = Permission.objects.filter(
			content_type__app_label=DOCUMENT_PERMISSION_APP_LABEL,
			content_type__model=DOCUMENT_PERMISSION_MODEL,
		)
		target_user.user_permissions.remove(*document_permissions)

		selected_permissions = list(document_permissions.filter(codename__in=permissions))
		target_user.user_permissions.add(*selected_permissions)

		return Response(
			{
				'detail': 'Document permissions assigned successfully.',
				'user_id': target_user.pk,
				'permissions': [permission.codename for permission in selected_permissions],
			},
			status=status.HTTP_200_OK,
		)

	@transaction.atomic
	def patch(self, request, user_id=None):
		if not is_admin_actor(request.user):
			return Response(
				{'detail': 'Only superusers and admins can update document permissions.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		if user_id is None:
			return Response({'detail': 'User ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

		target_user = get_object_or_404(User, pk=user_id)

		if target_user.is_staff or target_user.is_superuser:
			return Response({'detail': 'Permissions can only be assigned to regular users.'}, status=status.HTTP_400_BAD_REQUEST)

		serializer = DocumentPermissionAssignmentSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		validated_data = serializer.validated_data
		if not isinstance(validated_data, dict):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		permissions = validated_data.get('permissions')
		if not isinstance(permissions, list):
			return Response({'detail': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

		document_permissions = Permission.objects.filter(
			content_type__app_label=DOCUMENT_PERMISSION_APP_LABEL,
			content_type__model=DOCUMENT_PERMISSION_MODEL,
		)
		selected_permissions = list(document_permissions.filter(codename__in=permissions))

		target_user.user_permissions.remove(*document_permissions)
		target_user.user_permissions.add(*selected_permissions)

		return Response(
			{
				'detail': 'Document permissions updated successfully.',
				'user_id': target_user.pk,
				'permissions': [permission.codename for permission in selected_permissions],
			},
			status=status.HTTP_200_OK,
		)


class DocumentPermissionListView(APIView):
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request):
		if not is_admin_actor(request.user):
			return Response(
				{'detail': 'Only superusers and admins can view document permissions.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		permissions = Permission.objects.filter(
			content_type__app_label=DOCUMENT_PERMISSION_APP_LABEL,
			content_type__model=DOCUMENT_PERMISSION_MODEL,
		).order_by('id')

		return Response(
			[
				{
					'id': permission.pk,
					'codename': permission.codename,
					'name': permission.name,
				}
				for permission in permissions
			],
			status=status.HTTP_200_OK,
		)
