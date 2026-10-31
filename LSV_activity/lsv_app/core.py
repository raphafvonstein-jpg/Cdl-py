"""Leitura, tratamento e estatística; independente da interface Streamlit."""
from __future__ import annotations

import bisect
import copy
import json
import math
import re
import statistics

NAN = float('nan')
MEASURED, RHE, IR, CORRECTED, ETA, ETA_MV, CURRENT, CURRENT_MA, GEO, ACTIVE = range(10)
X_AXES, Y_AXES = (0, 1, 3, 4, 5), (7, 8, 9)
COLUMNS = [
    ('A', 'Potencial medido', 'V vs referência usada', 'E importado'),
    ('B', 'Potencial convertido', 'V vs RHE', 'A + Eref(vs SHE) + ln(10) RT/F × pH; se já RHE, B = A'),
    ('C', 'Queda iR', 'V', 'G × Rs'),
    ('D', 'Potencial corrigido', 'V vs RHE', 'B − C'),
    ('E', 'Sobrepotencial', 'V', 'D − Eeq'),
    ('F', 'Sobrepotencial', 'mV', 'E × 1000'),
    ('G', 'Corrente', 'A', 'I importada'),
    ('H', 'Corrente', 'mA', 'G × 1000'),
    ('I', 'Densidade geométrica', 'mA/cm²', 'H / área geométrica'),
    ('J', 'Densidade eletroativa', 'mA/cm²', 'H / área eletroativa'),
]
REFERENCES = ['', 'RHE', 'SHE', 'Ag/AgCl', 'SCE', 'Hg/HgO', 'Hg/Hg2SO4', 'custom']
MEAN_HEADERS = ['Potencial comum (V vs RHE)', 'Média j geom. (mA/cm²)', 'DP j geom. (mA/cm²)',
                'Média j eletroat. (mA/cm²)', 'DP j eletroat. (mA/cm²)', 'n']


def number(value):
    try:
        text = str(value).strip().replace('−', '-').replace('–', '-')
        return float(text.replace(',', '.')) if text else NAN
    except (TypeError, ValueError):
        return NAN


def required(value, name, *, positive=False, nonnegative=False):
    n = number(value)
    if not math.isfinite(n) or positive and n <= 0 or nonnegative and n < 0:
        raise ValueError(f'Informe um valor válido para {name}.')
    return n


def decode_text(data: bytes):
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252', errors='replace')


def parse_text(text: str, block=None):
    lines = text.lstrip('\ufeff').splitlines()
    def split(line, delimiter):
        return re.split(r'\s+', line.strip()) if delimiter == 'space' else line.split(delimiter)
    best = None
    for delimiter in ['\t', ';', ',', 'space']:
        runs, run = [], []
        def finish():
            if len(run) >= 2:
                runs.append(run[:])
            run.clear()
        for i, line in enumerate(lines):
            values = [number(v) for v in split(line, delimiter)]
            if sum(math.isfinite(v) for v in values) < 2:
                finish()
                continue
            if run and len(values) != len(run[0][1]):
                finish()
            run.append((i, values))
        finish()
        score = max((len(r) for r in runs), default=0)
        if best is None or score > best[0]:
            best = score, delimiter, runs
    if not best[0]:
        raise ValueError('Não foi possível identificar duas colunas numéricas.')
    _, delimiter, runs = best
    index = max(range(len(runs)), key=lambda i: len(runs[i])) if block is None else int(block)
    if not 0 <= index < len(runs):
        raise ValueError('Bloco de dados inválido.')
    run = runs[index]
    start, width = run[0][0], len(run[0][1])
    headers = [f'Coluna {i+1}' for i in range(width)]
    for i in range(start - 1, max(-1, start - 6), -1):
        h = split(lines[i], delimiter)
        if len(h) == width and any(re.search('[a-zA-Z]', v) for v in h):
            headers = [v.strip() or headers[j] for j, v in enumerate(h)]
            break
    def find(pattern, default):
        return next((i for i, h in enumerate(headers) if re.search(pattern, h, re.I)), default)
    x = find(r'potential|potencial|ewe|^e\s*[/\(]', 0)
    y = find(r'current|corrente|<i>|^i\s*[/\(]', 1 if x == 0 else 0)
    if x == y:
        y = 1 if x == 0 else 0
    zx = find(r"z\s*['′](?!['′])|zre|re\s*\(?z|real", 0)
    zy = find(r"z\s*(?:['′]{2}|″)|zim|im\s*\(?z|imag", 1 if zx == 0 else 0)
    if zx == zy:
        zy = 1 if zx == 0 else 0
    return dict(headers=headers, data=[r[1] for r in run], x=x, y=y, zx=zx, zy=zy, block=index,
                start_line=start + 1, other_rows=sum(len(r) for i, r in enumerate(runs) if i != index))


def impedance_sign(header):
    text = str(header).replace('−', '-')
    if re.search(r'-\s*(?:z|im)', text, re.I):
        return 1
    return -1 if re.search(r"im|imag|z\s*(?:['′]{2}|″)", text, re.I) else 1


def impedance(record):
    parsed = parse_text(record['text'], record.get('block'))
    x, y = int(record.get('zx', parsed['zx'])), int(record.get('zy', parsed['zy']))
    if x == y or min(x, y) < 0 or max(x, y) >= len(parsed['headers']):
        raise ValueError('Selecione colunas diferentes de Z′ e Z″.')
    scale = required(record.get('zScale', 1), 'unidade da impedância', positive=True)
    sign = impedance_sign(parsed['headers'][y])
    points = [(r[x] * scale, r[y] * scale * sign) for r in parsed['data']]
    for i, (real, imaginary) in enumerate(points):
        if math.isfinite(real) and math.isfinite(imaginary) and imaginary > 0:
            if real < 0:
                raise ValueError('O primeiro ponto com −Z″ positivo tem Z′ negativo.')
            return dict(rs=real, y=imaginary, line=parsed['start_line'] + i, index=i,
                        points=[p for p in points if all(math.isfinite(v) for v in p)], name=record['name'])
    raise ValueError('Não há ponto com −Z″ positivo na impedância.')


def parameters(settings):
    ref = settings.get('referenceElectrode', '')
    if ref not in REFERENCES or not ref:
        raise ValueError('Selecione o eletrodo de referência em Tratamento.')
    eq = required(settings.get('eq', 1.23), 'Eeq')
    if ref == 'RHE':
        shift, ph, eref, temperature = 0., None, None, None
    else:
        ph = required(settings.get('ph'), 'pH')
        eref = 0. if ref == 'SHE' else required(settings.get('refPotential'), 'Eref vs SHE')
        temperature = required(settings.get('temperature', 25), 'temperatura')
        if temperature <= -273.15:
            raise ValueError('Temperatura abaixo do zero absoluto.')
        shift = eref + math.log(10) * 8.31446261815324 * (temperature + 273.15) / 96485.33212 * ph
    detail = str(settings.get('referenceElectrolyte', '')).strip()
    name = ('Outra referência' if ref == 'custom' else ref) + (' · ' + detail if detail and ref != 'RHE' else '')
    return dict(reference=ref, reference_name=name, eq=eq, shift=shift, ph=ph, eref=eref, temperature=temperature)


def column_headers(params):
    return [f'{letter} · {name} ({"V vs " + params["reference_name"] if i == 0 else unit})'
            for i, (letter, name, unit, _) in enumerate(COLUMNS)]


def treat(record, params, eis=None):
    parsed = parse_text(record['text'], record.get('block'))
    x, y = int(record.get('x', parsed['x'])), int(record.get('y', parsed['y']))
    if x == y or min(x, y) < 0 or max(x, y) >= len(parsed['headers']):
        raise ValueError('Selecione colunas diferentes de potencial e corrente.')
    area = required(record.get('area'), 'área geométrica', positive=True)
    active = record.get('electroArea')
    active = None if active is None or str(active).strip() == '' else required(active, 'área eletroativa', positive=True)
    rs = eis['rs'] if eis else required(record.get('rs'), 'Rs', nonnegative=True)
    rows, omitted = [], 0
    for raw in parsed['data']:
        a, current = raw[x], raw[y]
        if not math.isfinite(a) or not math.isfinite(current):
            omitted += 1
            continue
        b, ir, ma = a + params['shift'], current * rs, current * 1000
        corrected = b - ir
        eta = corrected - params['eq']
        values = [a, b, ir, corrected, eta, eta * 1000, current, ma, ma / area, None if active is None else ma / active]
        if not all(v is None or math.isfinite(v) for v in values):
            raise ValueError('Resultado fora do intervalo numérico.')
        rows.append(values)
    if len(rows) < 2:
        raise ValueError('Menos de dois pontos válidos.')
    return {**record, 'rows': rows, 'rs': rs, 'area': area, 'electroArea': active,
            'eis': eis, 'parsed': parsed, 'omitted': omitted}


def monotonic(rows):
    direction = 0
    for a, b in zip(rows, rows[1:]):
        delta = (b[0] > a[0]) - (b[0] < a[0])
        if delta and direction and delta != direction:
            return False
        if delta:
            direction = delta
    return bool(direction)


def mean_vectors(curves, count=201):
    if len(curves) < 2:
        raise ValueError('A média requer duas ou três réplicas.')
    sets = []
    for curve in curves:
        if not monotonic(curve['rows']):
            raise ValueError('O potencial medido muda de direção; separe os ramos para calcular a média.')
        rows = sorted(curve['rows'], key=lambda r: r[0])
        if any(a[0] == b[0] for a, b in zip(rows, rows[1:])):
            raise ValueError('Potenciais medidos repetidos; revise o ramo.')
        sets.append((rows, [r[0] for r in rows]))
    low, high = max(s[0][0][0] for s in sets), min(s[0][-1][0] for s in sets)
    if high <= low:
        raise ValueError('Não há faixa de potencial comum entre as réplicas.')
    result = []
    for i in range(count):
        x = low + (high - low) * i / (count - 1)
        replicas = []
        for rows, xs in sets:
            hi = max(1, min(len(rows) - 1, bisect.bisect_right(xs, x)))
            a, b = rows[hi - 1], rows[hi]
            fraction = (x - a[0]) / (b[0] - a[0])
            replicas.append([None if a[j] is None or b[j] is None else a[j] + fraction * (b[j] - a[j]) for j in range(10)])
        values, sd = [], []
        for j in range(10):
            ys = [r[j] for r in replicas]
            values.append(None if None in ys else statistics.mean(ys))
            sd.append(None if None in ys else statistics.stdev(ys))
        result.append(dict(values=values, sd=sd, replicas=replicas, n=len(curves)))
    return result


def target_vector(rows, target=10):
    hits = []
    for i, (a, b) in enumerate(zip(rows, rows[1:])):
        ya, yb = a[GEO], b[GEO]
        if ya == target:
            hits.append((i, 0., float(i)))
        if yb == target:
            hits.append((i, 1., float(i + 1)))
        if ya < target < yb or yb < target < ya:
            f = (target - ya) / (yb - ya)
            hits.append((i, f, i + f))
    unique = []
    for hit in hits:
        if not any(abs(hit[2] - other[2]) < 1e-10 for other in unique):
            unique.append(hit)
    if not unique:
        raise ValueError(f'{target} mA/cm² fora da faixa medida.')
    if len(unique) > 1:
        raise ValueError(f'Mais de um cruzamento em {target} mA/cm².')
    i, f, _ = unique[0]
    a, b = rows[i], rows[i + 1]
    return [None if a[j] is None or b[j] is None else a[j] + f * (b[j] - a[j]) for j in range(10)]


def bar_stats(curves, target):
    values = []
    for curve in curves:
        if not monotonic(curve['rows']):
            raise ValueError('Potencial medido com inversão; separe os ramos.')
        values.append(target_vector(curve['rows'], target)[ETA_MV])
    if not values:
        raise ValueError('Nenhuma réplica tratada.')
    return dict(mean=statistics.mean(values), sd=statistics.stdev(values) if len(values) > 1 else None,
                n=len(values), values=values)


def new_session():
    return dict(format='lsv-bancada', version=9, samples=[dict(id=1, name='Amostra 1')], curves=[], impedances=[],
                settings=dict(referenceElectrode='', referenceElectrolyte='', rheMode='reference', ph='', refPotential='',
                              temperature='25', eq='1.23', xAxis='1', yAxis='8', mode='raw', chartKind='curves'),
                barTargets=[10, 50, 100])


def next_id(state):
    return max([0] + [r['id'] for key in ('samples', 'curves', 'impedances') for r in state.get(key, [])]) + 1


def normalize_session(data):
    if not isinstance(data, dict):
        raise ValueError('A sessão deve ser um objeto JSON.')
    state = copy.deepcopy(data)
    if state.get('format') != 'lsv-bancada' or state.get('version') not in range(2, 10):
        raise ValueError('Sessão LSV incompatível.')
    settings = state.setdefault('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('Configurações de sessão inválidas.')
    if number(settings.get('eUnit', 1)) != 1 or number(settings.get('iUnit', 1)) != 1:
        raise ValueError('Esta versão recebe somente V e A; converta os arquivos antes de importar.')
    state.setdefault('impedances', [])
    if not isinstance(state.get('curves'), list) or not isinstance(state['impedances'], list):
        raise ValueError('Dados de sessão inválidos.')
    records = state['curves'] + state['impedances']
    ids = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Registro de arquivo inválido.')
        if not isinstance(record.get('id'), int) or record['id'] <= 0 or not isinstance(record.get('name'), str) or not isinstance(record.get('text'), str):
            raise ValueError('Arquivo de sessão inválido.')
        ids.append(record['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('Identificadores de arquivo repetidos.')
    if state['version'] < 4:
        offset = required(settings.get('offset', 0), 'deslocamento da sessão antiga')
        settings.update(rheMode='reference' if offset else 'already', ph='0', refPotential=str(offset), temperature='25')
        for c in state['curves']:
            c['electroArea'] = c.get('factor') * c['area'] if isinstance(c.get('factor'), (float, int)) else None
    if state['version'] < 5:
        settings['referenceElectrode'] = 'RHE' if settings.get('rheMode') == 'already' else 'custom'
    if state['version'] < 7:
        mapping = {0: 0, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 1}
        for key in ('xAxis', 'yAxis'):
            if key in settings:
                settings[key] = str(mapping[int(settings[key])])
    if state.get('samples') is not None and not isinstance(state['samples'], list):
        raise ValueError('Lista de amostras inválida.')
    if not state.get('samples'):
        state['samples'] = []
        for c in state['curves']:
            sample = next((s for s in state['samples'] if s['name'] == c['sample']), None)
            if sample is None:
                sample = dict(id=next_id(state), name=c['sample'])
                state['samples'].append(sample)
            c['sampleId'] = sample['id']
    samples = state['samples']
    if any(not isinstance(s, dict) for s in samples):
        raise ValueError('Amostra inválida.')
    names = [s.get('name') for s in samples]
    sample_ids = [s.get('id') for s in samples]
    if any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != len(names):
        raise ValueError('As amostras precisam de nomes diferentes e não vazios.')
    if any(not isinstance(i, int) or i <= 0 or i in ids for i in sample_ids) or len(set(sample_ids)) != len(sample_ids):
        raise ValueError('Identificadores de amostra inválidos.')
    if any(c.get('sampleId') not in sample_ids for c in state['curves']):
        raise ValueError('Arquivo sem amostra correspondente.')
    for sample in samples:
        cs = [c for c in state['curves'] if c['sampleId'] == sample['id']]
        if len(cs) > 3 or len({c.get('rep') for c in cs}) != len(cs) or any(c.get('rep') not in (1, 2, 3) for c in cs):
            raise ValueError('Cada amostra deve conter até três posições distintas de LSV.')
        for c in cs:
            c['sample'] = sample['name']
    linked = [c.get('eisId') for c in state['curves'] if c.get('eisId') is not None]
    if any(i not in {e['id'] for e in state['impedances']} for i in linked) or len(set(linked)) != len(linked):
        raise ValueError('Vínculos de impedância inválidos.')
    targets = state.get('barTargets', [10, 50, 100])
    if not isinstance(targets, list) or any(t not in (10, 50, 100) for t in targets) or len(set(targets)) != len(targets):
        raise ValueError('Correntes do gráfico de barras inválidas.')
    defaults = new_session()['settings']
    for key, value in defaults.items():
        settings.setdefault(key, value)
    if settings['referenceElectrode'] not in REFERENCES or int(settings['xAxis']) not in X_AXES or int(settings['yAxis']) not in Y_AXES or settings['mode'] not in ('raw', 'mean') or settings['chartKind'] not in ('curves', 'bars'):
        raise ValueError('Configuração de gráficos ou referência inválida.')
    state['barTargets'], state['version'] = targets, 9
    return state


def load_session(data: bytes):
    return normalize_session(json.loads(decode_text(data)))


def session_bytes(state):
    return json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def process_session(data):
    state = normalize_session(data)
    params = parameters(state['settings'])
    eis_by_id = {e['id']: e for e in state['impedances']}
    groups, warnings = [], []
    for sample in state['samples']:
        imported = [c for c in state['curves'] if c['sampleId'] == sample['id']]
        group = dict(sample=sample, curves=[], mean=None, bars={}, errors=[], complete=True)
        for record in sorted(imported, key=lambda c: c['rep']):
            try:
                eis = impedance(eis_by_id[record['eisId']]) if record.get('eisId') is not None else None
                curve = treat(record, params, eis)
                group['curves'].append(curve)
                if curve['omitted']:
                    warnings.append(f"{record['name']}: {curve['omitted']} linhas inválidas excluídas.")
                if curve['parsed']['other_rows']:
                    warnings.append(f"{record['name']}: {curve['parsed']['other_rows']} linhas em outros blocos não selecionadas.")
            except (ValueError, KeyError, IndexError, TypeError) as error:
                group['complete'] = False
                group['errors'].append(record['name'] + ': ' + str(error))
        if group['complete'] and len(group['curves']) >= 2:
            try:
                group['mean'] = mean_vectors(group['curves'])
            except ValueError as error:
                group['errors'].append(str(error))
        for target in state['barTargets']:
            try:
                if not group['complete']:
                    raise ValueError('Há réplica com tratamento pendente.')
                group['bars'][target] = bar_stats(group['curves'], target)
            except ValueError as error:
                group['bars'][target] = dict(error=str(error))
        warnings.extend(sample['name'] + ': ' + e for e in group['errors'])
        groups.append(group)
    return dict(state=state, params=params, groups=groups, warnings=warnings)


def sample_metric(group, target=10):
    if not group['complete'] or not group['curves']:
        raise ValueError('Tratamento pendente.')
    if group['mean']:
        rows = [r['values'] for r in group['mean']]
    elif len(group['curves']) == 1 and monotonic(group['curves'][0]['rows']):
        rows = group['curves'][0]['rows']
    else:
        raise ValueError('Não há média válida para localizar a corrente-alvo.')
    return target_vector(rows, target)


def mean_rows(group):
    return [[r['values'][RHE], r['values'][GEO], r['sd'][GEO], r['values'][ACTIVE], r['sd'][ACTIVE], r['n']]
            for r in group['mean'] or []]
