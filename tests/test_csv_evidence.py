"""CSV source files use the same quarantine, scoped download and byte evidence."""
import pytest
from fastapi import HTTPException
from app.flow_documents import validate_upload
from tests.test_file_security import order,upload,mode,scan
from tests.conftest import login


@pytest.mark.parametrize('raw',[b'a,b\n"unfinished',b'a,b\nvalue,\xff',b'a\x00,b\n1,2',
    ('a,b\n'+'x'*2001+',z').encode(),('a,b\n'+'1,2\n'*5001).encode()])
def test_malformed_or_unbounded_csv_refused(raw):
    with pytest.raises(HTTPException):validate_upload('合成清单.csv',raw)


def test_csv_preserves_bom_and_original_bytes_and_obeys_scan_and_scope(client,monkeypatch):
    mode(monkeypatch,'quarantine')
    row=order(client)
    raw=b'\xef\xbb\xbfline_id,vin,amount_cents\r\n1,LHGCM82633A123456,12345\r\n'
    asset=upload(client,row,content=raw,name='合成车辆来源.csv',category='procurement_contract')
    assert not asset['security']['can_use']
    assert client.get('/api/flow/files/'+str(asset['id'])).status_code==409
    mode(monkeypatch,'structure_only');scan(client,asset['id'],version=asset['security']['version'])
    response=client.get('/api/flow/files/'+str(asset['id']))
    assert response.status_code==200 and response.content==raw
    assert response.headers['content-type'].startswith('text/csv')
    login(client,'inventory')
    assert client.get('/api/flow/files/'+str(asset['id'])).status_code==403
    login(client)
    other=client.post('/api/stores',json={'code':'CSV-B','name':'合成CSV另一店','active':True})
    assert other.status_code==201
    client.headers['X-Store-ID']=str(other.json()['id'])
    assert client.get('/api/flow/files/'+str(asset['id'])).status_code==404
