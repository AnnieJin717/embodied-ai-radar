import copy,json,os,time,unittest
from unittest.mock import patch
from urllib.error import HTTPError
from src.admin.workflow import extract,validate_combined
TEXT='甲机器人完成A轮融资。乙机器人发布新产品。丙机器人近日发布原型。'*4
def record(name='甲机器人'):
 return {'name':name,'fields':{'founders':{'value':['张某'],'evidence':'不存在的原文'},'business_description':{'value':'机器人','evidence':'甲机器人'}},'events':[{'type':'prototype','summary':'发布原型','event_date':'近日','evidence':'丙机器人近日发布原型'}]}
class SpeedTests(unittest.TestCase):
 def test_fast_multi_subject_preserves_validation(self):
  def call(*_):return {'category':'full','subjects':[record('甲机器人'),record('乙机器人')]},{'prompt_tokens':10,'completion_tokens':20}
  with patch.dict(os.environ,{'ADMIN_EXTRACTION_MODE':'fast'}):r=extract(TEXT,None,None,{},call=call)
  self.assertEqual(r['llm_calls'],1);self.assertEqual(len(r['subjects']),2)
  self.assertFalse(r['subjects'][0]['fields']['founders']['verified_quote'])
  self.assertTrue(r['subjects'][0]['fields']['business_description']['verified_quote'])
  self.assertTrue(r['subjects'][0]['events'][0]['date_needs_review'])
  self.assertEqual(r['usage']['prompt_tokens'],10)
 def test_partial_and_unrelated(self):
  for category,subjects in [('partial',[{**record(),'events':[]}]),('unrelated',[])]:
   with patch.dict(os.environ,{'ADMIN_EXTRACTION_MODE':'fast'}):
    r=extract(TEXT,None,None,{},call=lambda *_:({'category':category,'subjects':copy.deepcopy(subjects)},{}))
   self.assertEqual(r['category'],category);self.assertEqual(r['llm_calls'],1)
 def test_bad_schema_retries_without_accepting(self):
  calls=[]
  def bad(*_):calls.append(1);return {'category':'full','subjects':[{'name':'甲','fields':{'founders':{'value':[123],'evidence':'甲'}},'events':[]}]},{}
  with patch.dict(os.environ,{'ADMIN_EXTRACTION_MODE':'fast'}),self.assertRaises(ValueError):extract(TEXT,None,None,{},call=bad)
  self.assertEqual(len(calls),2)
  for d in [{'category':'full','subjects':[record(),record()]},{'category':'unrelated','subjects':[record()]}]:
   with self.assertRaises(ValueError):validate_combined(d)
 def test_permanent_error_does_not_retry(self):
  calls=[]
  def unauthorized(*_):calls.append(1);raise HTTPError('https://example.org',401,'Unauthorized',{},None)
  with patch.dict(os.environ,{'ADMIN_EXTRACTION_MODE':'fast'}),self.assertRaises(ValueError):extract(TEXT,None,None,{},call=unauthorized)
  self.assertEqual(len(calls),1)
 def test_staged_and_fast_comparison(self):
  measurements={}
  for mode in ['staged','fast']:
   calls=[]
   def call(messages,model):
    calls.append(1);time.sleep(.04)
    if mode=='fast':data={'category':'full','subjects':[record(n) for n in ['甲','乙','丙']]}
    elif len(calls)==1:data={'category':'full','subjects':['甲','乙','丙']}
    else:data=record(['甲','乙','丙'][len(calls)-2])
    return data,{}
   with patch.dict(os.environ,{'ADMIN_EXTRACTION_MODE':mode}):r=extract(TEXT,None,None,{},call=call)
   measurements[mode]={'calls':r['llm_calls'],'elapsed_ms':r['elapsed_ms']}
   self.assertEqual(len(r['subjects']),3)
  self.assertEqual(measurements['staged']['calls'],4);self.assertEqual(measurements['fast']['calls'],1)
  print('SIMULATED fixed 40ms/request, NOT live model benchmark:',json.dumps(measurements))
if __name__=='__main__':unittest.main()
