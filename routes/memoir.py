"""Memoir routes — view the finished memoir and download the PDF.

The `/memoir/demo` route renders Margaret Williams's pre-written chapters
directly (no DB lookup) per the build spec.
"""

import io
import json
import logging
import os
import tempfile
from datetime import datetime

from flask import (
    Blueprint, abort, render_template, send_file
)

from models.database import Memoir, Session, db
from utils.pdf_generator import MemoirPDFGenerator

logger = logging.getLogger(__name__)
memoir_bp = Blueprint("memoir", __name__)


# ----------------------------------------------------------------------
# Demo content — hardcoded per the build spec
# ----------------------------------------------------------------------
DEMO_CHAPTERS = {
    "Childhood & Family Origins": (
        "I was born in 1938 in a small terraced house on Splott Road in Cardiff, "
        "the year before the war began, and I have only ever known the world to "
        "be a place that had to be rebuilt. My father, Thomas, worked the docks. "
        "He left the house before I was awake and came home when the lamps were "
        "lit, smelling of coal and sea salt, and he would lift me onto his lap "
        "and ask me, in his careful Welsh lilt, what I had learned that day. My "
        "mother, Eileen, baked bread every Friday so that the whole street knew "
        "it was Friday. I can still feel the warmth of the loaves on the table, "
        "and the way she would let me press my thumb into the soft top of one "
        "before it went into the oven. I had two sisters and a brother, and we "
        "all shared one bedroom, two to a bed, and the sound of the Taff river "
        "at night was the sound of my childhood, low and steady and always there. "
        "Summer days on Splott Road seemed to last forever. We kicked a ball "
        "made of rags against the gable end of the house, we played hopscotch "
        "in chalk on the pavement, we ran after the ice-cream van like small "
        "animals, and we did not see a television until I was nearly ten. The "
        "street was a community in a way that is hard to describe to people "
        "today — neighbours' doors were always open, and the aunts next door "
        "kept a closer eye on us than our own mother did, and our own mother "
        "kept a closer eye on them. We were poor, of course. Everyone was poor, "
        "in those days, in that street. But the door was open, and there was "
        "always a cup of tea, and that, I think, was a kind of wealth."
    ),
    "Love & Relationships": (
        "I met my husband, David, at a dance at the Rialto Ballroom in 1959. I "
        "was wearing my mother's blue dress, taken in at the waist with safety "
        "pins, and I was so nervous I hardly spoke all evening. He asked me to "
        "dance twice. I said no the first time, out of pure shyness, and I have "
        "always been glad I did, because it gave him the chance to ask again, "
        "and that, I think, is what love often is — a second chance. We were "
        "married the following spring, in 1961, at St. Mary's Church, and the "
        "reception was held in the church hall with sandwiches and a small cake "
        "my mother had iced herself. We had fifty-four years together, which is "
        "a long time by any measure, and a miracle by the measure of those "
        "years. People think love has to be dramatic to be real. It is not. "
        "Sometimes it is just someone making you a cup of tea before you have "
        "asked for one, and leaving it on the table beside you without a word, "
        "and you know, in that small gesture, that you are not alone in the "
        "world. That is what David did, every morning, for fifty-four years. "
        "We had our disagreements, of course. We had the kind of disagreements "
        "that come from sharing a small life in a small house for a long time. "
        "But we had our habit, too, on the worst evenings, of sitting in the "
        "kitchen with a cup of tea between us, and just being there, and somehow "
        "that was always enough. He died in 2013, on a Tuesday, with my hand in "
        "his. I have not danced since."
    ),
    "Career & Life's Work": (
        "I became a primary school teacher in 1961, at Roath Park Primary, the "
        "same year I was married, and I taught for thirty-seven years. I taught "
        "in almost every year group, but I was happiest with the older children, "
        "the ones who were just beginning to understand the world as a place "
        "with words in it. There was a boy in my class, Owen, who could not read "
        "at eight. He sat at the back and coloured in the margins of his books "
        "and refused, politely but absolutely, to look at the words. I sat with "
        "him, after school, three afternoons a week, for a year, and I never "
        "raised my voice, and I never gave up, and by the time he left my class "
        "he was reading novels. I heard from him, twenty years later. He had "
        "become a librarian. He sent me a copy of his favourite book, with a "
        "dedication I keep on the mantelpiece. I have letters like that from "
        "dozens of children, some of them now grandparents themselves. There is "
        "no prouder thing, in this life, than to know that you were useful. The "
        "work was exhausting, and I was paid almost nothing, and I came home "
        "most evenings too tired to cook, and there were years I wondered if I "
        "had done any good at all. But the letters, the photographs of grown "
        "men and women with their own children in their arms, those tell me "
        "something different. They tell me I was there, and that being there "
        "was enough. I retired in 1998, and for the first month I did not know "
        "what to do with the silence. Then I learned to love it, slowly, and "
        "to fill it with the people I loved."
    ),
    "Wisdom & Advice for the Future": (
        "I have grandchildren now, four of them, and I think of them often, "
        "and I worry for them, the way all grandparents worry, because the "
        "world they are growing into is not the world I grew up in. But if I "
        "could leave them with a few small things, they would be these. Write "
        "letters, not texts. A letter is a thing someone can hold, and put in "
        "a drawer, and take out on a hard day, and that is worth more than a "
        "thousand messages. Most arguments, in this life, are not about the "
        "thing you are arguing about. They are about fear — yours, or theirs. "
        "When you remember that, it becomes easier to be gentle. A good life "
        "is not built from grand gestures. It is built from small ordinary days, "
        "done with care. A cup of tea made for someone. A door held open. A "
        "telephone call to a friend you have not spoken to in too long. I hope "
        "you find someone who makes you laugh. I hope you keep that person. I "
        "am proud of you, even for things you have not done yet. I am proud of "
        "you for who you are becoming, which is, I think, a great deal. Take a "
        "long walk, often, with no destination in mind. Read books, in your "
        "hands, with the weight of them in your lap. Be kind to the people who "
        "serve you, in shops and cafés, because the world is held together by "
        "their patience, and they are doing their best. And when you are old, "
        "like me, sit sometimes and remember the people who are gone, and be "
        "glad, be very glad, that you knew them."
    ),
}


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@memoir_bp.route("/memoir/<share_token>")
def view_memoir(share_token: str):
    """Render the memoir viewer for a share token (or 'demo')."""
    if share_token == "demo":
        return _render_demo()

    memoir = Memoir.query.filter_by(share_token=share_token).first()
    if memoir is None:
        return (
            render_template(
                "base.html",
                content=(
                    "<section class='how'><h2 class='section-title'>Memoir not found</h2>"
                    "<p style='text-align:center;'>The link you followed is no longer "
                    "valid. Please check the URL or start a new memoir.</p></section>"
                ),
            ),
            404,
        )

    try:
        chapters = json.loads(memoir.chapters_json or "{}")
    except json.JSONDecodeError:
        chapters = {}

    # If the stored chapters are enriched dicts, flatten them
    display_chapters: dict = {}
    for k, v in chapters.items():
        if isinstance(v, list):
            display_chapters[k] = "\n\n".join(
                (m.get("original") if isinstance(m, dict) else str(m)) for m in v
            )
        else:
            display_chapters[k] = str(v)

    sess = Session.query.get(memoir.session_id)
    subject_name = sess.subject_name if sess else "A Life Story"
    birth_year = sess.subject_birth_year if sess else None

    return render_template(
        "memoir.html",
        subject_name=subject_name,
        birth_year=birth_year,
        chapters=display_chapters,
        share_token=memoir.share_token,
        qr_filename=os.path.basename(memoir.qr_path) if memoir.qr_path else None,
        now=datetime.now().strftime("%B %d, %Y"),
    )


@memoir_bp.route("/memoir/<share_token>/download")
def download_memoir(share_token: str):
    """Serve the PDF file for download."""
    # Special case: the demo memoir is generated on demand from
    # the hardcoded DEMO_CHAPTERS dict (no DB row exists for it).
    if share_token == "demo":
        return _generate_demo_pdf()
    memoir = Memoir.query.filter_by(share_token=share_token).first()
    if memoir is None or not memoir.pdf_path:
        abort(404)
    if not os.path.exists(memoir.pdf_path):
        abort(404)

    sess = Session.query.get(memoir.session_id)
    subject_name = (sess.subject_name if sess else "memoir").replace(" ", "_")
    return send_file(
        memoir.pdf_path,
        as_attachment=True,
        download_name=f"{subject_name}_memoir.pdf",
        mimetype="application/pdf",
    )


def _generate_demo_pdf():
    """Build the Margaret Williams demo PDF on demand and stream it back."""
    # Write to a temp file so ReportLab can close the document properly,
    # then read it back into BytesIO and send it. This avoids the "its too
    # small" issue you'd get from a half-written stream.
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        MemoirPDFGenerator().generate(
            subject_name="Margaret Rose Williams",
            birth_year=1938,
            chapters=DEMO_CHAPTERS,
            output_path=tmp_path,
        )
        with open(tmp_path, "rb") as f:
            data = f.read()
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name="Margaret_Rose_Williams_memoir.pdf",
            mimetype="application/pdf",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ----------------------------------------------------------------------
# Demo helpers
# ----------------------------------------------------------------------
def _render_demo():
    """Render the demo Margaret Williams memoir directly (no DB)."""
    return render_template(
        "memoir.html",
        subject_name="Margaret Rose Williams",
        birth_year=1938,
        chapters=DEMO_CHAPTERS,
        share_token="demo",
        qr_filename=None,
        now=datetime.now().strftime("%B %d, %Y"),
    )