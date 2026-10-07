"""Extraction must keep every order line, or nothing downstream can get it right."""
import json
import re
from pathlib import Path

import pytest

from app.core.text_extract import extract

GENERATED = Path("/data/eval/generated")
CASES = sorted(GENERATED.glob("*.json"))[:60]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@pytest.mark.parametrize("label_path", CASES, ids=lambda p: p.stem)
def test_every_line_survives_extraction(label_path):
    label = json.loads(label_path.read_text())
    text, ocr_used = extract(GENERATED / label["document"])
    assert not ocr_used                      # generated PDFs have a text layer
    page = norm(text)
    for ln in label["lines"]:
        assert norm(ln["raw"][:90]) in page, ln["raw"]   # PDFs print at most 90 chars


def test_rejects_unknown_type(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    with pytest.raises(ValueError):
        extract(f)
