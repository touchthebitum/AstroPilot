"""Exercise the progress editor's loss-prevention interactions in JavaScript."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "astropilot/web/app.js"


@pytest.mark.parametrize("ui_mode", ["simple", "pro"])
def test_field_transition_and_unsaved_editor_guards(tmp_path, ui_mode):
    engine = shutil.which("osascript") or shutil.which("node")
    if not engine:
        pytest.skip("JavaScript runtime unavailable")
    source = SCRIPT.read_text(encoding="utf-8")
    functions = source[source.index("function readableTargetName("):source.index("function savedMissionLabel(")]
    functions += source[source.index("function progressEditorSnapshot("):
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
const appliedUiMode = "pro";
const editor = new Element("div");
const document = {
  documentElement: {dataset:{}},
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
  const goal = editor.all().find(x => x.tag === "fieldset" && x.dataset.goalDuration === "true");
  assert(goal && goal.dataset.proOnly !== "true", "the total goal must be editable in Simple as well as Pro");
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
    program = harness.replace('const appliedUiMode = "pro";', f'const appliedUiMode = "{ui_mode}";') + functions + "\ncheck();\n"
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


def test_goal_hours_minutes_preserve_original_precision_and_validate_edits(tmp_path):
    source = SCRIPT.read_text()
    functions = source[source.index('function progressInput('):source.index('async function openProjectProgress(')]
    program = r'''
const assert=require('node:assert/strict');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.value='';}
 append(...items){this.children.push(...items);}
 addEventListener(name,fn){this.listeners[name]=fn;}
 dispatchEvent(e){this.listeners[e.type]?.(e);}
 all(){return this.children.flatMap(c=>[c,...c.all()]);}
 querySelector(tag){return this.all().find(c=>c.tag===tag)||null;}
}
const document={createElement:tag=>new Element(tag)};
function inspect(value){const root=projectGoalInput(value),inputs=root.all().filter(x=>x.tag==='input');return Object.fromEntries(inputs.map(x=>[x.dataset.field,x]));}
const original=40/60;const f=inspect(original);
assert.equal(Number(f.goal_hours.value),0);assert.equal(Number(f.goal_minutes.value),40);
assert.equal(f.target_hours.value,original,'Opening and saving unchanged must retain full precision');
f.goal_minutes.value='45';f.goal_minutes.dispatchEvent(new Event('input'));assert.equal(Number(f.target_hours.value),.75);
f.goal_minutes.value='60';f.goal_minutes.dispatchEvent(new Event('input'));assert(Number.isNaN(Number(f.target_hours.value)));
const unknown=inspect(undefined);assert.equal(unknown.target_hours.value,'');assert.equal(unknown.goal_hours.value,'');
const fine=1.123456789123;assert.equal(inspect(fine).target_hours.value,fine);
const editable=inspect(fine);
editable.goal_hours.dispatchEvent(new Event('input'));assert.equal(editable.target_hours.value,fine);
editable.goal_minutes.dispatchEvent(new Event('input'));assert.equal(editable.target_hours.value,fine);
let goal=fine;
for(let i=0;i<4;i++) {
 const forward=inspect(JSON.parse(JSON.stringify(goal)));
 forward.goal_hours.value='2';forward.goal_hours.dispatchEvent(new Event('input'));
 assert.equal(Number(forward.target_hours.value),2.123456789123);
 const back=inspect(JSON.parse(JSON.stringify(Number(forward.target_hours.value))));
 back.goal_hours.value='1';back.goal_hours.dispatchEvent(new Event('input'));
 goal=JSON.parse(JSON.stringify(Number(back.target_hours.value)));assert.equal(goal,fine);
}
const boundary=inspect(1.9999999999);
assert.equal(Number(boundary.goal_hours.value),1,'display must not carry rounded minutes into another canonical hour');
boundary.goal_hours.dispatchEvent(new Event('input'));assert.equal(Number(boundary.target_hours.value),1.9999999999);
const unrepresentable=inspect(1.1234567891234567);
unrepresentable.goal_hours.value='2';unrepresentable.goal_hours.dispatchEvent(new Event('input'));
assert.equal(Number(unrepresentable.target_hours.value),1.1234567891234567);
assert.equal(unrepresentable.target_hours.dataset.precisionLoss,'true');
const exact=inspect(3);assert.equal(Number(exact.goal_hours.value),3);assert.equal(Number(exact.goal_minutes.value),0);
'''
    result = subprocess.run([shutil.which('node'), '-e', functions + program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
