"""Trusted declarative interpreter. Input never controls imports, paths or commands."""
import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU,(2,2))
resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
p=json.loads(sys.stdin.read(600000))
if p['mode'] not in ('methodology','teaching','second-brain') or len(p['steps'])>288:
    raise ValueError('unsupported program')
print(json.dumps({'status':'PASS','mode':p['mode'],'workbook':p['steps'],
    'question':p['question']['proposition'],'scope':p['coverage'],
    'claim_status':'SOURCE_EXTRACTS_NOT_VERIFIED_FACTS',
    'next_action':'independent review before release',
    'side_effects':[]}))
