"""Interface Streamlit; todo estado de dados pertence à sessão do usuário."""
from __future__ import annotations

import math
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from . import core
from .export import workbook_bytes, all_samples_zip, bars_csv, means_csv, safe_name, table_txt
from .plots import curves_figure, bars_figure, image_bytes

VIEWS = ['Amostras', 'Tratamento', 'Planilhas', 'Gráficos']


def state():
    return st.session_state['lsv_state']


def key(name):
    return f"e{st.session_state.get('lsv_epoch', 0)}_{name}"


def seed(name, value):
    k = key(name)
    if k not in st.session_state:
        st.session_state[k] = value
    return k


def touch():
    st.session_state['lsv_revision'] = st.session_state.get('lsv_revision', 0) + 1
    st.session_state.pop('lsv_zip', None)


def find_curve(sample_id, rep):
    return next((c for c in state()['curves'] if c['sampleId'] == sample_id and c['rep'] == rep), None)


def upload_error(message):
    st.session_state['lsv_error'] = message


def remove_curve(sample_id, rep):
    curve = find_curve(sample_id, rep)
    if curve:
        state()['curves'].remove(curve)
        state()['impedances'] = [e for e in state()['impedances'] if e['id'] != curve.get('eisId')]
    sample = next(s for s in state()['samples'] if s['id'] == sample_id)
    sample[f'slotEpoch{rep}'] = sample.get(f'slotEpoch{rep}', 0) + 1
    touch()


def remove_eis(sample_id, rep):
    curve = find_curve(sample_id, rep)
    if curve:
        state()['impedances'] = [e for e in state()['impedances'] if e['id'] != curve.get('eisId')]
        curve['eisId'], curve['rs'] = None, None
        curve['eisEpoch'] = curve.get('eisEpoch', 0) + 1
        st.session_state.pop(key(f"c{curve['id']}_rs"), None)
        touch()


def add_sample():
    n = 1
    while any(s['name'] == f'Amostra {n}' for s in state()['samples']):
        n += 1
    state()['samples'].append(dict(id=core.next_id(state()), name=f'Amostra {n}'))
    touch()


def delete_sample(sample_id):
    for c in list(state()['curves']):
        if c['sampleId'] == sample_id:
            remove_curve(sample_id, c['rep'])
    state()['samples'] = [s for s in state()['samples'] if s['id'] != sample_id]
    touch()


def rename_sample(sample_id, widget_key):
    sample = next(s for s in state()['samples'] if s['id'] == sample_id)
    draft = st.session_state[widget_key]
    sample['nameDraft'] = draft
    name = draft.strip()
    error = 'Digite o nome da amostra.' if not name else 'Esse nome já está em uso.' if any(s['id'] != sample_id and s['name'] == name for s in state()['samples']) else ''
    st.session_state[f'lsv_name_error_{sample_id}'] = error
    if error:
        return
    sample['name'] = name
    for c in state()['curves']:
        if c['sampleId'] == sample_id:
            c['sample'] = name
    touch()


def _numeric(value):
    if str(value).strip() == '':
        return None
    n = core.number(value)
    return n if math.isfinite(n) else value


def curve_field(curve_id, field, widget_key):
    curve = next(c for c in state()['curves'] if c['id'] == curve_id)
    value = st.session_state[widget_key]
    curve[field] = int(value) if field in ('x', 'y') else _numeric(value)
    touch()


def eis_field(eis_id, field, widget_key):
    eis = next(e for e in state()['impedances'] if e['id'] == eis_id)
    value = st.session_state[widget_key]
    eis[field] = int(value) if field in ('zx', 'zy') else float(value)
    touch()


def setting_field(field, widget_key):
    value = st.session_state[widget_key]
    state()['settings'][field] = str(value) if field in ('xAxis', 'yAxis') else value
    if field == 'referenceElectrode':
        state()['settings']['rheMode'] = 'already' if value == 'RHE' else 'reference'
        if value == 'SHE':
            state()['settings']['refPotential'] = '0'
            st.session_state[key('setting_refPotential')] = '0'
    touch()


def targets_changed(widget_key):
    state()['barTargets'] = sorted(st.session_state[widget_key])
    touch()


def _add_lsv(sample_id, rep, upload):
    text = core.decode_text(upload.getvalue())
    parsed = core.parse_text(text)
    sample = next(s for s in state()['samples'] if s['id'] == sample_id)
    old = find_curve(sample_id, rep)
    curve = dict(id=old['id'] if old else core.next_id(state()), sampleId=sample_id, sample=sample['name'], rep=rep,
                 name=upload.name, text=text, x=parsed['x'], y=parsed['y'], block=parsed['block'],
                 area=old.get('area', 2) if old else 2, electroArea=old.get('electroArea') if old else None,
                 rs=old.get('rs') if old else None, eisId=old.get('eisId') if old else None,
                 eisEpoch=old.get('eisEpoch', 0) if old else 0)
    if old:
        state()['curves'].remove(old)
    state()['curves'].append(curve)
    for field in ('x', 'y'):
        st.session_state.pop(key(f"c{curve['id']}_{field}"), None)


def upload_lsv(sample_id, rep, widget_key):
    upload = st.session_state[widget_key]
    if upload is None:
        remove_curve(sample_id, rep)
        return
    try:
        _add_lsv(sample_id, rep, upload)
        upload_error('')
        touch()
    except (ValueError, KeyError, IndexError) as error:
        upload_error(upload.name + ': ' + str(error))


def upload_bulk(sample_id, widget_key):
    uploads = st.session_state[widget_key] or []
    sample = next(s for s in state()['samples'] if s['id'] == sample_id)
    empty = [rep for rep in (1, 2, 3) if find_curve(sample_id, rep) is None]
    sample['bulkEpoch'] = sample.get('bulkEpoch', 0) + 1
    if len(uploads) > len(empty):
        upload_error(f"{sample['name']}: há {len(empty)} posição(ões) livre(s).")
        return
    errors = []
    for rep, upload in zip(empty, uploads):
        try:
            _add_lsv(sample_id, rep, upload)
        except (ValueError, KeyError, IndexError) as error:
            errors.append(upload.name + ': ' + str(error))
    upload_error('\n'.join(errors))
    touch()


def upload_eis(sample_id, rep, widget_key):
    upload = st.session_state[widget_key]
    curve = find_curve(sample_id, rep)
    if curve is None:
        return
    if upload is None:
        remove_eis(sample_id, rep)
        return
    try:
        text = core.decode_text(upload.getvalue())
        parsed = core.parse_text(text)
        eis = dict(id=core.next_id(state()), name=upload.name, text=text, block=parsed['block'],
                   zx=parsed['zx'], zy=parsed['zy'], zScale=1)
        state()['impedances'] = [e for e in state()['impedances'] if e['id'] != curve.get('eisId')]
        state()['impedances'].append(eis)
        curve['eisId'] = eis['id']
        upload_error('')
        touch()
    except (ValueError, KeyError, IndexError) as error:
        upload_error(upload.name + ': ' + str(error))


def load_uploaded_session(widget_key):
    upload = st.session_state[widget_key]
    if upload is None:
        return
    try:
        loaded = core.load_session(upload.getvalue())
        # Valida também o texto antes de substituir a sessão atual.
        for record in loaded['curves'] + loaded['impedances']:
            parsed = core.parse_text(record['text'], record.get('block'))
            for field in (('x', 'y') if 'rep' in record else ('zx', 'zy')):
                value = record.get(field, parsed[field])
                if not isinstance(value, int) or not 0 <= value < len(parsed['headers']):
                    raise ValueError('Coluna inválida em ' + record['name'])
                record[field] = value
            if 'rep' not in record and record.get('zScale', 1) not in (1, .001, 1000):
                raise ValueError('Unidade de impedância inválida.')
        st.session_state['lsv_state'] = loaded
        st.session_state['lsv_epoch'] = st.session_state.get('lsv_epoch', 0) + 1
        upload_error('')
        touch()
    except (ValueError, KeyError, IndexError, TypeError) as error:
        upload_error('Não foi possível abrir a sessão: ' + str(error))


def clear_session():
    st.session_state['lsv_state'] = core.new_session()
    st.session_state['lsv_epoch'] = st.session_state.get('lsv_epoch', 0) + 1
    st.session_state['view'] = 'Amostras'
    upload_error('')
    touch()


def _text_curve(curve, field, title):
    value = curve.get(field)
    k = seed(f"c{curve['id']}_{field}", '' if value is None else str(value))
    st.text_input(title, key=k, on_change=curve_field, args=(curve['id'], field, k))


def render_sample(sample):
    sid = sample['id']
    with st.container(border=True):
        k = seed(f'sample_{sid}_name', sample.get('nameDraft', sample['name']))
        st.text_input('Nome da amostra', key=k, on_change=rename_sample, args=(sid, k))
        error = st.session_state.get(f'lsv_name_error_{sid}')
        if error:
            st.error(error)
        count = sum(c['sampleId'] == sid for c in state()['curves'])
        c1, c2 = st.columns([2, 1])
        with c1.popover(f'Adicionar até 3 LSV · {count}/3'):
            bk = key(f"bulk_{sid}_{sample.get('bulkEpoch', 0)}")
            st.file_uploader('Arquivos LSV', type=['txt', 'dat', 'csv', 'tsv'], accept_multiple_files=True,
                             key=bk, on_change=upload_bulk, args=(sid, bk), disabled=count == 3)
        c2.button('Excluir amostra', key=key(f'del_sample_{sid}'), on_click=delete_sample, args=(sid,))
        for rep in (1, 2, 3):
            st.markdown(f'**Eletrodo {rep}**')
            curve = find_curve(sid, rep)
            eis = next((e for e in state()['impedances'] if curve and e['id'] == curve.get('eisId')), None)
            lsv_col, eis_col, area_col = st.columns([1.1, 1.1, .9])
            with lsv_col:
                lk = key(f"lsv_{sid}_{rep}_{sample.get(f'slotEpoch{rep}', 0)}")
                st.file_uploader(f'LSV {rep}', type=['txt', 'csv', 'tsv', 'dat'], key=lk,
                                 on_change=upload_lsv, args=(sid, rep, lk))
                if curve:
                    st.caption(curve['name'])
                    parsed = core.parse_text(curve['text'], curve.get('block'))
                    for field, title in [('x', 'Potencial (V)'), ('y', 'Corrente (A)')]:
                        fk = seed(f"c{curve['id']}_{field}", int(curve[field]))
                        st.selectbox(title, list(range(len(parsed['headers']))), key=fk,
                                     format_func=lambda i, h=parsed['headers']: f'{i+1} · {h[i]}',
                                     on_change=curve_field, args=(curve['id'], field, fk))
            with eis_col:
                ek = key(f"eis_{sid}_{rep}_{sample.get(f'slotEpoch{rep}', 0)}_{curve.get('eisEpoch', 0) if curve else 0}")
                st.file_uploader(f'Impedância {rep}', type=['txt', 'csv', 'tsv', 'dat'], key=ek, disabled=curve is None,
                                 on_change=upload_eis, args=(sid, rep, ek))
                if eis:
                    st.caption(eis['name'])
                    uk = seed(f"e{eis['id']}_zScale", eis.get('zScale', 1))
                    st.selectbox('Unidade de Z', [1, .001, 1000], key=uk,
                                 format_func=lambda n: {1: 'Ω', .001: 'mΩ', 1000: 'kΩ'}[n],
                                 on_change=eis_field, args=(eis['id'], 'zScale', uk))
                    try:
                        point = core.impedance(eis)
                        st.caption(f"Rs = {point['rs']:.6g} Ω · linha {point['line']}")
                    except ValueError as error:
                        st.warning(str(error))
                    st.button('Remover impedância', key=key(f'remove_eis_{sid}_{rep}'), on_click=remove_eis, args=(sid, rep))
                elif curve:
                    _text_curve(curve, 'rs', 'Rs manual (Ω)')
            with area_col:
                if curve:
                    _text_curve(curve, 'area', 'Área geométrica (cm²)')
                    _text_curve(curve, 'electroArea', 'Área eletroativa (cm²)')
                    st.button('Remover par', key=key(f'remove_lsv_{sid}_{rep}'), on_click=remove_curve, args=(sid, rep))
            if rep != 3:
                st.divider()


def render_samples():
    st.button('+ Adicionar amostra', on_click=add_sample)
    for i in range(0, len(state()['samples']), 2):
        columns = st.columns(2)
        for col, sample in zip(columns, state()['samples'][i:i+2]):
            with col:
                render_sample(sample)


def render_treatment():
    settings = state()['settings']
    refk = seed('setting_referenceElectrode', settings['referenceElectrode'])
    labels = {'': 'Selecione a referência', 'RHE': 'RHE — hidrogênio reversível', 'SHE': 'SHE — hidrogênio padrão',
              'Ag/AgCl': 'Ag/AgCl', 'SCE': 'Calomelano (SCE)', 'Hg/HgO': 'Hg/HgO', 'Hg/Hg2SO4': 'Hg/Hg₂SO₄', 'custom': 'Outro'}
    st.selectbox('Eletrodo de referência usado', core.REFERENCES, key=refk, format_func=lambda v: labels[v],
                 on_change=setting_field, args=('referenceElectrode', refk))
    ref = settings['referenceElectrode']
    fields = [('referenceElectrolyte', 'Eletrólito da referência'), ('ph', 'pH da solução'),
              ('refPotential', 'Eref vs SHE (V)'), ('temperature', 'Temperatura (°C)'), ('eq', 'Eeq para sobrepotencial (V)')]
    cols = st.columns(3)
    for i, (field, label) in enumerate(fields):
        k = seed('setting_' + field, str(settings[field]))
        with cols[i % 3]:
            st.text_input(label, key=k, disabled=field != 'eq' and (not ref or ref == 'RHE') or field == 'refPotential' and ref == 'SHE',
                          on_change=setting_field, args=(field, k))
    with st.expander('Ver fórmulas'):
        data = [{'Coluna': letter, 'Resultado': name, 'Unidade': unit, 'Fórmula': equation} for letter, name, unit, equation in core.COLUMNS]
        if ref:
            data[0]['Unidade'] = 'V vs ' + labels[ref]
        st.dataframe(pd.DataFrame(data), hide_index=True, width='stretch')


def render_workbooks(result):
    if not result['groups']:
        st.info('Adicione uma amostra.')
        return
    ids = [g['sample']['id'] for g in result['groups']]
    names = {g['sample']['id']: g['sample']['name'] for g in result['groups']}
    sk = seed('sheet_sample', ids[0])
    if st.session_state[sk] not in ids:
        st.session_state[sk] = ids[0]
    sid = st.selectbox('Amostra', ids, key=sk, format_func=names.get)
    group = next(g for g in result['groups'] if g['sample']['id'] == sid)
    tabs = st.tabs(['LSV 1', 'LSV 2', 'Média e DP', 'LSV 3'])
    for tab, rep in zip([tabs[0], tabs[1], tabs[3]], (1, 2, 3)):
        with tab:
            curve = next((c for c in group['curves'] if c['rep'] == rep), None)
            if curve:
                st.caption(curve['name'])
                st.dataframe(pd.DataFrame(curve['rows'], columns=core.column_headers(result['params'])), hide_index=True, width='stretch')
                st.download_button('Baixar LSV TXT', table_txt(curve['rows'], core.column_headers(result['params'])),
                                   file_name=f"{safe_name(group['sample']['name'])}_LSV_{rep}.txt",
                                   mime='text/plain', key=f'txt_{sid}_{rep}')
            else:
                st.info('Nenhum LSV válido nesta posição. Confira os arquivos e parâmetros.')
    with tabs[2]:
        if group['mean']:
            st.dataframe(pd.DataFrame(core.mean_rows(group), columns=core.MEAN_HEADERS), hide_index=True, width='stretch')
            st.download_button('Baixar média e DP TXT', table_txt(core.mean_rows(group), core.MEAN_HEADERS),
                               file_name=safe_name(group['sample']['name']) + '_media_DP.txt',
                               mime='text/plain', key=f'txt_mean_{sid}')
        else:
            st.info('A média requer duas ou três réplicas válidas em uma faixa comum.')
    left, right = st.columns(2)
    if group['curves']:
        left.download_button('Baixar amostra XLSX', workbook_bytes(group, result['params']), file_name=safe_name(group['sample']['name']) + '.xlsx',
                             mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if right.button('Preparar ZIP com todas as amostras', disabled=not any(g['curves'] for g in result['groups'])):
        st.session_state['lsv_zip'] = all_samples_zip(result)
    if 'lsv_zip' in st.session_state:
        st.download_button('Baixar ZIP', st.session_state['lsv_zip'], file_name='LSV_amostras.zip', mime='application/zip')


def render_graphs(result):
    settings = state()['settings']
    chartk = seed('setting_chartKind', settings['chartKind'])
    kind = st.selectbox('Tipo de gráfico', ['curves', 'bars'], key=chartk,
                        format_func=lambda v: 'Curvas LSV' if v == 'curves' else 'Barras · sobrepotencial',
                        on_change=setting_field, args=('chartKind', chartk))
    if kind == 'bars':
        tk = seed('targets', state()['barTargets'])
        st.multiselect('Correntes exibidas (mA/cm²)', [10, 50, 100], key=tk, on_change=targets_changed, args=(tk,))
        st.caption('Sobrepotencial médio ± DP entre eletrodos · área geométrica · correção iR')
        fig, notes = bars_figure(result)
        csv_data, filename = bars_csv(result), 'LSV_sobrepotenciais.csv'
    else:
        cols = st.columns(3)
        for col, field, title, options in [(cols[0], 'xAxis', 'Eixo X', core.X_AXES), (cols[1], 'yAxis', 'Eixo Y', core.Y_AXES)]:
            k = seed('setting_' + field, int(settings[field]))
            with col:
                st.selectbox(title, options, key=k, format_func=lambda i: f'{core.COLUMNS[i][0]} · {core.COLUMNS[i][1]} ({core.COLUMNS[i][2]})',
                             on_change=setting_field, args=(field, k))
        mk = seed('setting_mode', settings['mode'])
        with cols[2]:
            st.radio('Mostrar', ['raw', 'mean'], key=mk, horizontal=True,
                     format_func=lambda v: 'Eletrodos' if v == 'raw' else 'Média ± DP', on_change=setting_field, args=('mode', mk))
        x, y = int(settings['xAxis']), int(settings['yAxis'])
        fig, notes = curves_figure(result, x, y, settings['mode'])
        csv_data, filename = means_csv(result, x, y), 'LSV_medias_DP.csv'
    for note in notes:
        st.caption(note)
    st.pyplot(fig, width=760)
    png = image_bytes(fig)
    svg = image_bytes(fig, 'svg')
    plt.close(fig)
    cols = st.columns(3)
    cols[0].download_button('Baixar gráfico PNG', png, file_name='LSV_grafico.png', mime='image/png')
    cols[1].download_button('Baixar gráfico SVG', svg, file_name='LSV_grafico.svg', mime='image/svg+xml')
    cols[2].download_button('Baixar dados CSV', csv_data, file_name=filename, mime='text/csv')


def main():
    st.set_page_config(page_title='LSV e impedância', page_icon='📈', layout='wide')
    st.session_state.setdefault('lsv_state', core.new_session())
    st.session_state.setdefault('lsv_epoch', 0)
    st.session_state.setdefault('lsv_revision', 0)
    st.markdown('<style>div[data-testid="stFileUploaderDropzone"]{padding:8px}div[data-testid="stFileUploaderDropzoneInstructions"]{font-size:11px}div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:10px}</style>', unsafe_allow_html=True)
    st.title('LSV e impedância')
    with st.sidebar:
        st.subheader('Sessão')
        ik = key('session_upload')
        st.file_uploader('Abrir sessão JSON', type=['json'], key=ik, on_change=load_uploaded_session, args=(ik,))
        st.download_button('Salvar sessão JSON', core.session_bytes(state()), file_name='LSV_sessao.json', mime='application/json')
        st.button('Limpar sessão', on_click=clear_session)
        st.caption('Os arquivos são processados na sessão do aplicativo. Salve o JSON para continuar depois.')
    if st.session_state.get('lsv_error'):
        st.error(st.session_state['lsv_error'])
    view = st.radio('Seção', VIEWS, horizontal=True, key='view', label_visibility='collapsed')
    if view == 'Amostras':
        render_samples()
    elif view == 'Tratamento':
        render_treatment()
    else:
        try:
            result = core.process_session(state())
        except (ValueError, KeyError, IndexError, TypeError) as error:
            st.info(str(error))
            return
        if result['warnings']:
            with st.expander('Avisos dos dados'):
                for warning in result['warnings']:
                    st.warning(warning)
        if view == 'Planilhas':
            render_workbooks(result)
        else:
            render_graphs(result)
