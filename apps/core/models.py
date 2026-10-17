from django.db import models


class CebuLocation(models.Model):
    """Approved service area locations in Cebu."""
    class LocationType(models.TextChoices):
        CITY = 'city', 'City'
        MUNICIPALITY = 'municipality', 'Municipality'

    name = models.CharField(max_length=100, unique=True)
    location_type = models.CharField(max_length=20, choices=LocationType.choices)
    province = models.CharField(max_length=100, default='Cebu')
    is_active = models.BooleanField(default=True)  # Admin can disable areas
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    class Meta:
        db_table = 'cebu_locations'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_location_type_display()}), {self.province}'


class AuditLog(models.Model):
    """Audit trail for sensitive platform actions."""
    actor_email = models.EmailField(blank=True)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.actor_email} {self.action} {self.resource_type} at {self.timestamp}'
