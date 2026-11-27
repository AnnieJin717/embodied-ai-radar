import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.admin.config import load_project_config,configuration_status
class ConfigTests(unittest.TestCase):
 def test_notepad_names_and_encodings(self):
  for name,encoding in [('.env','utf-8-sig'),('.env.txt','utf-16'),('.env.txt','utf-8')]:
   with self.subTest(name=name,encoding=encoding),tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
    Path(tmp,name).write_text('OPENROUTER_API_KEY=fixture-secret\nOPENROUTER_MODEL=qwen/qwen3-30b-a3b-instruct-2507\n',encoding=encoding)
    result=load_project_config(tmp)
    self.assertTrue(result['ready']);self.assertEqual(result['file'],name)
    self.assertNotIn('fixture-secret',json.dumps(result));self.assertEqual(os.getenv('OPENROUTER_API_KEY'),'fixture-secret')
 def test_missing_file_and_model(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
   result=load_project_config(tmp);self.assertIsNone(result['file']);self.assertEqual(len(result['missing']),2)
   Path(tmp,'.env.txt').write_text('OPENROUTER_API_KEY=fixture-secret\n',encoding='utf-8')
   result=load_project_config(tmp);self.assertEqual(result['missing'],['OPENROUTER_MODEL'])
 def test_live_local_reload_and_precedence(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'ADMIN_LOCAL_CONFIG_RELOAD':'1'},clear=True):
   p=Path(tmp,'.env');p.write_text('OPENROUTER_API_KEY=fixture-one\nOPENROUTER_MODEL=qwen/model-one',encoding='utf-8')
   self.assertTrue(configuration_status(tmp)['ready'])
   p.write_text('OPENROUTER_API_KEY=fixture-two',encoding='utf-8')
   self.assertEqual(configuration_status(tmp)['missing'],['OPENROUTER_MODEL'])
   self.assertEqual(os.getenv('OPENROUTER_API_KEY'),'fixture-two')
 def test_server_environment_keeps_priority(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'OPENROUTER_API_KEY':'deployment-secret','OPENROUTER_MODEL':'qwen/deployment'},clear=True):
   Path(tmp,'.env').write_text('OPENROUTER_API_KEY=file-secret\nOPENROUTER_MODEL=qwen/local',encoding='utf-8')
   result=load_project_config(tmp);self.assertTrue(result['ready']);self.assertEqual(os.getenv('OPENROUTER_API_KEY'),'deployment-secret')
if __name__=='__main__':unittest.main()
