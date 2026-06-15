from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.test import APITestCase, APIClient

from .models import AdminProfile, Document, DocumentShare, UserGroup, UserProfile


User = get_user_model()


class DocumentPermissionAndSharingTests(APITestCase):
	def setUp(self):
		self.api_client = cast(APIClient, self.client)

		self.admin_user = User.objects.create_user(
			username='adminuser',
			email='admin@example.com',
			password='strongpass123',
			is_staff=True,
		)
		self.admin_profile = AdminProfile.objects.create(user=self.admin_user)
		self.admin_token = Token.objects.create(user=self.admin_user)

		self.regular_user = User.objects.create_user(
			username='regularuser',
			email='regular@example.com',
			password='strongpass123',
		)
		self.regular_profile = UserProfile.objects.create(user=self.regular_user, created_by=self.admin_profile)

		self.recipient_user = User.objects.create_user(
			username='recipient',
			email='recipient@example.com',
			password='strongpass123',
		)
		self.recipient_profile = UserProfile.objects.create(user=self.recipient_user, created_by=self.admin_profile)
		self.recipient_token = Token.objects.create(user=self.recipient_user)

		self.group = UserGroup.objects.create(name='Team A', created_by=self.admin_profile)
		self.group.members.add(self.recipient_profile)

	def test_admin_can_assign_document_permissions_to_user_by_email(self):
		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
		response = cast(Response, self.api_client.post(
			reverse('auth-assign-document-permissions'),
			{
				'email': self.regular_user.email,
				'permissions': ['view_document', 'add_document', 'share_document'],
			},
			format='json',
		))

		self.assertEqual(response.status_code, 200)
		response_data = cast(dict[str, Any], response.data)
		self.assertEqual(response_data['email'], self.regular_user.email)
		assigned = set(
			self.regular_user.user_permissions.filter(content_type__model='document').values_list('codename', flat=True)
		)
		self.assertEqual(assigned, {'view_document', 'add_document', 'share_document'})

	def test_admin_can_assign_document_permissions_by_email_with_patch(self):
		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
		response = cast(Response, self.api_client.patch(
			reverse('auth-assign-document-permissions'),
			{
				'email': self.regular_user.email,
				'permissions': ['view_document', 'delete_document'],
			},
			format='json',
		))

		self.assertEqual(response.status_code, 200)
		response_data = cast(dict[str, Any], response.data)
		self.assertEqual(response_data['email'], self.regular_user.email)
		assigned = set(
			self.regular_user.user_permissions.filter(content_type__model='document').values_list('codename', flat=True)
		)
		self.assertEqual(assigned, {'view_document', 'delete_document'})

	def test_assign_permissions_fails_for_unknown_email(self):
		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
		response = cast(Response, self.api_client.post(
			reverse('auth-assign-document-permissions'),
			{
				'email': 'nonexistent@example.com',
				'permissions': ['view_document'],
			},
			format='json',
		))
		self.assertEqual(response.status_code, 400)
		self.assertIn('nonexistent', str(response.data))

	def test_shared_document_is_visible_to_recipient(self):
		view_permission = Permission.objects.get(codename='view_document', content_type__model='document')
		share_permission = Permission.objects.get(codename='share_document', content_type__model='document')
		self.regular_user.user_permissions.add(view_permission, share_permission)
		self.recipient_user.user_permissions.add(view_permission)
		regular_token = Token.objects.create(user=self.regular_user)

		document = Document.objects.create(
			title='Policy',
			file=SimpleUploadedFile('policy.txt', b'policy body'),
			uploaded_by=self.regular_profile,
		)

		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {regular_token.key}')
		share_response = cast(Response, self.api_client.post(
			reverse('document-share', args=[document.pk]),
			{'group_name': self.group.name},
			format='json',
		))
		self.assertIn(share_response.status_code, {200, 201})
		self.assertTrue(DocumentShare.objects.filter(document=document, shared_with_group=self.group).exists())

		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.recipient_token.key}')
		list_response = cast(Response, self.api_client.get(reverse('document-list')))
		response_data = cast(list[dict[str, object]], list_response.data)
		self.assertEqual(list_response.status_code, 200)
		self.assertEqual(len(response_data), 1)
		self.assertEqual(response_data[0]['id'], document.pk)

	def test_can_view_permissions_for_user_by_email(self):
		"""Test that GET /api/permissions/?email=... works."""
		view_permission = Permission.objects.get(codename='view_document', content_type__model='document')
		self.regular_user.user_permissions.add(view_permission)

		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
		response = cast(Response, self.api_client.get(
			reverse('auth-assign-document-permissions'),
			{'email': self.regular_user.email},
		))
		self.assertEqual(response.status_code, 200)
		response_data = cast(dict[str, Any], response.data)
		self.assertEqual(response_data['email'], self.regular_user.email)

	def test_add_member_to_group_by_email(self):
		"""Test adding a user to a group using their email."""
		new_user = User.objects.create_user(
			username='newmember',
			email='newmember@example.com',
			password='strongpass123',
		)
		new_profile = UserProfile.objects.create(user=new_user, created_by=self.admin_profile)

		self.api_client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
		response = cast(Response, self.api_client.post(
			reverse('group-add-member', args=[self.group.pk]),
			{'email': 'newmember@example.com'},
			format='json',
		))
		self.assertEqual(response.status_code, 200)
		self.assertIn(new_profile, self.group.members.all())
