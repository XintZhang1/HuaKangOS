"""Single-question exports preserve the chart population and native care scope."""
import csv
import io
from itertools import combinations
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.conftest import login
from tests import test_customer_service as care
from tests import test_questionnaire_versions as q
from tests.test_multistore import second_store,switch


def exported(client,table,filters=None):
    response=client.get(q.API+'/export/'+table,params=filters or {})
    assert response.status_code==200,response.text
    return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))


def test_each_chart_detail_and_csv_share_one_original_question_across_versions(client):
    old=q.started(client);q.close(client,old,{'satisfaction':4,'recommend':False})
    q.published(client)
    first=q.started(client);q.close(client,first,{'answers':{'wait_minutes':0,'first_visit':False}})
    second=q.started(client);q.close(client,second,{'result':'declined','answers':{}})
    # Reusing the same schema still creates a distinct issued version.
    q.published(client)
    third=q.started(client);q.close(client,third,{'answers':{'wait_minutes':7,'first_visit':True}})
    data=client.get(q.API+'/report').json()
    assert data['metrics']['questionnaires_closed']==4
    assert {chart['table_filters']['version_number'] for chart in data['charts']}=={1,2,3}
    for chart in data['charts']:
        filters=chart['table_filters']
        matching=lambda row:all(row.get(key)==value for key,value in filters.items())
        distribution=[row for row in data['tables'][chart['table']]['rows'] if matching(row)]
        answers=[row for row in data['tables']['questionnaire_answers']['rows'] if matching(row)]
        assert [row['values'][-2] for row in distribution]==chart['labels']
        assert [row['count'] for row in distribution]==chart['series'][0]['values']
        assert sum(chart['series'][0]['values'])==len(answers)
        for key,rows in [(chart['table'],distribution),('questionnaire_answers',answers)]:
            assert exported(client,key,filters)==[data['tables'][key]['headers']]+[[str(v) for v in row['values']] for row in rows]
    boolean=next(c for c in data['charts'] if c['id']=='questionnaire_2_first_visit')
    zero=next(c for c in data['charts'] if c['id']=='questionnaire_2_wait_minutes')
    assert dict(zip(boolean['labels'],boolean['series'][0]['values']))=={'否':1,'未回答':1}
    assert dict(zip(zero['labels'],zero['series'][0]['values']))=={'0':1,'未回答':1}
    for key,table in data['tables'].items():
        assert exported(client,key)==[table['headers']]+[[str(v) for v in row['values']] for row in table['rows']]
    # A valid but different original digest cannot fall back to the whole table.
    wrong={**boolean['table_filters'],'schema_digest':'0'*64}
    assert exported(client,boolean['table'],wrong)==[data['tables'][boolean['table']]['headers']]
    assert exported(client,'questionnaire_answers',wrong)==[data['tables']['questionnaire_answers']['headers']]


def test_partial_empty_and_invalid_question_selectors_fail_closed_in_chinese(client):
    q.published(client);q.close(client,q.started(client),{'answers':{'wait_minutes':0,'first_visit':False}})
    chart=client.get(q.API+'/report').json()['charts'][0]
    filters=chart['table_filters']
    bad=[dict(parts) for size in (1,2) for parts in combinations(filters.items(),size)]
    bad.extend({**filters,key:''} for key in filters)
    bad.extend({**filters,'version_number':value} for value in ['0','-1','1.5','false',' 2','99999999999'])
    bad.extend({**filters,'schema_digest':value} for value in ['wrong','A'*64,'0'*63])
    bad.extend({**filters,'question_key':value} for value in ['Wait','../../secret','x'*41])
    for params in bad:
        response=client.get(q.API+'/export/'+chart['table'],params=params)
        assert response.status_code==422,(params,response.text)
        assert isinstance(response.json()['detail'],str)
        assert any('\u4e00'<=c<='\u9fff' for c in response.json()['detail'])
    unsupported=client.get(q.API+'/export/questionnaire_issued',params=filters)
    assert unsupported.status_code==422 and '单题筛选' in unsupported.json()['detail']


def test_filtered_csv_keeps_employee_and_store_scope_even_with_known_other_digest(client):
    q.published(client)
    private=q.started(client);q.close(client,private,{'answers':{'wait_minutes':99,'first_visit':True}})
    customer=care.customer(owner='sales');login(client,'sales')
    own=q.started(client,customer_id=customer,assignee='sales')
    q.close(client,own,{'answers':{'wait_minutes':0,'first_visit':False}})
    report=client.get(q.API+'/report').json()
    chart=next(c for c in report['charts'] if c['id']=='questionnaire_2_wait_minutes')
    filters=chart['table_filters']
    rows=exported(client,'questionnaire_answers',filters)
    assert len(rows)==2 and rows[1][0]==own['number'] and rows[1][-1]=='0'
    assert len(exported(client,'questionnaire_distribution',filters))==3  # zero and the zero-count missing row
    care.user_id('reception');login(client,'reception')
    assert len(exported(client,'questionnaire_answers',filters))==1
    login(client,'admin');other=second_store(client);switch(client,other)
    assert len(exported(client,'questionnaire_answers',filters))==1
    assert len(exported(client,'questionnaire_distribution',filters))==1
    switch(client,1);login(client,'finance')
    assert client.get(q.API+'/export/questionnaire_answers',params=filters).status_code==403
    login(client,'admin');switch(client,'all')
    assert client.get(q.API+'/export/questionnaire_distribution',params=filters).status_code==409


def test_questionnaire_export_and_detail_rendering_contract():
    node=shutil.which('node')
    if not node:pytest.skip('Node helpers are optional; this is not browser acceptance')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,'--test','tests/js/questionnaire_exports.test.cjs'],cwd=root,
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
