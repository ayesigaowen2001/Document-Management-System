from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.fields import empty
from rest_framework.views import APIView

from .models import AdminProfile, Document, UserGroup, UserProfile
from .serializers import (
	AccountCreateSerializer,
	AdminProfileSerializer,
	DocumentSerializer,
	UserGroupAddMemberSerializer,
	UserGroupSerializer,
	UserProfileSerializer,
)


User = get_user_model()


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
	queryset = Document.objects.select_related('uploaded_by', 'group').all()
	serializer_class = DocumentSerializer
	authentication_classes = [TokenAuthentication]
	permission_classes = [IsAuthenticated]


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
