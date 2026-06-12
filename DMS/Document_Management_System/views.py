# =============================================================================
# DMS/Document_Management_System/views.py — API Views
# =============================================================================
# This file defines all REST API views for the Document Management System (DMS)
# application. It provides the following categories of endpoints:
#
# 1. ViewSets (CRUD operations):
#    - AdminProfileViewSet  – Manage admin profiles (superuser-only)
#    - UserProfileViewSet   – Manage user profiles   (superuser-only)
#    - UserGroupViewSet     – Manage user groups     (superuser-only)
#    - DocumentViewSet      – Manage documents       (permission-aware)
#
# 2. Authentication views:
#    - AuthTokenLoginView   – Login  via username/password, issue token
#    - AuthTokenLogoutView  – Logout, destroy the user's token
#
# 3. Admin / User management views:
#    - SuperuserCreateAdminView – CRUD for admin accounts    (superuser-only)
#    - CreateUserView           – CRUD for regular users     (admin/superuser)
#
# 4. Permission management views:
#    - AssignDocumentPermissionsView – Bulk assign/revoke document perms
#    - DocumentPermissionListView     – List all available document perms
#
# Each view uses TokenAuthentication.  Permission checks rely on Django's
# built-in permission system as well as the custom DocumentAccessPermission
# class that enforces fine-grained view/add/change/delete/share rights.
# =============================================================================

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
	DocumentShareSerializer,
	UserGroupAddMemberSerializer,
	UserGroupSerializer,
	UserProfileSerializer,
	UserUpdateSerializer,
	DocumentPermissionAssignmentSerializer

)


# ---------------------------------------------------------------------------
# Global helpers & constants
# ---------------------------------------------------------------------------

User = get_user_model()

# Used to scope permission queries to the Document model only.
DOCUMENT_PERMISSION_APP_LABEL = 'Document_Management_System'
DOCUMENT_PERMISSION_MODEL = 'document'


def get_request_user_profile(user):
	"""
	Retrieve the UserProfile related to the given User object.
	Returns None if the user does not have a profile (e.g., admin/superuser).
	"""
	return getattr(user, 'user_profile', None)


def is_admin_actor(user) -> bool:
	"""
	Check whether a user should be treated as an administrative actor.
	Returns True if the user is:
	  - a superuser,
	  - a staff member,
	  - or has an AdminProfile (i.e. is an admin created via SuperuserCreateAdminView).
	"""
	return bool(user.is_superuser or getattr(user, 'is_staff', False) or hasattr(user, 'admin_profile'))


# ---------------------------------------------------------------------------
# Custom permission class
# ---------------------------------------------------------------------------

class DocumentAccessPermission(BasePermission):
	"""
	Custom DRF permission class that enforces document-level access control.

	**Table-level permission (has_permission):**
	  - Unauthenticated users are denied.
	  - Admin actors (superuser/staff/AdminProfile) bypass checks.
	  - Maps the HTTP method to a Django permission codename
		(GET → view_document, POST → add_document, etc.)
		and checks whether the user has that permission.
	  - The 'share' action always requires the 'share_document' permission.
	  - OPTIONS requests are always allowed.

	**Object-level permission (has_object_permission):**
	  - Admin actors bypass checks.
	  - Safe methods (GET, HEAD, OPTIONS) → delegates to _can_view_document().
	  - Mutating methods (PUT, PATCH, DELETE) → only the uploader may proceed.
	"""
	message = 'You do not have the required document permission.'

	def has_permission(self, request, view) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
		"""Check whether the user has the required document permission at table level."""
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
		"""Check whether the user may access a specific document instance."""
		user = request.user
		if is_admin_actor(user):
			return True

		if request.method in SAFE_METHODS:
			return self._can_view_document(user, obj)

		return bool(obj.uploaded_by.user_id == user.id)

	def _can_view_document(self, user, document) -> bool:
		"""
		Determine if a regular user can *view* a specific document.
		Access is granted if the user:
		  - is the uploader, or
		  - has been directly shared the document, or
		  - belongs to a group that has been shared the document.
		"""
		user_profile = get_request_user_profile(user)
		if user_profile is None:
			return False

		if document.uploaded_by_id == user_profile.id:
			return True

		return bool(document.shares.filter(
			Q(shared_with_user=user_profile) | Q(shared_with_group__members=user_profile)
		).exists())

	def _get_permission_codename(self, method, action):
		"""Map an HTTP method (and optional DRF action) to a Django permission codename."""
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


# ---------------------------------------------------------------------------
# ViewSets  (CRUD endpoints)
# ---------------------------------------------------------------------------

class AdminProfileViewSet(viewsets.ModelViewSet):
	"""
	ViewSet for managing AdminProfile records.
	- Only accessible to Django admin users (is_staff=True / is_superuser).
	- Uses TokenAuthentication.
	- Provides the standard set of list / create / retrieve / update / destroy
	  actions automatically via ModelViewSet.
	"""
	queryset = AdminProfile.objects.select_related('user').all()
	serializer_class = AdminProfileSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]


class UserProfileViewSet(viewsets.ModelViewSet):
	"""
	ViewSet for managing regular UserProfile records.
	- Only accessible to Django admin users.
	- Eager-loads the related 'user' and 'created_by' ForeignKeys.
	"""
	queryset = UserProfile.objects.select_related('user', 'created_by').all()
	serializer_class = UserProfileSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]


class UserGroupViewSet(viewsets.ModelViewSet):
	"""
	ViewSet for managing UserGroup records (groups of regular users).
	- Only accessible to Django admin users.
	- Eager-loads the 'created_by' FK and prefetches the 'members' M2M.

	Custom actions:
	- POST /user-groups/{pk}/add-member/  → adds a UserProfile to the group.
	"""
	queryset = UserGroup.objects.select_related('created_by').prefetch_related('members').all()
	serializer_class = UserGroupSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAdminUser]

	@action(detail=True, methods=['post'], url_path='add-member')
	def add_member(self, request, pk=None):
		"""
		POST /user-groups/{id}/add-member/
		Add a single UserProfile (supplied in the request body) to the group.
		"""
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
	"""
	ViewSet for managing Document records.
	- Uses the custom DocumentAccessPermission for fine-grained access control.
	- Admin users (superuser/staff/AdminProfile) see all documents.
	- Regular users only see documents they own or have been shared with.

	Custom actions:
	- POST /documents/{pk}/share/  → share a document with a user or group.
	"""
	queryset = Document.objects.select_related('uploaded_by', 'group').prefetch_related('shares').all()
	serializer_class = DocumentSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [DocumentAccessPermission]

	def get_queryset(self):
		"""
		Override to scope the document queryset to the current user:
		- Admin actors → all documents.
		- Regular users → documents uploaded by them, shared directly with
		  them, or shared with a group they belong to.
		"""
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
		"""
		Automatically set the `uploaded_by` field on the document to the
		current user's UserProfile when creating a new document.
		Raises a 400 error if the user does not have a UserProfile.
		"""
		user_profile = get_request_user_profile(self.request.user)
		if user_profile is None:
			raise ValidationError({'detail': 'A user profile is required to upload documents.'})

		serializer.save(uploaded_by=user_profile)

	@action(detail=True, methods=['post'], url_path='share')
	def share(self, request, pk=None):
		"""
		POST /documents/{id}/share/
		Share a document with another user (UserProfile) or a group (UserGroup).

		- Checks object-level permission first.
		- Uses get_or_create so re-sharing the same combination updates the
		  shared_by field rather than creating a duplicate DocumentShare row.
		"""
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


# ---------------------------------------------------------------------------
# Authentication views
# ---------------------------------------------------------------------------

class AuthTokenLoginView(ObtainAuthToken):
	"""
	POST /api/auth/login/
	Login view that accepts username and password and returns an auth token.
	Uses DRF's ObtainAuthToken under the hood but overrides `post` to return
	a more structured response (token + user_id + username).

	Accessible without authentication (AllowAny).
	"""
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
	"""
	POST /api/auth/logout/
	Logout view that deletes the user's auth token, effectively invalidating
	the session.

	Requires a valid token (IsAuthenticated).
	"""
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		return Response({'detail': 'Logged out successfully.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Admin / User management views
# ---------------------------------------------------------------------------

class SuperuserCreateAdminView(APIView):
	"""
	Superuser-only CRUD view for managing Admin accounts.

	Available endpoints (all require TokenAuthentication):
	  - GET    /api/admins/          → list all admin profiles
	  - GET    /api/admins/{pk}/     → retrieve a single admin profile
	  - POST   /api/admins/          → create a new admin (Django staff user)
	  - PATCH  /api/admins/{pk}/     → update username / email / password

	All operations are restricted to superusers.  When creating an admin, the
	view creates both a Django User (is_staff=True) and an AdminProfile record.
	"""
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, pk=None):
		"""
		GET /api/admins/  or  GET /api/admins/{pk}/
		Returns one or all admin profiles.
		"""
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
		"""
		PATCH /api/admins/{pk}/
		Partially update an admin's User record (username, email, password).
		Each field is optional; only supplied fields are updated.
		Password is hashed via set_password().
		"""
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
		"""
		POST /api/admins/
		Create a new admin user.
		- The created Django User has is_staff=True.
		- An associated AdminProfile is also created.
		"""
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
	"""
	Admin/Superuser view for managing regular User accounts.

	Available endpoints (all require TokenAuthentication):
	  - GET    /api/users/          → list all user profiles
	  - GET    /api/users/{pk}/     → retrieve a single user profile
	  - POST   /api/users/          → create a new regular user
	  - PATCH  /api/users/{pk}/     → update username / email / password

	All operations are restricted to superusers and admin-profile holders.
	When creating a user, the view creates both a Django User and a UserProfile,
	optionally recording the admin who created it.
	"""
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, pk=None):
		"""
		GET /api/users/  or  GET /api/users/{pk}/
		Returns one or all regular user profiles.
		"""
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
		"""
		PATCH /api/users/{pk}/
		Partially update a regular user's User record (username, email, password).
		Each field is optional; only supplied fields are updated.
		Password is hashed via set_password().
		"""
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
		"""
		POST /api/users/
		Create a new regular user.
		- The created Django User is NOT staff (regular user).
		- An associated UserProfile is created, with `created_by` set to the
		  requesting admin's admin_profile (if applicable).
		"""
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


# ---------------------------------------------------------------------------
# Permission management views
# ---------------------------------------------------------------------------

class AssignDocumentPermissionsView(APIView):
	"""
	View for assigning and updating document-level permissions on regular users.

	Available endpoints (all require TokenAuthentication):
	  - GET    /api/permissions/            → list all document permissions
	  - GET    /api/permissions/{user_id}/  → list perms for a specific user
	  - POST   /api/permissions/            → assign (overwrite) perms for a user
	  - PATCH  /api/permissions/{user_id}/  → update  (overwrite) perms for a user

	All operations are restricted to admin actors.
	Permissions can only be assigned to regular (non-staff, non-superuser) users.
	On each POST/PATCH, the user's existing document permissions are cleared and
	replaced with the requested set.
	"""
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request, user_id=None):
		"""
		GET /api/permissions/  or  GET /api/permissions/{user_id}/
		If user_id is provided, returns the list of document permissions with
		an `assigned` flag indicating which ones the user currently has.
		Otherwise, returns all document-level permission definitions.
		"""
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
		"""
		POST /api/permissions/
		Assign (overwrite) document permissions for a user.
		Accepts a user reference and a list of permission codenames.
		Clears all existing document permissions for the user first,
		then assigns only the requested ones.
		"""
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
		"""
		PATCH /api/permissions/{user_id}/
		Update (overwrite) document permissions for a user identified by URL.
		Accepts a list of permission codenames.
		Clears all existing document permissions for the user first,
		then assigns only the requested ones.
		"""
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
	"""
	GET /api/permissions/list/
	List all available document-level permissions (view, add, change, delete, share)
	for the Document model.

	Restricted to admin actors (superusers / staff / AdminProfile holders).
	"""
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]

	def get(self, request):
		"""
		Return a list of all permission definitions for the Document model,
		each containing id, codename, and name.
		"""
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
