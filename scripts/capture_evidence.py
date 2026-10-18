"""Capture actual localhost dashboards with headless Edge and standard-library CDP."""
import subprocess, socket, urllib.request, time, json, os, base64, struct
from pathlib import Path
from urllib.parse import urlparse, quote, urlencode
root=Path.cwd();out=root/'docs/evidence/integrator'
edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
assert edge.exists(),'Edge not found'
sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
proc=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port='+str(port),'--remote-allow-origins=http://127.0.0.1:'+str(port),'--user-data-dir='+str(root/'.browser-lab'),'--window-size=1600,1500','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
ws=None
try:
    for _ in range(50):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json') as r:tabs=json.load(r)
            tab=next(t for t in tabs if t['type']=='page');break
        except Exception:time.sleep(0.2)
    u=urlparse(tab['webSocketDebuggerUrl']);ws=socket.create_connection((u.hostname,u.port),timeout=30)
    ws.sendall((f'GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+base64.b64encode(os.urandom(16)).decode()+f'\r\nSec-WebSocket-Version: 13\r\nOrigin: http://127.0.0.1:{port}\r\n\r\n').encode())
    handshake=b''
    while b'\r\n\r\n' not in handshake:handshake+=ws.recv(4096)
    assert handshake.startswith(b'HTTP/1.1 101'),handshake
    def exact(n):
        data=b''
        while len(data)<n:
            chunk=ws.recv(n-len(data))
            if not chunk:raise RuntimeError('CDP websocket closed')
            data+=chunk
        return data
    def read():
        h=exact(2);length=h[1]&127
        if length==126:length=struct.unpack('!H',exact(2))[0]
        elif length==127:length=struct.unpack('!Q',exact(8))[0]
        return json.loads(exact(length))
    sequence=0
    def call(method,params=None):
        global sequence
        sequence+=1
        payload=json.dumps({'id':sequence,'method':method,'params':params or {}}).encode();mask=os.urandom(4)
        header=bytes([129,128|len(payload)]) if len(payload)<126 else bytes([129,254])+struct.pack('!H',len(payload))
        ws.sendall(header+mask+bytes(c^mask[i%4] for i,c in enumerate(payload)))
        while True:
            result=read()
            if result.get('id')==sequence:
                if 'error' in result:raise RuntimeError(result['error'])
                return result.get('result',{})
    call('Network.enable');call('Page.enable')
    call('Emulation.setDeviceMetricsOverride',{'width':1600,'height':1500,'deviceScaleFactor':1,'mobile':False})
    auth=base64.b64encode(b'lab:local-lab-only').decode()
    call('Network.setExtraHTTPHeaders',{'headers':{'Authorization':'Basic '+auth}})
    trace=json.loads((out/'validation.json').read_text(encoding='utf-8'))['trace_id']
    panes={'logs':{'datasource':'loki','queries':[{'refId':'A','expr':'{service_name=~"service-a|service-b|data-service"} | trace_id="'+trace+'"','queryType':'range'}],'range':{'from':'now-1h','to':'now'}}}
    pages=[('jaeger-trace.png','http://127.0.0.1:26686/trace/'+trace),('grafana-dashboard.png','http://127.0.0.1:23000/d/credit-lab?orgId=1&from=now-30m&to=now'),('grafana-logs.png','http://127.0.0.1:23000/explore?'+urlencode({'schemaVersion':1,'panes':json.dumps(panes),'orgId':1}))]
    records=[]
    for filename,url in pages:
        call('Page.navigate',{'url':url});time.sleep(8)
        body=call('Runtime.evaluate',{'expression':'document.body.innerText','returnByValue':True})['result'].get('value','')
        shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        (out/filename).write_bytes(base64.b64decode(shot['data']))
        records.append({'file':filename,'url':url,'visible_text':body[:10000]})
    (out/'screenshots.json').write_text(json.dumps(records,indent=2))
    print('Capturas locales guardadas:',', '.join(r['file'] for r in records))
finally:
    if ws:ws.close()
    proc.terminate()
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:proc.kill()
