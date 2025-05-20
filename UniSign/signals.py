# فایل signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Course
from .utils import extract_students_from_pdf

@receiver(post_save, sender=Course)
def process_pdf_after_save(sender, instance, created, **kwargs):
    if instance.pdf_file:
        students = extract_students_from_pdf(instance)
        # حالا شما می‌توانید اطلاعات دانشجویان را در مدل دیگری ذخیره کنید یا به هر نحوی از آن استفاده کنید.
        print(students)
