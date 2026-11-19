"""Compile the mean overhead-distance penalty directly into v06."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
model = json.loads((root / 'v06.json').read_text())
model['version'] = 'v08'
first, second = model['layers'][:2]
for start in range(14):
    first['W'].append([0.] * start + [-1.] * (14-start) + [0.] * 4)
    first['b'].append(0.)
    first['node_names'].append(f'overhead_{14-start}')
for i, row in enumerate(second['W']):
    row.extend(([-1/14] if i < 2 else [0.]) * 14)
(root / 'v08.json').write_text(json.dumps(model, indent=2)+'\n')
model['version'] = 'v09'
for start in range(14):
    first['W'].append([0.] * start + [1.] * (14-start) + [0.] * 4)
    first['b'].append(0.)
    first['node_names'].append(f'underfoot_{14-start}')
for i, row in enumerate(second['W']):
    row[-14:] = ([-1/28] if i < 2 else [0.]) * 28
(root / 'v09.json').write_text(json.dumps(model, indent=2)+'\n')
