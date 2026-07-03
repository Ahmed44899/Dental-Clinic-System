from rest_framework import serializers
import cloudinary.uploader
from django.conf import settings
from .models import XRay


class XRaySerializer(serializers.ModelSerializer):
    # Write-only — accept image file in requests but don't return raw path
    image_file = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = XRay
        fields = [
            'id', 'patient', 'appointment',
            'image_file', 'image_local', 'image_cloud',
            'storage_type', 'source', 'external_id',
            'taken_at', 'description', 'imported_at',
        ]
        read_only_fields = ['id', 'image_local', 'image_cloud', 'imported_at', 'source']

    def validate(self, data):
        patient = data.get('patient')
        appointment = data.get('appointment')
        if appointment and patient and appointment.patient_id != patient.id:
            raise serializers.ValidationError({
                'appointment': 'This appointment belongs to a different patient.'
            })
        return data

    def create(self, validated_data):
        image_file = validated_data.pop('image_file', None)

        # Save locally using Django's ImageField
        if image_file:
            validated_data['image_local'] = image_file
            validated_data['storage_type'] = 'local'

            # Cloud upload is opt-in because X-rays contain sensitive medical data.
            try:
                if not settings.XRAY_CLOUD_UPLOAD_ENABLED:
                    raise RuntimeError('Cloud X-ray upload is disabled')
                upload_result = cloudinary.uploader.upload(
                    image_file,
                    folder=f"dental_clinic/xrays/patient_{validated_data['patient'].id}",
                    resource_type='image'
                )
                validated_data['image_cloud'] = upload_result['secure_url']
                validated_data['storage_type'] = 'both'  # saved in both places
            except Exception:
                # If cloud upload fails, local copy is still safe
                pass

        validated_data['source'] = 'manual'
        return super().create(validated_data)
