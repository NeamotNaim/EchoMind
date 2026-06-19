"""PDF memoir generator built on ReportLab Platypus.

Produces a beautiful, professional PDF for a completed memoir with:
- Cover page (subject name, life span, decorative rule, footer date)
- Table of contents
- One chapter per page block, with styled headings
- Page numbers in footer
- Closing page with a brief dedication and QR placeholder
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents

logger = logging.getLogger(__name__)

# Brand colours
NAVY = colors.HexColor("#1a2744")
GOLD = colors.HexColor("#8b6914")
MAHOGANY = colors.HexColor("#4a3728")
LIGHT_RULE = colors.HexColor("#c8b88a")
CREAM = colors.HexColor("#f5f0e8")


class MemoirPDFGenerator:
    """Builds a polished PDF memoir from a chapters dict."""

    def generate(
        self,
        subject_name: str,
        birth_year: Optional[int],
        chapters: Dict[str, str],
        output_path: str,
    ) -> str:
        """Build the PDF and save it to output_path. Returns the path."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            doc = BaseDocTemplate(
                output_path,
                pagesize=A4,
                leftMargin=2.4 * cm,
                rightMargin=2.4 * cm,
                topMargin=2.4 * cm,
                bottomMargin=2.4 * cm,
                title=f"{subject_name} — A Life Story",
                author="EchoMind",
            )

            frame = Frame(
                doc.leftMargin,
                doc.bottomMargin,
                doc.width,
                doc.height,
                id="normal",
                showBoundary=0,
            )

            cover_template = PageTemplate(
                id="cover",
                frames=[frame],
                onPage=self._draw_cover_decor,
            )
            content_template = PageTemplate(
                id="content",
                frames=[frame],
                onPage=self._draw_page_decor,
            )
            doc.addPageTemplates([cover_template, content_template])

            styles = self._build_styles()
            story = self._build_story(subject_name, birth_year, chapters, styles)

            doc.build(story)
            return output_path
        except Exception as exc:
            logger.error("PDF generation failed: %s", exc)
            # Fall back to a plain-text version of the memoir
            return self._fallback_text(subject_name, birth_year, chapters, output_path)

    # ------------------------------------------------------------------
    # Page decoration
    # ------------------------------------------------------------------
    def _draw_cover_decor(self, canv, doc):
        canv.saveState()
        # Cream page background
        canv.setFillColor(CREAM)
        canv.rect(0, 0, *A4, stroke=0, fill=1)
        # Top decorative rule
        canv.setStrokeColor(GOLD)
        canv.setLineWidth(1.4)
        canv.line(2.4 * cm, A4[1] - 3.2 * cm, A4[0] - 2.4 * cm, A4[1] - 3.2 * cm)
        # Bottom decorative rule
        canv.line(2.4 * cm, 2.4 * cm, A4[0] - 2.4 * cm, 2.4 * cm)
        canv.restoreState()

    def _draw_page_decor(self, canv, doc):
        canv.saveState()
        # Cream page background
        canv.setFillColor(CREAM)
        canv.rect(0, 0, *A4, stroke=0, fill=1)
        # Footer rule
        canv.setStrokeColor(LIGHT_RULE)
        canv.setLineWidth(0.6)
        canv.line(2.4 * cm, 1.8 * cm, A4[0] - 2.4 * cm, 1.8 * cm)
        # Page number
        canv.setFont("Helvetica", 9)
        canv.setFillColor(MAHOGANY)
        canv.drawCentredString(A4[0] / 2.0, 1.3 * cm, str(doc.page))
        # Watermark wordmark
        canv.setFont("Helvetica-Oblique", 8)
        canv.setFillColor(GOLD)
        canv.drawRightString(A4[0] - 2.4 * cm, 1.3 * cm, "EchoMind")
        canv.drawString(2.4 * cm, 1.3 * cm, "A Life Story")
        canv.restoreState()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        cover_title = ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=36,
            leading=42,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        cover_subtitle = ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=16,
            leading=22,
            textColor=MAHOGANY,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
        cover_meta = ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=18,
            textColor=MAHOGANY,
            alignment=TA_CENTER,
        )
        toc_heading = ParagraphStyle(
            "TOCHeading",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
        chapter_title = ParagraphStyle(
            "ChapterTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=GOLD,
            spaceBefore=6,
            spaceAfter=14,
        )
        chapter_body = ParagraphStyle(
            "ChapterBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=12,
            leading=20,  # ~1.5 line spacing for 12pt
            textColor=colors.black,
            alignment=TA_JUSTIFY,
            spaceAfter=10,
        )
        closing = ParagraphStyle(
            "Closing",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=14,
            leading=22,
            textColor=MAHOGANY,
            alignment=TA_CENTER,
        )
        return {
            "cover_title": cover_title,
            "cover_subtitle": cover_subtitle,
            "cover_meta": cover_meta,
            "toc_heading": toc_heading,
            "chapter_title": chapter_title,
            "chapter_body": chapter_body,
            "closing": closing,
        }

    # ------------------------------------------------------------------
    # Story assembly
    # ------------------------------------------------------------------
    def _build_story(
        self,
        subject_name: str,
        birth_year: Optional[int],
        chapters: Dict[str, str],
        styles: Dict[str, ParagraphStyle],
    ) -> List:
        story: List = []

        # ---- COVER PAGE ----
        story.append(Spacer(1, 4.5 * cm))
        story.append(Paragraph(f"{subject_name}", styles["cover_title"]))
        story.append(Paragraph("A Life Story", styles["cover_subtitle"]))
        if birth_year:
            story.append(Paragraph(f"Born {birth_year}", styles["cover_meta"]))
        story.append(Spacer(1, 6 * cm))
        story.append(
            Paragraph("A memoir preserved for family", styles["cover_meta"])
        )
        story.append(Spacer(1, 0.5 * cm))
        story.append(
            Paragraph(
                f"Created with EchoMind &middot; {datetime.now().strftime('%B %Y')}",
                styles["cover_meta"],
            )
        )

        # ---- TABLE OF CONTENTS ----
        story.append(PageBreak())
        story.append(Paragraph("Contents", styles["toc_heading"]))
        story.append(Spacer(1, 0.4 * cm))
        toc_style = ParagraphStyle(
            "TOCLevel0",
            parent=styles["chapter_body"],
            fontSize=14,
            leading=26,
            textColor=NAVY,
        )
        toc = TableOfContents()
        toc.levelStyles = [toc_style]
        story.append(toc)
        # Force a page break after TOC placeholder
        story.append(Spacer(1, 0.2 * cm))

        # ---- CHAPTERS ----
        # Switch to content template after cover+TOC by triggering a break
        # (BaseDocTemplate honours template by id when we set doc.afterFlowable)
        story.append(NextPageTemplate("content"))
        story.append(PageBreak())

        for chapter_name, body in chapters.items():
            # Tell TOC to capture this heading
            chapter_heading = Paragraph(
                chapter_name,
                styles["chapter_title"],
            )
            story.append(chapter_heading)
            story.append(Spacer(1, 0.3 * cm))

            paragraphs = self._split_paragraphs(body)
            for p in paragraphs:
                story.append(Paragraph(p, styles["chapter_body"]))
            story.append(PageBreak())

        # ---- CLOSING PAGE ----
        story.append(Paragraph("&nbsp;", styles["closing"]))
        story.append(Spacer(1, 6 * cm))
        story.append(
            Paragraph("This memoir was created with EchoMind.", styles["closing"])
        )
        story.append(Spacer(1, 0.6 * cm))
        story.append(
            Paragraph("May these stories live on.", styles["closing"])
        )
        story.append(Spacer(1, 2 * cm))
        story.append(
            Paragraph(
                f"&mdash; {datetime.now().strftime('%B %d, %Y')}",
                styles["closing"],
            )
        )

        return story

    @staticmethod
    def _split_paragraphs(body: str) -> List[str]:
        """Split a block of prose into clean paragraph strings."""
        if not body:
            return [""]
        # Normalise line endings
        text = body.replace("\r\n", "\n").strip()
        # Split on blank lines
        parts = [p.strip() for p in re_split_paragraphs(text) if p.strip()]
        if not parts:
            return [text]
        return parts

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------
    def _fallback_text(
        self,
        subject_name: str,
        birth_year: Optional[int],
        chapters: Dict[str, str],
        output_path: str,
    ) -> str:
        """Write a plain-text version of the memoir as a last resort."""
        try:
            text_path = os.path.splitext(output_path)[0] + ".txt"
            with open(text_path, "w", encoding="utf-8") as fh:
                fh.write(f"{subject_name} — A Life Story\n")
                if birth_year:
                    fh.write(f"Born {birth_year}\n")
                fh.write("=" * 40 + "\n\n")
                for name, body in chapters.items():
                    fh.write(name.upper() + "\n")
                    fh.write("-" * len(name) + "\n\n")
                    fh.write((body or "").strip() + "\n\n")
            logger.warning(
                "PDF generation failed; wrote plain-text fallback to %s", text_path
            )
            return text_path
        except Exception as exc:  # pragma: no cover
            logger.error("Fallback text write failed: %s", exc)
            return output_path


def re_split_paragraphs(text: str) -> List[str]:
    """Helper: split on blank lines."""
    import re

    return re.split(r"\n\s*\n", text)
