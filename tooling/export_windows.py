import importlib.util,os,pathlib,sys
spec=importlib.util.spec_from_file_location('candidate_export',pathlib.Path(__file__).with_name('prepare_windows.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=pathlib.Path.cwd()
print(module.prepare(os.environ['APPROVED_SHA'],check_payload_only='--check-payload-only' in sys.argv))
