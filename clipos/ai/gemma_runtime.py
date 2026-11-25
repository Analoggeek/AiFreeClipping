"""Explicit model lifecycle on the existing loopback-only Ollama trust boundary.

Only a user-confirmed install contacts the model registry (through Ollama).
Normal inference/status never pulls weights or contacts a cloud AI service.
"""
import json
import re
import urllib.request
from ..core.local_ai import LocalOllama, LocalAIError

DEFAULT_MODEL = 'gemma:7b'
# Verified Ollama library identifiers; pull still fails visibly if unavailable.
GEMMA_TAGS = ('gemma:7b','gemma:7b-instruct-v1.1-q4_K_S','gemma:7b-instruct-v1.1-q3_K_S','gemma:2b')
PROFILES = {'Low memory': {'num_ctx':2048,'num_predict':1000},
            'Balanced': {'num_ctx':4096,'num_predict':1500},
            'High quality': {'num_ctx':8192,'num_predict':2000}}

class GemmaRuntime:
    def __init__(self, host='http://127.0.0.1:11434'):
        self.client=LocalOllama(host,timeout=180)

    def status(self):
        tags=self.client.request('/api/tags').get('models',[])
        return [dict(name=x['name'],size=x.get('size',0)) for x in tags
                if isinstance(x,dict) and isinstance(x.get('name'),str) and 'cloud' not in x['name'].lower()]

    def memory(self):
        rows=self.client.request('/api/ps').get('models',[])
        return [{'name':x.get('name','unknown'),'size':x.get('size',0),'vram':x.get('size_vram',0)} for x in rows if isinstance(x,dict)]

    def pull(self, model, *, consent=False, progress=None, cancelled=None):
        if not consent:raise LocalAIError('Explicit permission is required before downloading model weights')
        if model not in GEMMA_TAGS:raise LocalAIError('Select a verified Gemma library tag for download')
        request=urllib.request.Request(self.client.host+'/api/pull',data=json.dumps({'model':model,'stream':True}).encode(),headers={'Content-Type':'application/json'})
        success=False
        try:
            with self.client.opener.open(request,timeout=30) as response:
                while True:
                    if cancelled and cancelled():raise LocalAIError('Model download cancelled; Ollama may retain reusable partial blobs')
                    line=response.readline(65537)
                    if not line:break
                    if len(line)>65536:raise LocalAIError('Oversized Ollama download status')
                    data=json.loads(line)
                    if data.get('error'):raise LocalAIError(str(data['error'])[:300])
                    if progress:progress(data)
                    success=data.get('status')=='success'
            if not success:raise LocalAIError('Model download ended without confirmation')
            return self.client.require_local_model(model)
        except LocalAIError:raise
        except Exception as exc:raise LocalAIError(f'Gemma download failed: {type(exc).__name__}; check local Ollama logs') from exc

    def unload(self,model):
        self.client.require_local_model(model)
        return self.client.request('/api/generate',{'model':model,'keep_alive':0,'stream':False})

    def verify_offline(self,model):
        self.client.require_local_model(model)
        text=self.client.generate('Reply with the word READY.',model)
        return 'Local GGUF inference responded: '+text[:160]+'. This checks Ollama only; it is not a whole-system firewall or Whisper/vision certification.'
