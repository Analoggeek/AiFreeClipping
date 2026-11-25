"""Loopback-only, proxy/redirect-free transport for local AI inference.

Trust boundary: the user-controlled local runtime must itself be configured for
local inference. CLIPOS refuses remote endpoints and Ollama remote/cloud models;
it is not an OS firewall for an independently modified local server.
"""
from __future__ import annotations
import ipaddress
import json
from urllib.parse import urlsplit
import urllib.request


class LocalAIError(RuntimeError):
    pass


def local_endpoint(host: str) -> str:
    try:
        url=urlsplit(host)
        if url.scheme not in ('http','https') or url.username or url.password:
            raise ValueError('Expected HTTP(S) without credentials')
        if url.path not in ('','/') or url.query or url.fragment:
            raise ValueError('Endpoint cannot contain a path, query or fragment')
        name=url.hostname
        if name=='localhost':name='127.0.0.1'  # no DNS/rebinding for localhost
        address=ipaddress.ip_address(name or '')
        if not address.is_loopback:raise ValueError('Only loopback addresses are allowed')
        port=url.port
        if port is None:port=443 if url.scheme=='https' else 80
        literal=f'[{address}]' if address.version==6 else str(address)
        return f'{url.scheme}://{literal}:{port}'
    except (ValueError,TypeError) as exc:
        raise LocalAIError('Local AI requires localhost/127.0.0.1/::1; remote inference is prohibited') from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise LocalAIError('Local AI redirects are prohibited')


class LocalOllama:
    def __init__(self,host='http://127.0.0.1:11434',timeout=120):
        self.host=local_endpoint(host)
        self.timeout=max(.1,min(float(timeout),180))
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())

    def request(self,path,payload=None):
        if path not in ('/api/tags','/api/show','/api/generate','/api/ps'):
            raise LocalAIError('Unsupported local inference operation')
        data=json.dumps(payload,allow_nan=False).encode() if payload is not None else None
        req=urllib.request.Request(self.host+path,data=data,headers={'Content-Type':'application/json','User-Agent':'CLIPOS-local-AI'})
        try:
            with self.opener.open(req,timeout=self.timeout) as response:
                raw=response.read(2_000_001)
                if len(raw)>2_000_000:raise LocalAIError('Local AI response exceeds size limit')
                result=json.loads(raw)
            if not isinstance(result,dict):raise LocalAIError('Expected local AI JSON object')
            if result.get('error'):raise LocalAIError(str(result['error'])[:300])
            return result
        except LocalAIError:raise
        except Exception as exc:raise LocalAIError(f'Local Ollama request failed: {type(exc).__name__}') from exc

    def require_local_model(self,model):
        if not isinstance(model,str) or not model.strip() or len(model)>160 or 'cloud' in model.lower():
            raise LocalAIError('Choose an installed local model, not a cloud model')
        info=self.request('/api/show',{'model':model})
        def has_remote(value):
            if isinstance(value,dict):
                return any((key in ('remote_host','remote_model') and bool(item)) or has_remote(item) for key,item in value.items())
            if isinstance(value,list):return any(has_remote(item) for item in value)
            return False
        details=info.get('details',{});metadata=info.get('model_info',{})
        if has_remote(info) or details.get('format')!='gguf' or not metadata.get('general.architecture'):
            raise LocalAIError('Model does not expose installed local GGUF weights; remote/unknown models are refused')
        return info

    def generate(self,prompt,model,*,json_output=False,images=None,options=None):
        info=self.require_local_model(model)
        if images is not None:
            import base64
            if not isinstance(images,list) or not 1<=len(images)<=4:raise LocalAIError('Use 1–4 bounded image frames')
            if 'vision' not in info.get('capabilities',[]):raise LocalAIError('Installed local model does not advertise vision support')
            for image in images:
                if not isinstance(image,str) or len(image)>900000:raise LocalAIError('Vision image exceeds local input bound')
                try:raw=base64.b64decode(image,validate=True)
                except (ValueError,TypeError) as exc:raise LocalAIError('Invalid encoded vision frame') from exc
                if not raw.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')):raise LocalAIError('Expected encoded JPEG/PNG frame')
        if not isinstance(prompt,str) or len(prompt)>40000:raise LocalAIError('Prompt exceeds local input budget')
        payload={'model':model,'prompt':prompt,'stream':False,'keep_alive':'2m',
                 'options':{'temperature':.1,'num_predict':1500,'num_ctx':8192}}
        if options is not None:
            if not isinstance(options,dict) or set(options)-{'num_ctx','num_predict'}:raise LocalAIError('Unsupported inference options')
            for key,value in options.items():
                hi=8192 if key=='num_ctx' else 2000
                if type(value) is not int or not 128<=value<=hi:raise LocalAIError('Inference option outside safe memory/output bounds')
            payload['options'].update(options)
        if images is not None:payload['images']=images
        if json_output:payload['format']='json'
        result=self.request('/api/generate',payload)
        if result.get('done') is False:raise LocalAIError('Incomplete local generation')
        text=result.get('response')
        if not isinstance(text,str) or not text.strip():raise LocalAIError('Local model produced no response')
        return text
