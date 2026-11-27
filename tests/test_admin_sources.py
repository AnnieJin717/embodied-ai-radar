import json,unittest,os
from unittest.mock import patch,Mock
from src.admin import workflow
class SourceTests(unittest.TestCase):
 def test_official_www_is_used(self):
  text='公司发布融资消息，支持技术研发和产品商业化。'*5
  with patch.object(workflow,'public_news_url',side_effect=lambda u:u),patch.object(workflow,'fetch_page',return_value=(None,text,None)) as fetch,patch.object(workflow,'reader_article') as reader:
   self.assertEqual(workflow.fetch_article('https://36kr.com/p/123')[0],text)
   self.assertEqual(fetch.call_args.args[0],'https://www.36kr.com/p/123');reader.assert_not_called()
 def test_only_article_widget_is_used(self):
  text='公司完成融资，投入机器人技术研发和商业化。'*5
  state={'articleDetail':{'articleDetailData':{'data':{'widgetContent':'<p>'+text+'</p>'}},'articleConnectInfoJson':{'content':'不应抽取的推荐内容'}}}
  raw='<script>window.initialState='+json.dumps(state)+';</script>'
  self.assertEqual(workflow.article_from_36kr_state(raw),text)
  self.assertIsNone(workflow.article_from_36kr_state('window.initialState=notJSON;'))
 def test_json_response_mode_is_requested(self):
  response=Mock();response.read.return_value=json.dumps({'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]}).encode()
  opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-secret','ADMIN_MODEL_TRANSPORT':'python'}),patch.object(workflow,'build_opener',return_value=opener):
   result,_=workflow.openrouter([{'role':'user','content':'JSON'}],'qwen/test')
   payload=json.loads(opener.open.call_args.args[0].data)
   self.assertEqual(payload['response_format'],{'type':'json_object'});self.assertTrue(result['ok'])
 def test_unknown_placeholders_are_not_extracted(self):
  fields={'founders':{'value':[],'evidence':''},'website':{'value':'','evidence':''},'name':{'value':'公司','evidence':'公司'}}
  result=workflow.validate_record({'fields':fields,'events':[]},workflow.FIELDS)
  self.assertEqual(list(result['fields']),['name'])
 def test_completed_funding_rule_requires_named_literal_evidence(self):
  body='近日甲科技正式完成超4亿元C4轮融资交割。'
  fields={'funding_history':{'value':['C4轮'],'evidence':body}}
  self.assertEqual(workflow.verified_funding_event('甲科技',fields,body)['type'],'funding')
  self.assertIsNone(workflow.verified_funding_event('乙科技',fields,body))
  future='甲科技计划完成C4轮融资';fields['funding_history']['evidence']=future
  self.assertIsNone(workflow.verified_funding_event('甲科技',fields,future))
 def test_schema_and_unknown_values(self):
  from jsonschema import Draft202012Validator
  schema=workflow.combined_response_format()['json_schema']['schema']
  Draft202012Validator.check_schema(schema)
  good={'category':'full','subjects':[{'name':'甲','fields':{'funding_history':{'value':['A轮'],'evidence':'原文'}},'events':[]}]}
  self.assertFalse(list(Draft202012Validator(schema).iter_errors(good)))
  good['subjects'][0]['fields']['funding_history']['value']=[{'round':'A'}]
  self.assertTrue(list(Draft202012Validator(schema).iter_errors(good)))
  result=workflow.validate_record({'fields':{'founders':{'value':'未披露','evidence':'未披露'}},'events':[]},workflow.FIELDS)
  self.assertEqual(result['fields'],{})
if __name__=='__main__':unittest.main()
