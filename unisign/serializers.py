from rest_framework import serializers
from .models import StudentSignature

class StudentSignatureSerializer(serializers.ModelSerializer):
    created_at_jalali = serializers.SerializerMethodField(read_only=True)
    signed_by_fullname = serializers.SerializerMethodField(read_only=True)
    signature_image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = StudentSignature
        fields = ['id', 'student', 'course', 'signed_by', 'signed_by_fullname', 'signature_image', 'signature_image_url', 'created_at', 'created_at_jalali']
        read_only_fields = ['signed_by', 'created_at', 'created_at_jalali', 'signed_by_fullname', 'signature_image_url']

    def get_created_at_jalali(self, obj):
        return obj.created_at_jalali()

    def get_signed_by_fullname(self, obj):
        return f"{obj.signed_by.first_name} {obj.signed_by.last_name}".strip()

    def get_signature_image_url(self, obj):
        request = self.context.get('request')
        if obj.signature_image and hasattr(obj.signature_image, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.signature_image.url)
            return obj.signature_image.url
        return None

    def create(self, validated_data):
        # Get the user from the request context
        request = self.context.get('request')
        if request and request.user:
            validated_data['signed_by'] = request.user

        # Get existing signature if any
        existing_signature = StudentSignature.objects.filter(
            student=validated_data['student'],
            course=validated_data['course']
        ).first()

        if existing_signature:
            # Update existing signature
            existing_signature.signature_image = validated_data['signature_image']
            existing_signature.signed_by = validated_data['signed_by']
            existing_signature.save()
            return existing_signature
        else:
            # Create new signature
            return super().create(validated_data)

    def update(self, instance, validated_data):
        # Update the signature image and signed_by
        instance.signature_image = validated_data.get('signature_image', instance.signature_image)
        instance.signed_by = validated_data.get('signed_by', instance.signed_by)
        instance.save()
        return instance 