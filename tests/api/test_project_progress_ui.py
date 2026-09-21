"""Exercise the progress editor's loss-prevention interactions in JavaScript."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


def test_field_transition_and_unsaved_editor_guards(tmp_path):
    engine = shutil.which("osascript") or shutil.which("node")
    if not engine:
        pytest.skip("JavaScript runtime unavailable")
    source = SCRIPT.read_text(encoding="utf-8")
    functions = source[source.index("function progressEditorSnapshot("):
                       source.index("function prefillConfiguration()")]
    harness = r'''
const assert = (condition, message) => { if (!condition) throw new Error(message); };
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {};
    this.value = ""; this.hidden = false; this.textContent = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  all() { return this.children.flatMap((child) => [child, ...child.all()]); }
  querySelector(selector) {
    return this.all().find((child) => selector[0] === "#"
      ? child.id === selector.slice(1) : child.tag === selector) || null;
  }
  querySelectorAll(selector) {
    if (selector === "fieldset[data-intent-id]")
      return this.all().filter((child) => child.tag === "fieldset" && child.dataset.intentId);
    if (selector === "input, select")
      return this.all().filter((child) => child.tag === "input" || child.tag === "select");
    return [];
  }
}
const editor = new Element("div");
const document = {
  createElement: (tag) => new Element(tag),
  querySelector: (selector) => selector === "#project-progress-editor" ? editor : null,
};
let answer = false;
let prompts = [];
const window = {confirm: (message) => { prompts.push(message); return answer; }};
const state = {
  progressEditor: {
    project_id: "Sh2-129", imaging_field_id: "old",
    imaging_fields: [
      {imaging_field_id: "old", display_name: "Old", acquisition_intents: [
        {acquisition_intent_id: "old_intent", filter_type: "Ha"}]},
      {imaging_field_id: "new", display_name: "New", acquisition_intents: [
        {acquisition_intent_id: "new_intent", filter_type: "OIII"}]},
    ],
    acquisition_intent_progress: [{acquisition_intent_id: "old_intent", acquired_frames: 0, exposure_seconds: 300}],
    acquisition_intent_targets: [{acquisition_intent_id: "old_intent", target_hours: 2}],
  },
  progressEditorBaseline: null,
};
function check() {
  renderProjectProgressEditor();
  const select = editor.querySelector("#project-imaging-field");
  assert(confirmDiscardProjectProgress(), "pristine editor should not need confirmation");
  const firstInput = editor.querySelector("input");
  const original = firstInput.value;
  firstInput.value = "7";
  assert(!confirmDiscardProjectProgress(), "edited input must be guarded");
  select.value = "new";
  select.listeners.change();
  assert(select.value === "old", "cancel must restore the previous field");
  assert(firstInput.value === "7", "cancel must preserve unsaved input");
  assert(editor.querySelectorAll("fieldset[data-intent-id]")[0].dataset.intentId === "old_intent", "cancel must preserve inputs");
  assert(prompts.some((message) => message.includes("avancement et les objectifs")
    && message.includes("old_intent") && message.includes("modifications non enregistrées")), "warning must explain both losses");
  firstInput.value = original;
  answer = true;
  select.value = "new";
  select.listeners.change();
  assert(editor.querySelectorAll("fieldset[data-intent-id]")[0].dataset.intentId === "new_intent", "confirmed transition must show new intents");
  answer = false;
  assert(!confirmDiscardProjectProgress(), "leaving a changed field must prompt");
  assert(!renderProjects(), "cancel must prevent project rerender");
  assert(state.progressEditor !== null && !editor.hidden, "rerender cancellation must preserve editor");
  return "ok";
}
'''
    # The tiny DOM harness checks the real event listener, including cancellation.
    program = harness + functions + "\ncheck();\n"
    file = tmp_path / "progress_ui.js"
    file.write_text(program, encoding="utf-8")
    command = [engine, "-l", "JavaScript", str(file)] if Path(engine).name == "osascript" else [engine, str(file)]
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_wizard_navigation_guards_unsaved_progress():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if (renderProjects()) setView("projects")' in source
    assert 'if (!confirmDiscardProjectProgress()) return;\n  showFormError("");' in source
    assert 'button.dataset.back !== "projects" && !confirmDiscardProjectProgress()' in source
    assert 'if (!discardConfirmed && !confirmDiscardProjectProgress()) return;' in source
