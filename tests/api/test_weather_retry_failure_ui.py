"""Failure wording distinguishes a first search from a refusal retry."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("after_refusal", [False, True])
@pytest.mark.parametrize("reason", ["Météo temporairement indisponible", "Données météo rejetées", "Connexion impossible", "L’analyse n’a pas répondu après 90 secondes"])
def test_failure_wording_keeps_reason_without_inventing_a_refusal(after_refusal, reason):
    source = (ROOT / "astropilot/web/app.js").read_text()
    helper = source[source.index("function analysisFailureMessage("):source.index("async function loadTonight(")]
    program = "const assert=require('node:assert/strict');\n" + helper + f"""
const text=analysisFailureMessage({json.dumps(reason)}, {str(after_refusal).lower()});
assert(text.includes({json.dumps(reason)}));
assert(text.includes('Aucun nouveau résultat n’a été obtenu'));
assert(text.includes('Vos horaires et vos réglages sont conservés'));
assert.equal(text.includes('Le refus précédent n’a pas été réévalué'), {str(after_refusal).lower()});
"""
    result = subprocess.run([shutil.which("node"), "-"], input=program, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_existing_alert_is_unique_and_precedes_all_form_controls():
    html = (ROOT / "astropilot/web/index.html").read_text()
    assert html.count('id="availability-error"') == 1
    assert html.index('id="availability-title"') < html.index('id="availability-error"') < html.index('id="review-step"') < html.index('id="availability-form"')
