from common import CASE, app
import os

application = app()

@application.get('/__ci/provenance')
def provenance():
    return {'case': CASE.name, 'source_sha': os.environ['NIGHT_CHAIN_SOURCE_SHA']}
