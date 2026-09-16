"""Certificate PDF generation (reportlab, CJK-safe via built-in CID fonts).

Uses reportlab's bundled STSong-Light CID font, so Chinese text renders
without shipping any external font files.
"""

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

#: Built-in CJK font shipped with reportlab (no external font file needed).
_CJK_FONT = 'STSong-Light'
_registered = False


def _font():
    global _registered
    if not _registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        _registered = True
    return _CJK_FONT


def generate_certificate_pdf(student_exam, verification_code: str) -> bytes:
    """Render the certificate PDF for a passed exam attempt; return bytes.

    Args:
        student_exam: the passed StudentExam.
        verification_code: the certificate's verification code (created and
            stored by the caller before rendering, since the PDF embeds it).
    """
    exam = student_exam.exam
    student = student_exam.student

    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    font = _font()

    # Outer + inner border
    c.setStrokeColor(HexColor('#1a5276'))
    c.setLineWidth(2)
    c.rect(30, 30, page_w - 60, page_h - 60)
    c.setStrokeColor(HexColor('#d4ac0d'))
    c.setLineWidth(1)
    c.rect(40, 40, page_w - 80, page_h - 80)

    # Title
    c.setFillColor(HexColor('#1a5276'))
    c.setFont(font, 34)
    c.drawCentredString(page_w / 2, page_h - 120, '结 业 证 书')

    c.setFont(font, 12)
    c.drawCentredString(page_w / 2, page_h - 155, 'CERTIFICATE OF COMPLETION')

    # Body
    c.setFillColor(HexColor('#212121'))
    c.setFont(font, 16)
    lines = [
        f'兹证明学员 {student.get_full_name() or student.username}',
        f'在《{exam.title}》考试中取得 {student_exam.score} 分',
        f'（通过分数线 {exam.passing_score} 分），成绩合格，特发此证。',
    ]
    y = page_h - 220
    for line in lines:
        c.drawCentredString(page_w / 2, y, line)
        y -= 36

    # Issued date + verification code
    c.setFont(font, 12)
    c.setFillColor(HexColor('#555555'))
    issued = student_exam.end_time or student_exam.start_time
    c.drawCentredString(page_w / 2, y - 10, f'颁发日期：{issued:%Y 年 %m 月 %d 日}')

    c.drawCentredString(
        page_w / 2, y - 40,
        f'证书验证码：{verification_code}（请妥善保管，用于证书真伪查询）')

    c.showPage()
    c.save()
    return buf.getvalue()
