# utils.py (تابع استخراج از PDF)
import pymupdf
import re
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .models import Student, Enrollment
import arabic_reshaper
from bidi.algorithm import get_display


def extract_students_from_pdf(course):
    def fix_repeated_digits(text):
        return re.sub(r'(\d)\1{2,}', r'\1', text)

    try:
        file = course.pdf_file.path
        doc = pymupdf.open(file)
        students_by_page = []
        all_students = []

        # استخراج داده‌های متنی
        for page_num, page in enumerate(doc, start=1):
            page_students = []
            tables = page.find_tables()

            if not tables:
                continue

            for table in tables:
                extracted_data = table.extract()

                if not extracted_data:
                    continue

                for row in extracted_data:
                    # اعتبارسنجی داده‌ها
                    if len(row) < 9:  # اگر تعداد ستون‌ها کمتر از حد انتظار باشد
                        continue

                    student_number = str(row[4]).strip()
                    national_id = str(row[3]).strip()

                    if not (student_number.isdigit() and national_id.isdigit()):
                        continue

                    student_data = {
                        "row": fix_repeated_digits(str(row[8])),
                        "exam_place": str(row[7]),
                        "seat_number": str(row[6]),
                        "student_number": student_number,
                        "national_id": national_id,
                        "student_name": get_display(arabic_reshaper.reshape(str(row[2]))),
                        "entry_year": fix_repeated_digits(str(row[1])),
                        "student_image": None,
                    }

                    page_students.append(student_data)
                    all_students.append(student_data)

            students_by_page.append(page_students)

        # استخراج تصاویر
        for page_num, page in enumerate(doc, start=1):
            if page_num - 1 >= len(students_by_page):
                continue

            page_students = students_by_page[page_num - 1]
            images = page.get_images(full=True)

            # رد کردن لوگو در صفحه اول
            skip_logo = (page_num == 1)
            img_iter = (img for idx, img in enumerate(images) if not (skip_logo and idx == 0))

            for student, img in zip(page_students, img_iter):
                xref = img[0]
                base_image = doc.extract_image(xref)

                if not base_image:
                    continue

                img_bytes = base_image.get("image")
                ext = base_image.get("ext", "jpg")
                fname = f"students/{student['national_id']}.{ext}"

                if not default_storage.exists(fname):
                    default_storage.save(fname, ContentFile(img_bytes))

                student["student_image"] = fname

        return all_students  # همیشه لیست برمی‌گرداند (حتی خالی)

    except Exception as e:
        print(f"خطا در استخراج PDF: {str(e)}")
        return []  # جلوگیری از بازگشت None