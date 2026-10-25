"""Create a complete synthetic profile for the compiled Windows snapshot smoke test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/api')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = output / 'seed'
    from pytest import MonkeyPatch
    from fastapi.testclient import TestClient
    from astropilot.app import create_app
    from astropilot.profile_backup import create_backup, snapshot
    from astropilot.user_profile import save_user_profile
    from astro_score import build_durable_tonight_application_service
    from test_tonight_api import lineage_client, lineage_selection_payload, DEFAULT_WEATHER_REFERENCE_TIME, valid_profile, LINEAGE_START
    from test_execution_session_api import create_completed, credit
    from test_field_observation_api import payload
    import decision.services.durable_tonight_application_service as durable
    with MonkeyPatch.context() as patch:
        patch.setenv('ASTROPILOT_DATA_DIR', str(root))
        patch.setattr(durable, 'generate_mission_id', lambda: 'mission-lineage')
        api = lineage_client(root, DEFAULT_WEATHER_REFERENCE_TIME)
        assert api.post('/v1/tonight', json={'availability': {'mode': 'all_night'}}).status_code == 200
        accepted = api.post('/v1/decision-selections', json=lineage_selection_payload())
        assert accepted.status_code == 200, accepted.text
        profile = {**valid_profile(), 'projects': {'M31': {'hours': 0, 'target_hours': 4, 'imaging_field_id': 'sh2-129_ou4',
            'acquisition_intent_progress': [{'acquisition_intent_id': 'sh2-129_ha', 'acquired_duration_manual': 0}],
            'acquisition_intent_targets': [{'acquisition_intent_id': 'sh2-129_ha', 'target_hours': 4}]}}}
        save_user_profile(profile)
        client = TestClient(create_app(service_factory=build_durable_tonight_application_service, guardian_renewal_enabled=False))
        create_completed(client, 'execution-1', mission_id='mission-lineage', evidence_id='evidence-1')
        recorded = client.post('/v1/field-observations', json=payload(observation_id='obs-1', decision_id='decision-lineage', execution_id=None,
            observed_at_utc=LINEAGE_START.isoformat(), recorded_at_utc=LINEAGE_START.isoformat()))
        assert recorded.status_code == 201, recorded.text
        compared = client.post('/v1/field-observations/obs-1/outcome-evaluation')
        assert compared.status_code == 201, compared.text
        applied = credit(client, 'execution-1', 'evidence-1', confirm=True)
        assert applied.status_code == 200, applied.text
        files = snapshot(root)
        _, summary = create_backup(root)
        assert all(summary[key] == 1 for key in ('projects', 'sessions', 'observations', 'comparisons')), summary
        assert snapshot(root) == files
        for name, raw in files.items():
            path = output / 'data' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        proof = {'schema': 'nightmerit.synthetic_snapshot_fixture.v1', 'synthetic_only': True, 'summary': summary,
            'domain_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        (output / 'fixture.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
        print(json.dumps({'synthetic_only': True, 'summary': summary, 'documents': len(files)}))


if __name__ == '__main__':
    main()
