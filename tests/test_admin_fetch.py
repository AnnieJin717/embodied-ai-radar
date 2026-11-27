import socket,unittest
from email.message import Message
from subprocess import CompletedProcess
from unittest.mock import Mock,patch
from src.admin import workflow
from src.admin.reader_transport import native_reader
BODY='某机器人公司完成融资，用于技术研发、产品开发和市场拓展。'*5
READER=('Title: 测试\nPublished Time: 2026-11-27\nMarkdown Content:\n'+BODY).encode()
class FetchTests(unittest.TestCase):
 def test_native_reader_keeps_secret_out_of_arguments(self):
  with patch('src.admin.reader_transport.subprocess.run',return_value=CompletedProcess([],0,READER+b'\n200',b'')) as run:
   self.assertEqual(native_reader('https://r.jina.ai/https://example.org/news',{'Authorization':'Bearer fixture-secret'}),READER)
   args,kwargs=run.call_args
   self.assertNotIn('fixture-secret',' '.join(args[0]));self.assertIn(b'fixture-secret',kwargs['input'])
  with self.assertRaises(ValueError):native_reader('https://example.org',{})
 def test_proxy_route_is_tried_when_direct_connection_fails(self):
  results=[CompletedProcess([],28,b'',b''),CompletedProcess([],0,READER+b'\n200',b'')]
  with patch('src.admin.reader_transport.getproxies',return_value={'https':'http://127.0.0.1:7890'}),patch('src.admin.reader_transport.subprocess.run',side_effect=results) as run:
   self.assertEqual(native_reader('https://r.jina.ai/https://example.org',{}),READER)
   self.assertEqual(run.call_count,2)
   self.assertIn(b'noproxy = "*"',run.call_args_list[0].kwargs['input'])
   self.assertIn(b'proxy = "http://127.0.0.1:7890"',run.call_args_list[1].kwargs['input'])
 def test_native_reader_and_python_fallback(self):
  with patch.object(workflow.os,'name','nt'),patch.object(workflow,'native_reader',return_value=READER):
   self.assertEqual(workflow.reader_article('https://example.org')[0],BODY)
  response=Mock();response.read.return_value=READER
  opener=Mock();opener.open.return_value.__enter__=Mock(return_value=response);opener.open.return_value.__exit__=Mock(return_value=False)
  with patch.object(workflow.os,'name','nt'),patch.object(workflow,'native_reader',side_effect=OSError()),patch.object(workflow,'build_opener',return_value=opener):
   self.assertEqual(workflow.reader_article('https://example.org')[0],BODY)
 def test_challenge_pages_are_not_article_text(self):
  self.assertFalse(workflow.usable_article('系统正在检测当前网络环境，请耐心等待。'*10))
  with self.assertRaises(ValueError):workflow.parse_reader_response(b'Title: error\nMarkdown Content:\nverify you are human '+b'x'*100)
 def test_second_public_address_is_attempted(self):
  first,second=Mock(),Mock();first.connect.side_effect=TimeoutError()
  response=Mock();response.status=200;response.headers=Message();response.headers['Content-Type']='text/plain';response.read.return_value=BODY.encode()
  connection=Mock();connection.getresponse.return_value=response
  addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',80)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1',80))]
  with patch.object(workflow.socket,'getaddrinfo',return_value=addresses),patch.object(workflow.socket,'socket',side_effect=[first,second]),patch.object(workflow.http.client,'HTTPConnection',return_value=connection):
   self.assertEqual(workflow.fetch_page('http://example.org/news')[1],BODY)
  first.close.assert_called();second.connect.assert_called_once_with(('1.1.1.1',80));second.close.assert_called()
 def test_private_url_and_failure_diagnostics(self):
  private=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',80))]
  with patch.object(workflow.socket,'getaddrinfo',return_value=private),patch.object(workflow,'native_reader') as native:
   with self.assertRaises(ValueError):workflow.fetch_article('http://localhost/news')
   native.assert_not_called()
  with patch.object(workflow,'public_news_url',side_effect=lambda u:u),patch.object(workflow,'fetch_page',side_effect=TimeoutError()),patch.object(workflow,'reader_article',side_effect=TimeoutError()):
   with self.assertRaisesRegex(ValueError,'尚未调用模型.*超时'):workflow.fetch_article('https://example.org/news')
if __name__=='__main__':unittest.main()
