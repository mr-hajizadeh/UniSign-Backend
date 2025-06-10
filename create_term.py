import os
import django

# تنظیم متغیر محیطی Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UniSign.settings')
django.setup()

# حالا می‌توانیم از مدل‌ها استفاده کنیم
from unisign.models import Term

def create_term():
    try:
        # ایجاد ترم جدید
        term = Term.objects.create(name='۱۴۰۳-۲')
        print(f"ترم {term.name} با موفقیت ایجاد شد.")
    except Exception as e:
        print(f"خطا در ایجاد ترم: {str(e)}")

if __name__ == '__main__':
    create_term() 