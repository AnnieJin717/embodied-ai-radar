import base64,json,os,tempfile,time,unittest
from pathlib import Path
from threading import Thread
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from src.admin.server import make_server
class AdminTests(unittest.TestCase):
 def test_url_fields_and_user_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   def fetch(url): calls.append(url);return '公开报道正文。某机器人企业宣布完成融资，用于产品研发和商业化落地。'*4,'2026-11-26'
   def extract(text,url,date,taxonomy):
    self.assertGreater(len(text),30)
    return dict(url=url,body_hash='fixture',published_at=date,subjects=[],category='unrelated',elapsed_ms=1)
   server=make_server(('127.0.0.1',0),Path(tmp)/'db.sqlite','test-password',fetch=fetch,extract=extract)
   thread=Thread(target=server.serve_forever,daemon=True);thread.start()
   root=f'http://127.0.0.1:{server.server_port}'
   auth='Basic '+base64.b64encode(b'tester:test-password').decode()
   def request(path,data=None,token=auth):
    req=Request(root+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':token,'Content-Type':'application/json'})
    with urlopen(req,timeout=5) as r:return json.load(r)
   try:
    with self.assertRaises(HTTPError):request('/api/article',{'url':'https://example.org/news'},'')
    preview=request('/api/article',{'url':'https://example.org/news'})
    self.assertGreater(preview['characters'],30)
    task=request('/api/extract',{'url':'https://example.org/news'})
    for _ in range(100):
     job=request('/api/extract/jobs/'+task['id'])
     if job['status']!='running':break
     time.sleep(.02)
    self.assertEqual(job['status'],'succeeded');self.assertIn('fetch_ms',job['result']);self.assertEqual(len(calls),1)
    companies=request('/api/companies');self.assertEqual(len(companies),60);self.assertIn('founders',companies[0])
    updated=request('/api/company',{'id':companies[0]['id'],'fields':{'founder_education':'人工核实测试值'}})
    self.assertEqual(updated['founder_education'],'人工核实测试值')
    os.environ['USER_DATA_TOKEN']='service-test'
    with self.assertRaises(HTTPError):request('/api/v1/published')
    data=request('/api/v1/published',token='Bearer service-test')
    self.assertEqual(data['schema_version'],'1');self.assertEqual(len(data['companies']),60)
    self.assertNotIn('provenance',data['companies'][0]);self.assertNotIn('subjects',data)
    with self.assertRaises(HTTPError):request('/api/companies',token='Bearer service-test')
   finally:server.shutdown();server.server_close();os.environ.pop('USER_DATA_TOKEN',None)
if __name__=='__main__':unittest.main()
