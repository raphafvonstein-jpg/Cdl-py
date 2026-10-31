"""Gráficos científicos para Streamlit e exportação em PNG/SVG."""
import io
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from .core import COLUMNS, GEO, ACTIVE, ETA, ETA_MV, sample_metric, impedance

COLORS = ['#147e77', '#db8b35', '#7962b1', '#c05777', '#427db8', '#7f933c']
BAR_COLORS = {10: '#ffca99', 50: '#9dd59b', 100: '#9ebfe3'}


def _figure():
    fig, ax = plt.subplots(figsize=(9, 5.5), layout='constrained')
    ax.tick_params(direction='out')
    ax.spines[['top', 'right']].set_visible(True)
    return fig, ax


def metric_text(values, axis):
    symbol = 'η₁₀' if axis in (ETA, ETA_MV) else 'E₁₀'
    return f'{symbol} = {values[axis]:.1f} mV' if axis == ETA_MV else f'{symbol} = {values[axis]:.4f} V'


def curves_figure(result, x, y, mode='raw'):
    fig, ax = _figure()
    notes, plotted = [], 0
    for index, group in enumerate(result['groups']):
        name, color = group['sample']['name'], COLORS[index % len(COLORS)]
        used_mean = bool(mode == 'mean' and group['mean'] and all(r['values'][y] is not None for r in group['mean']))
        if used_mean:
            a = np.array([[r['values'][x], r['values'][y], r['sd'][y]] for r in group['mean']])
            ax.fill_between(a[:, 0], a[:, 1] - a[:, 2], a[:, 1] + a[:, 2], color=color, alpha=.17, linewidth=0)
            ax.plot(a[:, 0], a[:, 1], color=color, linewidth=1.6, label=name + '_Média')
            plotted += 1
        else:
            for c in group['curves']:
                rows = [r for r in c['rows'] if r[x] is not None and r[y] is not None]
                if not rows:
                    continue
                a = np.array(rows)
                ax.plot(a[:, x], a[:, y], color=color, linewidth=1.3,
                        linestyle={1: '-', 2: '--', 3: ':'}[c['rep']], label=name + '_Eletr' + str(c['rep']))
                plotted += 1
            if mode == 'mean' and group['curves']:
                notes.append(name + ': sem média válida nesse eixo; exibidas as curvas individuais disponíveis.')
        if y == ACTIVE and any(c['electroArea'] is None for c in group['curves']):
            notes.append(name + ': informe a área eletroativa de cada réplica para exibir todas as curvas desse eixo.')
        try:
            values = sample_metric(group)
            if values[x] is not None and values[y] is not None:
                ax.scatter([values[x]], [values[y]], color=color, s=28, edgecolors='white', zorder=5)
                ax.annotate(name + '\n' + metric_text(values, x), xy=(values[x], values[y]),
                            xytext=(10 if index % 2 == 0 else -10, 15 + index % 3 * 20), textcoords='offset points',
                            ha='left' if index % 2 == 0 else 'right', fontsize=9, color=color,
                            bbox=dict(boxstyle='round,pad=.35', fc='white', ec=color, alpha=.95),
                            arrowprops=dict(arrowstyle='-', color=color, lw=.8), annotation_clip=True)
        except ValueError as error:
            notes.append(name + ' · 10 mA/cm²: ' + str(error))
    ref_unit = 'V vs ' + result['params']['reference_name'] if x == 0 else COLUMNS[x][2]
    ax.set_xlabel(COLUMNS[x][1] + ' (' + ref_unit + ')')
    ax.set_ylabel(COLUMNS[y][1] + ' (' + COLUMNS[y][2] + ')')
    ax.margins(x=.07, y=.15)
    if plotted:
        ax.legend(frameon=False, fontsize=9, loc='best')
    else:
        ax.text(.5, .5, 'Não há curvas válidas para esses eixos.', transform=ax.transAxes, ha='center')
    return fig, notes


def nyquist_figure(state):
    fig, ax = _figure()
    notes, plotted = [], 0
    records = {e['id']: e for e in state['impedances']}
    for i, sample in enumerate(state['samples']):
        for c in state['curves']:
            if c['sampleId'] != sample['id'] or c.get('eisId') not in records:
                continue
            try:
                eis = impedance(records[c['eisId']])
                a = np.array(eis['points'])
                color = COLORS[i % len(COLORS)]
                ax.plot(a[:, 0], a[:, 1], color=color, linestyle={1: '-', 2: '--', 3: ':'}[c['rep']],
                        label=sample['name'] + '_Eletr' + str(c['rep']))
                ax.scatter([eis['rs']], [eis['y']], color=color, s=30)
                plotted += 1
            except ValueError as error:
                notes.append(c['name'] + ': ' + str(error))
    ax.axhline(0, color='#b4beb7', linewidth=.7)
    ax.set_xlabel('Z′ (Ω)')
    ax.set_ylabel('−Z″ (Ω)')
    ax.set_aspect('equal', adjustable='box')
    if plotted:
        ax.legend(frameon=False, fontsize=9)
    else:
        ax.text(.5, .5, 'Importe a impedância de cada LSV.', transform=ax.transAxes, ha='center')
    return fig, notes


def bars_figure(result):
    fig, ax = _figure()
    targets, groups = result['state']['barTargets'], result['groups']
    notes = []
    ax.set_xlabel('Amostras')
    ax.set_ylabel('Sobrepotencial (mV)')
    if not targets:
        ax.text(.5, .5, 'Selecione 10, 50 e/ou 100 mA/cm².', transform=ax.transAxes, ha='center')
        return fig, notes
    if not groups:
        ax.text(.5, .5, 'Adicione amostras.', transform=ax.transAxes, ha='center')
        return fig, notes
    x = np.arange(len(groups))
    width = .78 / len(targets)
    extrema = [0.]
    for j, target in enumerate(targets):
        xs = x + (j - (len(targets) - 1) / 2) * width
        ax.bar([], [], color=BAR_COLORS[target], label=f'{target} mA/cm²')
        for i, group in enumerate(groups):
            stat = group['bars'][target]
            if 'error' in stat:
                ax.text(xs[i], 0, 'n/d', ha='center', va='bottom', color='#7b8880', fontsize=9)
                notes.append(group['sample']['name'] + f' · {target} mA/cm²: ' + stat['error'])
                continue
            mean, sd = stat['mean'], stat['sd']
            ax.bar(xs[i], mean, width=width * .94, color=BAR_COLORS[target],
                   yerr=sd if sd is not None else None, capsize=4,
                   error_kw=dict(elinewidth=.8, capthick=.8, ecolor='#263b2d'))
            upper = mean + (sd or 0)
            extrema.extend([mean - (sd or 0), upper])
            ax.annotate(f'{mean:.0f}', xy=(xs[i], upper), xytext=(0, 6), textcoords='offset points',
                        ha='center', va='bottom', fontsize=10)
            if sd is None:
                notes.append(group['sample']['name'] + f' · {target} mA/cm²: uma réplica; sem DP.')
    low, high = min(extrema), max(extrema)
    span = max(100, high - low)
    ax.set_ylim(low - (.08 * span if low < 0 else 0), high + .22 * span)
    ax.set_xticks(x, [g['sample']['name'] for g in groups], rotation=15 if any(len(g['sample']['name']) > 16 for g in groups) else 0)
    ax.legend(frameon=False, loc='upper left', bbox_to_anchor=(0, 1.12), ncols=min(3, len(targets)))
    ax.grid(axis='y', alpha=.12)
    ax.set_axisbelow(True)
    return fig, notes


def image_bytes(fig, fmt='png'):
    out = io.BytesIO()
    fig.savefig(out, format=fmt, dpi=250, bbox_inches='tight')
    return out.getvalue()
