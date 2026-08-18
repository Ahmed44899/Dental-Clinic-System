import cloudinary.uploader
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.urls import reverse
from rest_framework import serializers

from .models import XRay


class XRaySerializer(serializers.ModelSerializer):
    """Validate uploads and expose only permission-checked image URLs."""

    image_file = serializers.ImageField(write_only=True, required=False)
    image_local = serializers.SerializerMethodField()
    image_cloud = serializers.SerializerMethodField()

    class Meta:
        model = XRay
        fields = [
            'id', 'patient', 'appointment',
            'image_file', 'image_local', 'image_cloud',
            'storage_type', 'source', 'external_id',
            'taken_at', 'description', 'imported_at',
        ]
        read_only_fields = [
            'id', 'image_local', 'image_cloud', 'storage_type',
            'source', 'external_id', 'imported_at',
        ]

    def _protected_image_url(self, obj):
        path = reverse('xray-image', kwargs={'pk': obj.pk})
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path

    def get_image_local(self, obj):
        return self._protected_image_url(obj) if obj.image_local else ''

    def get_image_cloud(self, obj):
        has_cloud_copy = bool(obj.cloud_public_id or obj.image_cloud)
        return self._protected_image_url(obj) if has_cloud_copy else ''

    def validate_image_file(self, image_file):
        if image_file.size > settings.XRAY_MAX_UPLOAD_SIZE:
            max_mb = settings.XRAY_MAX_UPLOAD_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                f'X-ray images must be {max_mb} MB or smaller.'
            )

        content_type = (getattr(image_file, 'content_type', '') or '').lower()
        if content_type not in settings.XRAY_ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError('Only JPEG and PNG images are accepted.')

        try:
            image_file.seek(0)
            with Image.open(image_file) as image:
                if image.format not in {'JPEG', 'PNG'}:
                    raise serializers.ValidationError(
                        'The file contents must be a JPEG or PNG image.'
                    )
                if image.width * image.height > settings.XRAY_MAX_IMAGE_PIXELS:
                    raise serializers.ValidationError(
                        'The image dimensions are too large to process safely.'
                    )
                image.verify()
        except serializers.ValidationError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
            raise serializers.ValidationError('The uploaded file is not a valid image.')
        finally:
            image_file.seek(0)
        return image_file

    def validate(self, data):
        patient = data.get('patient')
        appointment = data.get('appointment')
        if appointment and patient and appointment.patient_id != patient.id:
            raise serializers.ValidationError({
                'appointment': 'This appointment belongs to a different patient.'
            })
        if self.instance is None and not data.get('image_file'):
            raise serializers.ValidationError({
                'image_file': 'Choose a JPEG or PNG X-ray image to upload.'
            })
        return data

    def create(self, validated_data):
        image_file = validated_data.pop('image_file')
        validated_data['image_local'] = image_file
        validated_data['storage_type'] = 'local'
        cloud_public_id = ''

        if settings.XRAY_CLOUD_UPLOAD_ENABLED:
            try:
                upload_result = cloudinary.uploader.upload(
                    image_file,
                    folder=f"dental_clinic/xrays/patient_{validated_data['patient'].id}",
                    resource_type='image',
                    type='authenticated',
                )
                cloud_public_id = upload_result['public_id']
                validated_data['cloud_public_id'] = cloud_public_id
                validated_data['image_cloud'] = upload_result.get('secure_url', '')
                validated_data['storage_type'] = 'both'
            except Exception:
                if not settings.DEBUG:
                    raise serializers.ValidationError({
                        'image_file': 'Persistent image upload failed. Please try again.'
                    })
            finally:
                image_file.seek(0)

        validated_data['source'] = 'manual'
        try:
            return super().create(validated_data)
        except Exception:
            if cloud_public_id:
                cloudinary.uploader.destroy(
                    cloud_public_id,
                    resource_type='image',
                    type='authenticated',
                    invalidate=True,
                )
            raise
