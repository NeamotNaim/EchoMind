"""Memoir routes — view the finished memoir and download the PDF."""

import json
import logging
import os
from datetime import datetime

from flask import (
    Blueprint, current_app, jsonify, render_template, send_file, abort
)

from models.database import Memoir, Session, db

logger = logging.getLogger(__name__)
memoir_bp = Blueprint("memoir", __name__)


# ----------------------------------------------------------------------
# Demo content
# ----------------------------------------------------------------------
DEMO_CHAPTERS = {
    "Childhood & Family Origins": (
        "I was born in 1938 in a small terraced house in Cardiff, the year before "
        "the war began, and I have only ever known the world to be a place that "
        "had to be rebuilt. My father worked the docks. He left the house before "
        "I was awake and came home when the lamps were lit, smelling of rope and "
        "the sea, and he would lift me onto his lap and ask me, in his careful "
        "Welsh lilt, what I had learned that day. My mother baked bread every "
        "Friday. I can still feel the warmth of the loaves on the table, and the "
        "way she would let me press my thumb into the soft top of one before it "
        "went into the oven. We were not rich, but we were never hungry, and the "
        "street was full of children whose parents looked out for all of us as "
        "if we were their own. We played in the cobbled lanes until the lamplighter "
        "came, kicking a ball made of rags, telling stories about pirates and "
        "soldiers, before any of us had ever seen a television. In the evenings, "
        "when the air-raid warnings had long faded and the city was learning to "
        "be itself again, my mother would read to us from a battered copy of "
        "Grimm's Fairy Tales, and I learned early that stories were a way of "
        "holding onto a world that might otherwise slip away. I think of that "
        "house often. It is gone now, replaced by a block of flats that looks "
        "out over the same streets where we played. But the bread, the smell of "
        "it, and the sound of my father's voice asking me what I had learned — "
        "those are the things I keep."
    ),
    "Love & Relationships": (
        "I met my husband at a Saturday dance in 1959, in a church hall that had "
        "been strung with paper lanterns for the occasion. He was wearing a suit "
        "that his mother had clearly made him wear, and he had the shyest smile I "
        "had ever seen on a young man. I had gone with my friend Gwen, mostly "
        "because I had nothing better to do, and I had not expected to meet "
        "anyone, let alone the person I would spend the next fifty-four years "
        "with. He asked me to dance and I said yes before I had decided whether I "
        "wanted to, and we laughed about it for the rest of our lives. He was a "
        "quiet man, my husband. He did not say much, but what he said was always "
        "true, and when he put his hand on mine in the cinema I felt, for the "
        "first time, that the world was a place where I was meant to be. We were "
        "married the following spring, in the same church where my mother had "
        "been christened, and we honeymooned in a guesthouse in Tenby where the "
        "landlady called us 'the children' for the entire weekend. We had our "
        "disagreements, of course. We had the kind of disagreements that come "
        "from sharing a small house in a small life for a long time. But we had "
        "a habit, on the worst evenings, of sitting in the kitchen with a cup of "
        "tea between us, and just being there, and somehow that was always "
        "enough. He died in 2013, on a Tuesday, with my hand in his, and the "
        "nurse who came in said she had rarely seen two people so clearly in love. "
        "I have not danced since."
    ),
    "Career & Life's Work": (
        "I became a primary school teacher in 1961, the same year I had my first "
        "child, and I taught for thirty-seven years. I taught in the same school "
        "in Llandaff for almost all of that time, walking the same streets to "
        "work each morning, knowing every paving stone, every crack in the wall, "
        "every child who came through the gate. I taught reading and arithmetic, "
        "yes, but mostly I tried to teach the children to look at one another "
        "and to listen. I wanted them to know that what they had to say mattered, "
        "and that the world would be a better place if they said it kindly. I "
        "kept every class photograph in a brown leather album, and on the days "
        "when I was tired, I would take it down and remember the children whose "
        "names I still knew. Many of them wrote to me, in the years after they "
        "left, to tell me about their own children, their own lives. Some of them "
        "became teachers themselves. One of them became a poet, and she sent me a "
        "copy of her first book with a dedication that I have read so often the "
        "page is soft at the corners. I never felt I was brilliant at what I did. "
        "I was tired, often, and underpaid, and sometimes I went home at night "
        "and wondered if I had done any good at all. But the letters, the albums, "
        "the photographs of grown men and women with their own children in their "
        "arms, those tell me something different. They tell me that I was there, "
        "and that being there was enough."
    ),
    "Wisdom & Advice for the Future": (
        "I have grandchildren now, four of them, and I think of them often, "
        "and I worry for them, the way all grandparents worry, because the "
        "world they are growing into is not the world I grew up in. But if I "
        "could leave them with a few small things, they would be these. Be "
        "kind to the people who serve you in shops and cafés and on buses, "
        "because the world is held together by their patience, and they are "
        "doing their best. Read books. Not on a screen, if you can help it. "
        "Hold a book in your hands and feel the weight of it, and let the "
        "pages turn under your thumb. Have one true friend, and be that "
        "friend in return. Do not be afraid of hard work, but do not let work "
        "become the whole of who you are. Remember that the people you love "
        "will not be here forever, and the time you spend with them is the "
        "only time there is. Take a long walk, often, with no destination in "
        "mind. And when you are old, like me, sit sometimes and remember the "
        "people who are gone, and be glad, be very glad, that you knew them."
    ),
}


def _seed_demo_memoir() -> None:
    """Insert the demo memoir into the DB if it isn't already there."""
    from models.database import Memoir, Session
    import uuid as _uuid

    # Check if demo memoir already exists
    existing = Memoir.query.filter_by(share_token="demo").first()
    if existing is not None:
        return

    sess = Session.query.filter_by(subject_name="Margaret Rose Williams").first()
    if sess is None:
        sess = Session(
            id="demo-session",
            subject_name="Margaret Rose Williams",
            subject_birth_year=1938,
            subject_location="Cardiff, Wales",
            status="complete",
        )
        db.session.add(sess)
        db.session.commit()

    pdf_path = os.path.join("static", "memoirs", "demo.pdf")
    qr_path = os.path.join("static", "qrcodes", "demo.png")

    # Generate a demo PDF on the fly so the link works
    try:
        from utils.pdf_generator import MemoirPDFGenerator

        pdf_gen = MemoirPDFGenerator()
        pdf_gen.generate(
            "Margaret Rose Williams", 1938, DEMO_CHAPTERS, pdf_path
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Demo PDF generation failed: %s", exc)
        pdf_path = ""

    try:
        from utils.qr_generator import QRGenerator

        qr_gen = QRGenerator()
        share_url = f"{current_app.config.get('BASE_URL', 'http://localhost:5000')}/memoir/demo"
        qr_gen.generate(share_url, qr_path)
    except Exception as exc:  # pragma: no cover
        logger.warning("Demo QR generation failed: %s", exc)
        qr_path = ""

    memoir = Memoir(
        session_id=sess.id,
        chapters_json=json.dumps(DEMO_CHAPTERS, ensure_ascii=False),
        pdf_path=pdf_path or None,
        qr_path=qr_path or None,
        share_token="demo",
    )
    db.session.add(memoir)
    db.session.commit()


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@memoir_bp.route("/memoir/<share_token>")
def view_memoir(share_token: str):
    """Render the memoir viewer for a share token."""
    memoir = Memoir.query.filter_by(share_token=share_token).first()
    if memoir is None:
        # Try the demo route explicitly
        if share_token == "demo":
            try:
                _seed_demo_memoir()
                memoir = Memoir.query.filter_by(share_token="demo").first()
            except Exception as exc:
                logger.error("Demo seed failed: %s", exc)
        if memoir is None:
            return (
                render_template("base.html", content="<p>Memoir not found.</p>"),
                404,
            )

    try:
        chapters = json.loads(memoir.chapters_json or "{}")
    except json.JSONDecodeError:
        chapters = {}

    sess = Session.query.get(memoir.session_id)
    subject_name = sess.subject_name if sess else "A Life Story"
    birth_year = sess.subject_birth_year if sess else None

    # Convert enriched memory dicts back to plain strings if needed
    display_chapters: dict = {}
    for k, v in chapters.items():
        if isinstance(v, list):
            display_chapters[k] = "\n\n".join(
                (m.get("original") if isinstance(m, dict) else str(m)) for m in v
            )
        else:
            display_chapters[k] = str(v)

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
