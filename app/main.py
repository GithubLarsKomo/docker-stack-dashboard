import os, json, subprocess, time, re
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

NETWORK=os.getenv('NETWORK','ai-stack')
MCP_NETWORK=os.getenv('MCP_NETWORK','mcp-network')
HOST_GATEWAY=os.getenv('HOST_GATEWAY','host.docker.internal')
TIMEOUT=int(os.getenv('TIMEOUT','5'))
app=FastAPI(title='AI Stack Ops Dashboard',version='5.0.0')
app.mount('/static',StaticFiles(directory='/app/static'),name='static')

SERVICE_HINTS={
 'firecrawl':{'label':'Firecrawl','match':['firecrawl-api-1','firecrawl'],'port':3002,'role':'external-api','critical':'high','paths':[('POST','/v1/scrape','{"url":"https://example.com","formats":["markdown"]}'),('GET','/','')]},
 'ollama':{'label':'Ollama','match':['ollama'],'port':11434,'role':'llm-runtime','critical':'high','paths':[('GET','/api/tags',''),('GET','/','')]},
 'n8n':{'label':'n8n','match':['n8n'],'port':5678,'role':'workflow','critical':'high','paths':[('GET','/',''),('GET','/healthz','')]},
 'openwebui':{'label':'OpenWebUI','match':['open-webui','openwebui'],'port':8080,'role':'chat-ui','critical':'high','paths':[('GET','/',''),('GET','/health','')]},
 'searxng':{'label':'SearXNG','match':['searxng'],'port':8080,'role':'search','critical':'medium','paths':[('GET','/',''),('GET','/search?q=test&format=json','')]},
 'neo4j':{'label':'Neo4j','match':['neo4j'],'port':7474,'role':'graph-db','critical':'medium','paths':[('GET','/','')]},
 'mariadb':{'label':'MariaDB','match':['mariadb'],'port':3306,'role':'db','critical':'high','tcp':True,'paths':[]},
 'whisper':{'label':'Whisper API','match':['whisper-api'],'port':8008,'role':'asr','critical':'medium','paths':[('GET','/health',''),('GET','/',''),('GET','/docs','')]},
 'pocket':{'label':'Pocket TTS','match':['pocket-tts-api'],'port':7861,'role':'tts','critical':'medium','paths':[('GET','/health',''),('GET','/voices',''),('GET','/api/tts?text=test',''),('GET','/docs',''),('GET','/openapi.json',''),('GET','/','')]},
 'dashboard':{'label':'Ops Dashboard','match':['docker-stack-dashboard'],'port':8088,'role':'ops-dashboard','critical':'medium','paths':[('GET','/',''),('GET','/api/status','')]},
 'crawl4ai':{'label':'Crawl4AI','match':['crawl4ai'],'port':11235,'role':'crawler','critical':'medium','paths':[('GET','/health',''),('POST','/crawl','{"url":"https://example.com"}')]}
}
MCP_WORDS=['mcp','pubmed','openfda','patent','wikipedia','uniprot','clinicaltrials','openalex','medicare','medicaid','duckduckgo','biomcp','federal-regulations','medical-codes','healthcare-billing', 'docling']
INTERNAL_WORDS=['redis','postgres','rabbitmq','foundationdb','valkey','mysql']
PROMPTS={'diagnose':'diagnose this component and explain root causes','fix':'produce exact remediation commands and patches','endpoint':'identify or create suitable health/ready/function endpoints','security':'review and harden this component','networking':'fix Docker network, DNS and port problems','stability':'eliminate restart loops and flaky behavior','mcp':'repair and standardize MCP/SSE/Streamable-HTTP integration','agent-ready':'prepare for future SSH-based repair agent without implementing SSH'}


def run(cmd,timeout=TIMEOUT):
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e:
        return 1,'',str(e)

def jl(cmd):
    c,o,e=run(cmd); out=[]
    if c: return out
    for line in o.splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def j(cmd,fb):
    c,o,e=run(cmd)
    if c or not o: return fb
    try: return json.loads(o)
    except Exception: return fb

def rows(): return jl(['docker','ps','-a','--format','{{json .}}'])
def inspect(n):
    d=j(['docker','inspect',n],[])
    return d[0] if d else {}
def nets(n): return ((inspect(n).get('NetworkSettings') or {}).get('Networks') or {})
def state(n): return ((inspect(n).get('State') or {}).get('Status')) or 'missing'
def running(n): return state(n)=='running'
def health(n):
    h=(inspect(n).get('State') or {}).get('Health')
    return h.get('Status','none') if h else 'none'
def labels(n): return (inspect(n).get('Config') or {}).get('Labels') or {}
def compose(n):
    l=labels(n)
    return {'project':l.get('com.docker.compose.project',''),'service':l.get('com.docker.compose.service',''),'working_dir':l.get('com.docker.compose.project.working_dir',''),'config_files':l.get('com.docker.compose.project.config_files','')}
def porttxt(n):
    c,o,e=run(['docker','port',n],2); return o if c==0 else ''
def published(n):
    res={}; ps=((inspect(n).get('NetworkSettings') or {}).get('Ports') or {})
    for cp,bs in ps.items():
        if not bs: continue
        try: target=int(cp.split('/')[0])
        except: continue
        for b in bs:
            try: res.setdefault(target,[]).append(int(b['HostPort']))
            except: pass
    return res
def exposed(n):
    cfg=(inspect(n).get('Config') or {}).get('ExposedPorts') or {}; out=[]
    for k in cfg:
        try: out.append(int(k.split('/')[0]))
        except: pass
    return sorted(set(out))
def role(n):
    for h in SERVICE_HINTS.values():
        if n in h['match']: return h['role']
    low=n.lower()
    if any(w in low for w in MCP_WORDS): return 'mcp'
    if any(w in low for w in INTERNAL_WORDS): return 'internal'
    if any(w in low for w in ['migration','init','seed','setup']): return 'job'
    return 'unknown'
def critical(n):
    for h in SERVICE_HINTS.values():
        if n in h['match']: return h['critical']
    return 'medium' if role(n) in ['mcp','internal'] else 'low'
def dash_name():
    hn=os.getenv('HOSTNAME','')
    for r in rows():
        n=r.get('Names',''); sid=(inspect(n).get('Id') or '')[:12]
        if hn and (hn.startswith(sid) or sid.startswith(hn[:12])): return n
    return None
def same(a,b): return bool(set(nets(a)) & set(nets(b)))
def pick(names,net=NETWORK):
    for n in ['open-webui','n8n','docker-stack-dashboard','firecrawl-api-1','ollama',dash_name() or '']:
        if n in names and running(n) and net in nets(n): return n
    for n in names:
        if running(n) and net in nets(n): return n
    return ''
def curl(src,url,method='GET',payload='',sse=False):
    flags=f"-sS --max-time {TIMEOUT} -w '\\nHTTP_CODE:%{{http_code}}'"
    if method=='POST': inner=f"curl --noproxy '*' {flags} -X POST -H 'Content-Type: application/json' -d '{payload}' '{url}'"
    elif method=='OPTIONS': inner=f"curl --noproxy '*' {flags} -X OPTIONS '{url}'"
    else: inner=f"curl --noproxy '*' {flags} '{url}'"
    t=time.time(); c,o,e=run(['docker','exec',src,'sh','-lc',inner],TIMEOUT+3)
    code=None; body=o; m=re.search(r'HTTP_CODE:(\d+)$',o or '')
    if m: code=int(m.group(1)); body=o[:m.start()].strip()
    ok=(c==0 and code is not None and 200<=code<400)
    reachable=ok or code in [401,403,405,426] or (sse and body.startswith('event:'))
    if sse and body.startswith('event:'): ok=True; reachable=True
    return {'source':src,'url':url,'method':method,'http_code':code,'ok':ok,'reachable':reachable,'exit':c,'ms':int((time.time()-t)*1000),'error':e[-700:],'sample':body[:1000]}
def localcurl(url,method='GET',payload='',sse=False):
    cmd=['curl','--noproxy','*','-sS','--max-time',str(TIMEOUT),'-w','\nHTTP_CODE:%{http_code}']
    if method=='POST': cmd+=['-X','POST','-H','Content-Type: application/json','-d',payload]
    elif method=='OPTIONS': cmd+=['-X','OPTIONS']
    cmd.append(url); t=time.time(); c,o,e=run(cmd,TIMEOUT+2)
    code=None; body=o; m=re.search(r'HTTP_CODE:(\d+)$',o or '')
    if m: code=int(m.group(1)); body=o[:m.start()].strip()
    ok=(c==0 and code is not None and 200<=code<400); reachable=ok or code in [401,403,405,426] or (sse and body.startswith('event:'))
    if sse and body.startswith('event:'): ok=True; reachable=True
    return {'source':'dashboard','url':url,'method':method,'http_code':code,'ok':ok,'reachable':reachable,'exit':c,'ms':int((time.time()-t)*1000),'error':e[-700:],'sample':body[:1000]}
def tcp(src,host,port):
    inner=f"python3 - <<'PY'\nimport socket,sys\ns=socket.socket();s.settimeout(3)\ntry:\n s.connect(('{host}',{int(port)})); print('ok'); sys.exit(0)\nexcept Exception as e:\n print(e); sys.exit(1)\nPY"
    t=time.time(); c,o,e=run(['docker','exec',src,'sh','-lc',inner],6)
    return {'source':src,'url':f'tcp://{host}:{port}','method':'TCP','http_code':None,'ok':c==0,'reachable':c==0,'exit':c,'ms':int((time.time()-t)*1000),'error':(e or o)[-700:],'sample':o[:300]}

def cand_ports(n):
    ps=set(exposed(n)); ps.update(published(n).keys())
    if not ps: ps.update([80,3000,3001,3002,3010,5000,5050,5678,7474,7860,7861,8000,8008,8080,8088,11434])
    return sorted(ps)

def service_container(h,names):
    for m in h['match']:
        if m in names: return m
    return None

def discover_service(n,names):
    if not running(n): return {'container':n,'type':'service','best':None,'endpoints':[],'recommendation':'Container läuft nicht.'}
    hint=next((h for h in SERVICE_HINTS.values() if n in h['match']),None)
    tst=pick(names)
    if hint and hint.get('tcp'):
        ch=tcp(tst,n,hint['port']) if tst else None
        return {'container':n,'type':'tcp','best':ch if ch and ch['ok'] else None,'endpoints':[ch] if ch else [],'recommendation':'' if ch and ch['ok'] else 'TCP nicht erreichbar.'}
    paths=(hint or {}).get('paths',[])+[('GET',p,'') for p in ['/health','/healthz','/ready','/docs','/openapi.json','/']]
    seen=set(); paths=[x for x in paths if not ((x[0],x[1]) in seen or seen.add((x[0],x[1])))]
    results=[]
    for port in cand_ports(n)[:12]:
        for method,path,payload in paths[:16]:
            if tst and same(tst,n):
                r=curl(tst,f'http://{n}:{port}{path}',method,payload); results.append(r)
                if r['ok']: return {'container':n,'type':'service','best':r,'endpoints':results[:80],'recommendation':''}
    for target,hps in published(n).items():
        for hp in sorted(set(hps)):
            for method,path,payload in paths[:16]:
                r=localcurl(f'http://{HOST_GATEWAY}:{hp}{path}',method,payload); results.append(r)
                if r['ok']: return {'container':n,'type':'service','best':r,'endpoints':results[:80],'recommendation':''}
    return {'container':n,'type':'service','best':None,'endpoints':results[:80],'recommendation':'Kein geeigneter Health-/Docs-/Root-Endpoint erkannt.'}

def discover_mcp(n,names):
    if not running(n): return {'container':n,'type':'mcp','transport':'unknown','best':None,'endpoints':[],'recommendation':'Container läuft nicht.'}
    tst=pick(names,MCP_NETWORK) or pick(names,NETWORK)
    paths=[('GET','/sse','','sse'),('GET','/mcp','','streamable-http-discovery'),('POST','/mcp','{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ops-dashboard","version":"5.0"}}}','streamable-http-initialize'),('OPTIONS','/mcp','','streamable-http-options'),('GET','/message','','supergateway-message'),('GET','/health','','health'),('GET','/','','root')]
    results=[]
    for port in cand_ports(n)[:12]:
        for method,path,payload,meaning in paths:
            if tst and same(tst,n):
                r=curl(tst,f'http://{n}:{port}{path}',method,payload,sse=(path=='/sse')); r['meaning']=meaning; results.append(r)
                if r['ok'] or (r['reachable'] and path in ['/mcp','/sse']):
                    tr='sse' if path=='/sse' else ('streamable-http' if path=='/mcp' else 'http')
                    return {'container':n,'type':'mcp','transport':tr,'best':r,'endpoints':results[:80],'recommendation':'' if r['ok'] else 'Erreichbar, aber Methode/Auth/Handshake prüfen.'}
    for target,hps in published(n).items():
        for hp in sorted(set(hps)):
            for method,path,payload,meaning in paths:
                r=localcurl(f'http://{HOST_GATEWAY}:{hp}{path}',method,payload,sse=(path=='/sse')); r['meaning']=meaning; results.append(r)
                if r['ok'] or (r['reachable'] and path in ['/mcp','/sse']):
                    tr='sse' if path=='/sse' else ('streamable-http' if path=='/mcp' else 'http')
                    return {'container':n,'type':'mcp','transport':tr,'best':r,'endpoints':results[:80],'recommendation':'' if r['ok'] else 'Erreichbar, aber Methode/Auth/Handshake prüfen.'}
    return {'container':n,'type':'mcp','transport':'unknown','best':None,'endpoints':results[:80],'recommendation':'Kein MCP/SSE/Streamable-HTTP Endpoint erkannt.'}

def stats(): return {r.get('Name'):r for r in jl(['docker','stats','--no-stream','--format','{{json .}}'])}
def gpu():
    c,o,e=run(['nvidia-smi','--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],3)
    if c: return {'available':False,'error':e or o}
    gs=[]
    for line in o.splitlines():
        p=[x.strip() for x in line.split(',')]
        if len(p)>=5: gs.append({'name':p[0],'temp_c':p[1],'util_pct':p[2],'mem_used_mb':p[3],'mem_total_mb':p[4]})
    return {'available':True,'gpus':gs}
def log_errors(n):
    c,o,e=run(['docker','logs','--tail','180',n],3)
    keys=['error','fatal','exception','traceback','unhealthy','connection refused','failed','typeerror','permission denied','cannot connect','warn']
    return [x[-600:] for x in (o+'\n'+e).splitlines() if any(k in x.lower() for k in keys)][-40:]

def collect():
    _,dv,_=run(['docker','version','--format','{{.Server.Version}}']); _,ctx,_=run(['docker','context','show']); _,hn,_=run(['hostname'])
    rs=rows(); names=[r.get('Names','') for r in rs if r.get('Names')]; st=stats()
    cont=[]
    for r in rs:
        n=r.get('Names',''); ins=inspect(n)
        cont.append({'name':n,'image':r.get('Image',''),'state':state(n),'status_text':r.get('Status',''),'health':health(n),'restart_count':ins.get('RestartCount',0),'role':role(n),'critical':critical(n),'networks':[{'name':k,'ip':v.get('IPAddress','')} for k,v in nets(n).items()],'ports':porttxt(n),'published_ports':published(n),'exposed_ports':exposed(n),'in_ai_stack':NETWORK in nets(n),'in_mcp_network':MCP_NETWORK in nets(n),'is_dashboard':n==dash_name(),'stats':st.get(n,{}),'compose':compose(n)})
    services=[]
    for key,h in SERVICE_HINTS.items():
        cn=service_container(h,names)
        if not cn:
            services.append({'key':key,'label':h.get('label',key),'container':None,'ok':False,'state':'missing','role':h['role'],'critical':h['critical'],'best':None,'recommendation':'Container nicht gefunden.'}); continue
        d=discover_service(cn,names)
        services.append({'key':key,'label':h.get('label',key),'container':cn,'ok':bool(d.get('best')),'state':state(cn),'role':h['role'],'critical':h['critical'],'expected_network':NETWORK,'in_expected_network':NETWORK in nets(cn),'best':d.get('best'),'endpoints':d.get('endpoints',[]),'recommendation':d.get('recommendation','')})
    mcps=[]
    for c in sorted([x for x in cont if x['role']=='mcp'], key=lambda z:z['name']):
        d=discover_mcp(c['name'],names); best=d.get('best')
        mcps.append({'label':c['name'],'container':c['name'],'ok':bool(best and (best.get('ok') or best.get('reachable'))),'state':c['state'],'role':'mcp','critical':c['critical'],'transport':d.get('transport','unknown'),'best':best,'endpoints':d.get('endpoints',[]),'recommendation':d.get('recommendation',''),'restart_count':c['restart_count'],'networks':c['networks'],'ports':c['ports'],'compose':c['compose']})
    netlist=[]
    for nr in jl(['docker','network','ls','--format','{{json .}}']):
        ni=j(['docker','network','inspect',nr.get('Name','')],[]); members=[]
        if ni:
            for v in (ni[0].get('Containers') or {}).values(): members.append({'name':v.get('Name',''),'ipv4':v.get('IPv4Address','')})
        netlist.append({'name':nr.get('Name',''),'driver':nr.get('Driver',''),'scope':nr.get('Scope',''),'containers':sorted(members,key=lambda x:x['name'])})
    findings=[]
    def add(sev,cat,name,msg,fix,verify,agent_safe=False): findings.append({'severity':sev,'category':cat,'name':name,'message':msg,'fix':fix,'verify':verify,'agent_safe':agent_safe})
    for c in cont:
        n=c['name']
        if c['state']=='restarting': add('Critical','runtime',n,f"Container restartet; RestartCount={c['restart_count']}",f"docker logs --tail=200 {n}\ncd {c['compose'].get('working_dir') or '<compose-dir>'} && docker compose up -d --force-recreate",f"docker ps -a --filter name={n}")
        elif c['state']=='exited' and not ('migration' in n or n.endswith('-init-1') or c['status_text'].startswith('Exited (0)')): add('Medium','runtime',n,'Container ist beendet',f'docker logs --tail=100 {n}\ndocker start {n}',f'docker ps -a --filter name={n}',True)
        if c['health']=='unhealthy': add('High','healthcheck',n,'Healthcheck unhealthy',f"docker inspect {n} --format '{{{{json .State.Health}}}}' | jq",f"docker inspect {n} --format '{{{{.State.Health.Status}}}}'")
        if c['restart_count'] and c['state']=='running' and int(c['restart_count'])>10: add('Medium','stability',n,f"Container läuft, hatte aber {c['restart_count']} Restarts.",f'docker logs --tail=200 {n}',f"watch -n5 'docker inspect {n} --format \"Restart={{{{.RestartCount}}}} Status={{{{.State.Status}}}}\"'")
    for s in services:
        if s['container'] and s['state']=='running' and not s['ok']: add('High' if s['critical']=='high' else 'Medium','endpoint',s['container'],f"{s['label']} hat keinen zuverlässigen Service-Endpoint. {s.get('recommendation','')}",f"docker logs --tail=200 {s['container']}\n# /health oder /docs Endpoint prüfen/ergänzen", "curl --noproxy '*' <endpoint>")
        if s['container'] and s.get('expected_network') and not s.get('in_expected_network'): add('Medium','networking',s['container'],f"Sollte im Netzwerk {s['expected_network']} sein.",f"cd {compose(s['container']).get('working_dir') or '<compose-dir>'}\n# docker-compose.yml networks ergänzen\ndocker compose up -d",f"docker inspect {s['container']} --format '{{{{json .NetworkSettings.Networks}}}}' | jq")
    for m in mcps:
        if m['state']=='running' and not m['ok']: add('Medium','mcp-endpoint',m['container'],f"MCP-Endpunkt nicht zuverlässig erkannt. {m.get('recommendation','')}",f"docker logs --tail=200 {m['container']}\n# /sse, /mcp, /message und Port-Mapping prüfen.","curl --noproxy '*' <mcp-endpoint>")
    if 'docker-stack-dashboard' in names: add('Medium','security','docker-stack-dashboard','Docker-Socket ist gemountet; sicherheitssensibel.','Nur lokal/Admin-Netz nutzen; vor Reverse Proxy Auth setzen.','docker inspect docker-stack-dashboard --format \'{{json .Mounts}}\' | jq')
    ai=next((n for n in netlist if n['name']==NETWORK),{'containers':[]})
    logs={f['name']:log_errors(f['name']) for f in findings[:20] if f['name'] in names}
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'host':{'hostname':hn,'docker_version':dv,'docker_context':ctx},'network':NETWORK,'mcp_network':MCP_NETWORK,'host_gateway':HOST_GATEWAY,'dashboard_container':dash_name(),'tester':pick(names),'summary':{'total':len(cont),'running':sum(1 for c in cont if c['state']=='running'),'restarting':sum(1 for c in cont if c['state']=='restarting'),'exited':sum(1 for c in cont if c['state']=='exited'),'unhealthy':sum(1 for c in cont if c['health']=='unhealthy'),'findings':len(findings),'critical':sum(1 for f in findings if f['severity']=='Critical'),'high':sum(1 for f in findings if f['severity']=='High'),'services_ok':sum(1 for s in services if s['ok']),'services_total':len([s for s in services if s['container']]),'mcps_ok':sum(1 for m in mcps if m['ok']),'mcps_total':len(mcps)},'containers':cont,'networks':netlist,'ai_stack_members':ai['containers'],'services':services,'mcps':mcps,'findings':findings,'error_logs':logs,'gpu':gpu()}

def component_payload(component,st):
    c=next((x for x in st['containers'] if x['name']==component),None)
    svc=next((s for s in st['services'] if s.get('container')==component or s.get('key')==component),None)
    mcp=next((m for m in st['mcps'] if m.get('container')==component),None)
    fs=[f for f in st['findings'] if f['name'] in [component,(svc or {}).get('label',''),(mcp or {}).get('label','')]]
    return {'component':component,'container':c,'service':svc,'mcp':mcp,'findings':fs,'logs':st['error_logs'].get(component,[])}

def make_prompt(kind,component=None):
    st=collect(); focus=PROMPTS.get(kind,PROMPTS['diagnose'])
    if component:
        payload=component_payload(component,st); scope=f'Component-specific task for `{component}`'
    else:
        payload={'summary':st['summary'],'services':st['services'],'mcps':st['mcps'],'findings':st['findings'],'containers':st['containers'],'networks':st['networks'],'gpu':st['gpu'],'error_logs':st['error_logs']}; scope='Full-stack task'
    data=json.dumps(payload,ensure_ascii=False,indent=2)
    return f'''You are a Senior DevOps Engineer, Docker Architect, Linux SRE, Networking Expert and Software Architect for a local AI/RAG/MCP Docker stack.

Scope: {scope}
Task focus: {focus}

Operational goals:
- Stop errors, restart loops, unhealthy states and problematic behavior.
- Identify the correct health/ready/docs/function endpoints for this component.
- If no suitable endpoint exists, propose the minimal code/compose change to add one.
- Keep UI/API Services and MCP servers conceptually separate.
- Preserve network segmentation: external APIs on ai-stack; MCP servers on mcp-network; internal DBs/queues only on private backend networks unless intentionally shared.
- MCP services should expose stable SSE or Streamable HTTP endpoints plus a simple health endpoint where possible.
- Interpret MCP 405/401/403/426 as reachable-but-method/auth/handshake issue, not necessarily down.
- Use --noproxy "*" in curl examples.
- Prefer minimal, safe, reversible changes.
- Do NOT implement SSH automation yet. You may prepare for future SSH repair agent by describing guardrails, permissions, dry-run and audit logging.

Produce:
1. Executive Summary
2. Root cause analysis
3. Exact fix commands
4. docker-compose.yml patch
5. Dockerfile/code patch if an endpoint must be added
6. .env changes
7. Network changes
8. Endpoint design and verification
9. Security implications
10. Rollback commands
11. Safe execution order
12. Future agent automation notes

STATE_JSON:
```json
{data}
```'''

@app.get('/')
def index(): return FileResponse('/app/static/index.html')
@app.get('/api/status')
def status(): return collect()
@app.get('/api/export')
def export(): return JSONResponse(collect())
@app.get('/api/prompts')
def prompts(): return PROMPTS
@app.get('/api/prompt',response_class=PlainTextResponse)
def prompt(kind:str=Query('diagnose'),component:Optional[str]=Query(None)): return make_prompt(kind,component)
@app.get('/api/discover/{container}')
def discover(container:str):
    names=[r.get('Names','') for r in rows() if r.get('Names')]
    return discover_mcp(container,names) if role(container)=='mcp' else discover_service(container,names)
