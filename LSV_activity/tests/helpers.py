from lsv_app.core import new_session, next_id


def demo_session():
    state = new_session()
    state['samples'][0]['name'] = 'Amostra A'
    state['settings'].update(referenceElectrode='RHE', rheMode='already', xAxis='5', yAxis='8', mode='mean')
    for index in range(2):
        sample = state['samples'][0] if index == 0 else dict(id=next_id(state), name='Amostra B')
        if index:
            state['samples'].append(sample)
        for rep in (1, 3):
            delta = (.02 if rep == 3 else 0) - index * .1
            text = 'Potential/V\tCurrent/A\n' + '\n'.join(f'{e+delta}\t{i}' for e, i in [(1.5, .01), (1.7, .05), (1.9, .1), (2., .12)])
            state['curves'].append(dict(id=next_id(state), name=f'LSV_{index}_{rep}.txt', text=text,
                                        sample=sample['name'], sampleId=sample['id'], rep=rep, x=0, y=1,
                                        area=1., electroArea=2., rs=0., eisId=None))
    return state
