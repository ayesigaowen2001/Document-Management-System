# Document Management System API

This project is a Django + Django REST Framework backend for managing admin profiles, user profiles, groups, and documents.

## What Is Implemented

## 1) Data Models

Defined in DMS/Document_Management_System/models.py:

- AdminProfile
  - user: one-to-one with Django auth user
  - created_at
  - guard in save(): only staff or superuser users can have an AdminProfile

- UserProfile
  - user: one-to-one with Django auth user
  - created_by: optional foreign key to AdminProfile (nullable)
  - created_at

- UserGroup
  - name (unique)
  - description
  - created_by: foreign key to AdminProfile
  - members: many-to-many with UserProfile
  - created_at

- Document
  - title
  - file (upload_to="documents/")
  - uploaded_by: foreign key to UserProfile
  - group: optional foreign key to UserGroup
  - uploaded_at
  - custom permission: share_document

- DocumentShare
  - document: foreign key to Document
  - shared_by: foreign key to UserProfile
  - shared_with_user: optional foreign key to UserProfile
  - shared_with_group: optional foreign key to UserGroup
  - created_at
  - exactly one target is allowed per share record

## 2) Authentication

Token authentication is implemented with rest_framework.authtoken.

- Login endpoint returns token
- All protected endpoints require header:

Authorization: Token <token_value>

Configured in DMS/settings.py:

- rest_framework.authtoken in INSTALLED_APPS
- REST_FRAMEWORK DEFAULT_AUTHENTICATION_CLASSES includes:
  - rest_framework.authentication.TokenAuthentication
  - rest_framework.authentication.SessionAuthentication

Most API views also explicitly set TokenAuthentication.

## 3) Permissions (exact current behavior)

- AuthTokenLoginView
  - AllowAny

- AuthTokenLogoutView
  - IsAuthenticated

- AdminProfileViewSet
  - IsAdminUser

- UserProfileViewSet
  - IsAdminUser

- UserGroupViewSet
  - IsAdminUser

- DocumentViewSet
  - custom DocumentAccessPermission
  - superusers/admins can access all documents
  - regular users need explicit document permissions and only see documents they uploaded or that were shared to them directly or through a group

- SuperuserCreateAdminView
  - IsAuthenticated + runtime check request.user.is_superuser

- CreateUserView
  - IsAuthenticated + runtime check user is superuser OR has admin_profile

- AssignDocumentPermissionsView
  - IsAuthenticated + runtime check user is superuser OR has admin_profile

## 4) API Endpoints

Project root routing:

- /api/ -> includes DMS/Document_Management_System/urls.py

### Authentication endpoints

- POST /api/auth/login/
  - body:

```json
{
  "username": "admin",
  "password": "your_password"
}
```

- response:

```json
{
  "token": "<token>",
  "user_id": 1,
  "username": "admin"
}
```

- POST /api/auth/logout/
  - requires token header

### Account creation endpoints

- POST /api/auth/create-admin/
  - requires token header
  - only superuser allowed
  - body:

```json
{
  "username": "new_admin",
  "email": "new_admin@example.com",
  "password": "strongpass123"
}
```

- creates Django user with is_staff=True
- creates AdminProfile for that user

- POST /api/auth/create-user/
  - requires token header
  - allowed for superuser or admin (user with admin_profile)
  - body:

```json
{
  "username": "new_user",
  "email": "new_user@example.com",
  "password": "strongpass123"
}
```

- creates Django auth user
- creates UserProfile
- created_by is set from request.user.admin_profile when available (otherwise null)

- POST /api/auth/assign-document-permissions/
  - requires token header
  - allowed for superuser or admin (user with admin_profile)
  - body:

```json
{
  "user_id": 2,
  "permissions": ["view_document", "add_document", "share_document"]
}
```

- replaces the target user's current document permissions with the supplied list
- allowed codenames:
  - view_document
  - add_document
  - change_document
  - delete_document
  - share_document

### Resource endpoints (DRF router)

- /api/admin-profiles/
- /api/user-profiles/
- /api/groups/
- /api/documents/

### Custom document action

- POST /api/documents/{id}/share/
  - requires token header
  - requester must have share_document permission unless they are admin/superuser
  - body for direct user share:

```json
{
  "shared_with_user": 3
}
```

- body for group share:

```json
{
  "shared_with_group": 1
}
```

- exactly one of shared_with_user or shared_with_group must be provided

### Custom group action

- POST /api/groups/{id}/add-member/
  - requires token header
  - body:

```json
{
  "user_profile_id": 2
}
```

## 5) Serializers

Defined in DMS/Document_Management_System/serializers.py:

- AdminProfileSerializer
- UserProfileSerializer
- UserGroupSerializer
- UserGroupAddMemberSerializer
- DocumentSerializer
- DocumentShareSerializer
- DocumentPermissionAssignmentSerializer
- AccountCreateSerializer

## 6) Admin Site

Models are registered in DMS/Document_Management_System/admin.py:

- AdminProfile
- UserProfile
- UserGroup
- Document
- DocumentShare

## 7) Environment Configuration

Settings load environment variables from a .env file in project root.

Expected DB variables (from DMS/settings.py):

- DB_ENGINE (default: django.db.backends.postgresql)
- DB_NAME (default: DMS_db)
- DB_USER (default: postgres)
- DB_PASSWORD (default: empty)
- DB_HOST (default: localhost)
- DB_PORT (default: 5432)

## 8) Run the project

1. Activate virtual environment
2. Apply migrations
3. Create superuser
4. Run server

Example:

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

## 9) Notes on document upload

Document.file is a FileField, so create/update document requests should be sent as multipart/form-data when uploading a real file.

For regular users, document actions are permission-based:

- upload requires add_document
- view requires view_document
- update requires change_document
- delete requires delete_document
- share requires share_document

Even with permissions, regular users only operate on their own documents for write actions. Shared documents become visible for reading, but recipients do not automatically gain update, delete, or re-share authority over another user's document.
