from rest_framework import permissions


class IsPlatformAdmin(permissions.BasePermission):
    """
    Allows access strictly to active users with role == 'platform_admin'.
    Does NOT grant bypass via Django is_superuser or is_staff alone.
    """
    message = 'Platform Administrator privileges are required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, 'role', None) == 'platform_admin'
        )


class IsShelterAdmin(permissions.BasePermission):
    """
    Allows access strictly to active users with role == 'shelter_admin'.
    Platform Administrators and Adopters are explicitly denied.
    """
    message = 'Shelter Administrator privileges are required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, 'role', None) == 'shelter_admin'
        )


class IsAdopter(permissions.BasePermission):
    """
    Allows access strictly to active users with role == 'adopter'.
    """
    message = 'A registered adopter account is required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, 'role', None) == 'adopter'
        )


class IsAssignedShelterAdmin(permissions.BasePermission):
    """
    Object-level permission ensuring a Shelter Administrator can only access
    resources belonging to their assigned shelter.
    """
    message = 'You do not have permission to access another shelter\'s records.'

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and getattr(user, 'role', None) == 'shelter_admin'):
            return False
        shelter = getattr(obj, 'shelter', obj)
        return (
            shelter.owner_id == user.id
            or shelter.administrators.filter(id=user.id).exists()
        )

