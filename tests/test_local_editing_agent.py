"""Local-only transport and bounded agent safety; server responses are fixtures,
not evidence that a real LLM/vision model was run in this test environment.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from unittest.mock import patch
import pytest
from clipos.core.local_ai import LocalOllama,LocalAIError,local_endpoint
from clipos.db.database import Database


@pytest.mark.parametrize('host',['https://api.openai.com','http://192.168.1.3:11434','http://0.0.0.0:11434','http://127.0.0.1.attacker.test','http://localhost@attacker.test','file:///tmp/model','http://localhost/path','http://localhost/?key=x','http://user:pass@127.0.0.1','http://[::ffff:192.168.1.1]'])
def test_remote_and_ambiguous_endpoints_rejected_before_io(host):
    with patch('urllib.request.build_opener') as opener:
        with pytest.raises(LocalAIError):LocalOllama(host)
        opener.assert_not_called()


@pytest.mark.parametrize('host,result',[('http://localhost:11434','http://127.0.0.1:11434'),('http://[::1]:11434','http://[::1]:11434'),('http://127.0.0.1','http://127.0.0.1:80')])
def test_numeric_loopback_canonicalization(host,result):assert local_endpoint(host)==result


@pytest.fixture
def runtime():
    state={'requests':[],'remote':False,'redirect':False,'response':{'version':1,'settings':{'caption_size':64},'reason':'Larger captions'}}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            state['requests'].append((self.path,payload))
            if state['redirect']:
                self.send_response(302);self.send_header('Location','http://192.0.2.1/private');self.end_headers();return
            if self.path=='/api/show':
                result={'details':{'format':'gguf'},'model_info':{'general.architecture':'qwen2'}}
                if state['remote']:result['remote_host']='https://cloud.example'
            else:result={'response':json.dumps(state['response']),'done':True}
            raw=json.dumps(result).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
        def log_message(self,*_):pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',state
    server.shutdown();server.server_close();thread.join(2)


def test_local_model_checked_before_generation_and_environment_proxy_ignored(runtime,monkeypatch):
    host,state=runtime;monkeypatch.setenv('HTTP_PROXY','http://192.0.2.1:1');monkeypatch.setenv('http_proxy','http://192.0.2.1:1')
    text=LocalOllama(host).generate('Rank these excerpts',model='qwen2.5:3b',json_output=True)
    assert json.loads(text)==state['response']
    assert [x[0] for x in state['requests']]==['/api/show','/api/generate']
    assert state['requests'][1][1]['stream'] is False
    assert state['requests'][1][1]['format']=='json'


def test_cloud_model_never_receives_prompt(runtime):
    host,state=runtime;state['remote']=True
    with pytest.raises(LocalAIError):LocalOllama(host).generate('PRIVATE TRANSCRIPT','qwen:3b')
    assert len(state['requests'])==1 and state['requests'][0][0]=='/api/show'
    assert 'PRIVATE TRANSCRIPT' not in json.dumps(state['requests'])


def test_cloud_name_and_redirect_refused(runtime):
    host,state=runtime
    with pytest.raises(LocalAIError):LocalOllama(host).generate('private','qwen:cloud')
    assert not state['requests']
    state['redirect']=True
    with pytest.raises(LocalAIError):LocalOllama(host).generate('private','qwen:3b')
    assert len(state['requests'])==1
