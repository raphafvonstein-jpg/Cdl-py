"""XLSX com fórmulas e resultados em cache; exportação ZIP/CSV em memória."""
import bisect
import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.properties import CalcProperties
from .core import COLUMNS, MEAN_HEADERS, mean_rows, column_headers, session_bytes


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).rstrip('. ')[:100] or 'amostra'


def _csv(rows):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerows(rows)
    return ('\ufeff' + buffer.getvalue()).encode('utf-8')


def table_txt(rows, headers):
    """Tabela numérica em UTF-8, com cabeçalho e colunas separadas por tabulação."""
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter='\t', lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


def bars_csv(result):
    rows = [['amostra', 'j_geom_mA_cm2', 'sobrepotencial_medio_mV', 'DP_amostral_mV', 'n', 'status']]
    for group in result['groups']:
        for target, stat in group['bars'].items():
            rows.append([group['sample']['name'], target, stat.get('mean'), stat.get('sd'), stat.get('n'),
                         stat.get('error') or ('Sem DP (uma réplica)' if stat['n'] == 1 else 'OK')])
    return _csv(rows)


def means_csv(result, x, y):
    rows = [['amostra', 'X_' + COLUMNS[x][0], 'media_' + COLUMNS[y][0], 'DP_amostral', 'n', 'R1', 'R2', 'R3']]
    for group in result['groups']:
        for r in group['mean'] or []:
            if r['values'][y] is None:
                continue
            values = {c['rep']: r['replicas'][i][y] for i, c in enumerate(group['curves'])}
            rows.append([group['sample']['name'], r['values'][x], r['values'][y], r['sd'][y], r['n'], *[values.get(i) for i in (1, 2, 3)]])
    return _csv(rows)


def _style(ws, columns):
    ws.freeze_panes = 'A2'
    ws.row_dimensions[1].height = 38
    for c in ws[1]:
        c.font = Font(name='Calibri', bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='147E77')
        c.alignment = Alignment(wrap_text=True, vertical='center')
    for col in columns:
        ws.column_dimensions[col].width = 24
    ws.column_dimensions['N'].width = 31
    ws.column_dimensions['O'].width = 48
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.data_type in ('n', 'f'):
                c.number_format = '0.000000'


def _cache_xlsx(content, cached):
    """openpyxl escreve fórmulas; adiciona seus valores calculados ao XML."""
    output = io.BytesIO()
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as dest:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename in cached:
                root = ET.fromstring(data)
                for cell in root.iter(ns + 'c'):
                    address = cell.get('r')
                    if address not in cached[item.filename]:
                        continue
                    value = cell.find(ns + 'v')
                    if value is None:
                        value = ET.SubElement(cell, ns + 'v')
                    value.text = repr(float(cached[item.filename][address]))
                data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            dest.writestr(item, data)
    return output.getvalue()


def workbook_bytes(group, params):
    wb = Workbook()
    wb.remove(wb.active)
    wb.calculation = CalcProperties(calcId=191029, fullCalcOnLoad=True)
    for title in ['LSV 1', 'LSV 2', 'Média e DP', 'LSV 3']:
        wb.create_sheet(title)
    cached = {}
    def formula(ws, address, expression, value):
        if value is None:
            return
        ws[address] = '=' + expression
        path = 'xl/worksheets/sheet' + str(wb.index(ws) + 1) + '.xml'
        cached.setdefault(path, {})[address] = value
    for rep in (1, 2, 3):
        ws = wb[f'LSV {rep}']
        curve = next((c for c in group['curves'] if c['rep'] == rep), None)
        if curve is None:
            ws.append(['Status'])
            ws.append(['Nenhum arquivo válido nesta posição.'])
            _style(ws, ['A'])
            continue
        if len(curve['rows']) >= 1048576:
            raise ValueError('Arquivo acima do limite de linhas do Excel.')
        ws.append(column_headers(params) + ['E medido (V)', 'I medida (A)'])
        for i, values in enumerate(curve['rows'], 2):
            ws.append(values + [values[0], values[6]])
            expressions = [f'K{i}', f'A{i}+$O$7', f'G{i}*$O$3', f'B{i}-C{i}', f'D{i}-$O$6',
                           f'E{i}*1000', f'L{i}', f'G{i}*1000', f'H{i}/$O$4', f'H{i}/$O$5']
            for j, value in enumerate(values):
                formula(ws, chr(65 + j) + str(i), expressions[j], value)
        metadata = [('Amostra', group['sample']['name']), ('Rs (Ω)', curve['rs']),
                    ('Área geométrica (cm²)', curve['area']), ('Área eletroativa (cm²)', curve['electroArea']),
                    ('Eeq (V)', params['eq']), ('Conversão RHE (V)', params['shift']), ('pH', params['ph']),
                    ('Eref vs SHE (V)', params['eref']), ('Temperatura (°C)', params['temperature']),
                    ('Arquivo LSV', curve['name']), ('Origem de Rs', curve['eis']['name'] if curve['eis'] else 'manual'),
                    ('Linha EIS selecionada', curve['eis']['line'] if curve['eis'] else None),
                    ('Referência utilizada', params['reference_name'])]
        for i, (name, value) in enumerate(metadata, 2):
            ws.cell(i, 14, name)
            # Nomes são sempre texto, mesmo se começarem com '='.
            c = ws.cell(i, 15, value)
            if isinstance(value, str):
                c.data_type = 's'
        if params['reference'] != 'RHE':
            formula(ws, 'O7', 'O9+LN(10)*8.31446261815324*(O10+273.15)/96485.33212*O8', params['shift'])
        for j, (_, _, _, equation) in enumerate(COLUMNS, 1):
            ws.cell(1, j).comment = Comment(equation, 'LSV')
        _style(ws, list('ABCDEFGHIJKL'))

    ws = wb['Média e DP']
    ws.append(MEAN_HEADERS)
    for row in mean_rows(group):
        ws.append(row)
    def interpolation(curve, potential, axis, row):
        sorted_rows = sorted(enumerate(curve['rows'], 2), key=lambda r: r[1][1])
        potentials = [r[1][1] for r in sorted_rows]
        hi = max(1, min(len(potentials) - 1, bisect.bisect_right(potentials, potential)))
        a, b = sorted_rows[hi-1][0], sorted_rows[hi][0]
        prefix = f"'LSV {curve['rep']}'!"
        return f'{prefix}{axis}{a}+({prefix}{axis}{b}-{prefix}{axis}{a})*(A{row}-{prefix}B{a})/({prefix}B{b}-{prefix}B{a})'
    for i, row in enumerate(mean_rows(group), 2):
        for j in range(1, 5):
            if row[j] is None:
                continue
            terms = [interpolation(c, row[0], 'I' if j <= 2 else 'J', i) for c in group['curves']]
            expression = ('AVERAGE' if j in (1, 3) else 'STDEV') + '(' + ','.join(terms) + ')'
            formula(ws, chr(65 + j) + str(i), expression, row[j])
    if not group['mean']:
        ws.append(['; '.join(group['errors']) or 'A média requer ao menos duas réplicas válidas.'])
        ws['A2'].data_type = 's'
    _style(ws, list('ABCDEF'))
    out = io.BytesIO()
    wb.save(out)
    return _cache_xlsx(out.getvalue(), cached)


def all_samples_zip(result):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('sessao.json', session_bytes(result['state']))
        archive.writestr('avisos.json', json.dumps(result['warnings'], ensure_ascii=False))
        for group in result['groups']:
            if group['curves']:
                name = f"{group['sample']['id']}_{safe_name(group['sample']['name'])}.xlsx"
                archive.writestr(name, workbook_bytes(group, result['params']))
        for kind, label in [('curves', 'LSV'), ('impedances', 'EIS')]:
            for record in result['state'][kind]:
                archive.writestr(f"brutos/{label}/{record['id']}_{safe_name(record['name'])}", record['text'])
    return out.getvalue()
