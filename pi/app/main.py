from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .agent import PlayerAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
agent = PlayerAgent()


class ConnectInput(BaseModel):
    code: str = Field(min_length=4, max_length=32)


class ServerInput(BaseModel):
    server_url: str = Field(min_length=8, max_length=512)


async def background() -> None:
    while True:
        await asyncio.to_thread(agent.cycle)
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background())
    await asyncio.sleep(0.2)
    if hasattr(agent.platform, "start_renderer"):
        agent.platform.start_renderer("http://127.0.0.1:8090/player")
    yield
    task.cancel()


app = FastAPI(title="Signal Player", lifespan=lifespan)


@app.get("/healthz")
def health():
    renderer = getattr(agent.platform, "renderer_status", lambda: agent.runtime.get("renderer", "local_web_only"))()
    return {"ok": True, "enrolled": agent.enrolled, "renderer": renderer}


@app.get("/state")
def state():
    return {"enrolled": agent.enrolled, "server_url": agent.server_url, "manifest": agent.active_manifest(), "runtime": agent.runtime}


@app.post("/enrollment/connect")
def connect_enrollment(payload: ConnectInput):
    return agent.enroll(payload.code)


@app.post("/server")
def change_server(payload: ServerInput):
    try:
        agent.set_server_url(payload.server_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"server_url": agent.server_url}


@app.post("/enrollment/reset")
def reset_enrollment():
    agent.reset_enrollment()
    return {"status": "ready"}


@app.get("/media/{asset_id}")
def media(asset_id: str):
    if not asset_id.replace("-", "").isalnum():
        raise HTTPException(status_code=404)
    target = agent.media_dir / asset_id
    if not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(target)


@app.get("/", response_class=HTMLResponse)
@app.get("/player", response_class=HTMLResponse)
def player():
    return HTMLResponse(PLAYER_HTML)


PLAYER_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Signal Player</title><style>
*{box-sizing:border-box}html,body,#screen{margin:0;width:100%;height:100%;overflow:hidden;background:#10121b;color:#fff;font-family:Arial,sans-serif}.enroll{height:100%;display:grid;place-items:center;text-align:center;background:radial-gradient(circle at 50% 30%,#493385,#11121c 65%)}.enroll>div{width:min(440px,88vw)}.enroll h1{font-size:38px;margin:0 0 10px}.enroll h2{font-size:21px;margin:0 0 25px}.enroll p{color:#d9d2f4;line-height:1.45}.enroll label{display:block;text-align:left;font-size:13px;font-weight:bold;margin:18px 0 7px}.enroll input{width:100%;padding:14px;border-radius:8px;border:1px solid #d9d2f4;background:#fff;color:#23163e;font-size:21px;letter-spacing:4px;text-align:center;text-transform:uppercase}.enroll input.server{font-size:14px;letter-spacing:0;text-align:left;text-transform:none}.enroll button{width:100%;margin-top:16px;border:0;border-radius:8px;background:#fff;color:#34215f;padding:13px 15px;font-weight:bold;cursor:pointer}.enroll button.secondary{background:transparent;border:1px solid #e6dcff;color:#fff}.enroll details{text-align:left;margin-top:22px}.enroll summary{cursor:pointer;color:#d9d2f4}.message{min-height:22px;color:#ffd3d3;margin:14px 0 0}.layout{position:relative;width:100%;height:100%;background:#111}.zone,.full-display{position:absolute;overflow:hidden}.full-display{inset:0}.item{width:100%;height:100%;position:absolute;animation:fade .45s ease}.element{position:absolute;overflow:hidden}.element img,.element video,.element iframe,.full-display img,.full-display video,.full-display iframe{width:100%;height:100%;object-fit:contain;border:0}.ticker{white-space:nowrap;animation:ticker 14s linear infinite}.clock{font-variant-numeric:tabular-nums}@keyframes fade{from{opacity:0}to{opacity:1}}@keyframes ticker{from{transform:translateX(100%)}to{transform:translateX(-100%)}}</style></head><body><div id="screen"></div><script>
let state;const screen=document.querySelector('#screen');
function valid(a,now,tz){if(!a.enabled)return false;let d=new Date(now),start=a.startsAt&&new Date(a.startsAt),end=a.endsAt&&new Date(a.endsAt);if(start&&d<start||end&&d>=end)return false;let p=new Intl.DateTimeFormat('en-US',{timeZone:tz,weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),get=t=>p.find(x=>x.type===t)?.value;let day=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(get('weekday'));if(a.weekdays&&a.weekdays.length&&!a.weekdays.includes(day))return false;let clock=get('hour')+':'+get('minute');return !((a.dailyStart&&clock<a.dailyStart)||(a.dailyEnd&&clock>=a.dailyEnd))}
function style(e){return `left:${e.x||0}px;top:${e.y||0}px;width:${e.width||300}px;height:${e.height||100}px;z-index:${e.zIndex||0};${e.style||''}`}
function renderElement(e){let s=style(e),type=e.type||'text',text=e.text||e.value||'';if(type==='image'||type==='video'){let id=e.assetId||e.asset_id||e.mediaId||e.media_id;return `<div class="element" style="${s}">${type==='video'?`<video autoplay muted loop src="/media/${id}"></video>`:`<img src="/media/${id}" alt="">`}</div>`}if(type==='clock')return `<div class="element clock" style="${s};font-size:${e.fontSize||42}px">${new Intl.DateTimeFormat([],e.format||{timeStyle:'medium',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='date')return `<div class="element" style="${s};font-size:${e.fontSize||34}px">${new Intl.DateTimeFormat([],e.format||{dateStyle:'full',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='ticker')return `<div class="element ticker" style="${s};font-size:${e.fontSize||34}px">${text}</div>`;return `<div class="element" style="${s};color:${e.fill||e.color||'#fff'};font-size:${e.fontSize||42}px;background:${type==='shape'?(e.fill||'#0000'):''};padding:${e.padding||0}px">${text}</div>`}
function choose(candidates,now){let active=candidates.filter(c=>valid(c.assignment,now,state.timezone));if(!active.length)return null;let seconds=(now/1000)%active.reduce((total,c)=>total+(c.assignment.durationSeconds||20),0);for(let item of active){seconds-=item.assignment.durationSeconds||20;if(seconds<0)return item}return active[0]}
function playable(item){if(!item)return '';if(item.source&&item.source.type!=='design'){let id=item.source.assetId,type=item.source.type;if(type==='video')return `<video autoplay muted loop src="/media/${id}"></video>`;if(type==='pdf')return `<iframe src="/media/${id}"></iframe>`;return `<img src="/media/${id}" alt="">`}return (item.design?.elements||[]).map(renderElement).join('')}
function emptyState(){screen.innerHTML='<div class="enroll"><div><h1>Signal</h1><h2>Connected</h2><p>No content is currently scheduled.</p></div></div>'}function draw(){screen.dataset.setup='';if(!state||!state.layout){emptyState();return}let now=Date.now(),full=choose(state.content.filter(c=>c.assignment.destinationId===state.playerId),now),zones=state.layout.zones,zoneContent=zones.map(z=>({zone:z,item:choose(state.content.filter(c=>c.assignment.destinationId===z.id),now)}));if(!full&&!zoneContent.some(entry=>entry.item)){emptyState();return}screen.innerHTML='<div class="layout">'+(full?`<div class="full-display item">${playable(full)}</div>`:'')+zoneContent.map(({zone:z,item:candidate})=>`<div class="zone" style="left:${z.x/19.2}%;top:${z.y/10.8}%;width:${z.width/19.2}%;height:${z.height/10.8}%;background:${z.background||'transparent'}">${candidate?`<div class="item">${playable(candidate)}</div>`:''}</div>`).join('')+'</div>'}
async function connect(){let input=document.querySelector('#code'),message=document.querySelector('#message'),button=document.querySelector('#connect');button.disabled=true;message.textContent='Connecting to Signal…';try{let r=await fetch('/enrollment/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:input.value})}),data=await r.json();message.textContent=data.status==='enrolled'?'Display connected. Loading signage…':(data.message||'Unable to connect this display right now.')}catch(_){message.textContent='Unable to reach Signal. Check the server address and network connection.'}button.disabled=false;load()}async function saveServer(){let value=document.querySelector('#server').value,message=document.querySelector('#message');try{let r=await fetch('/server',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url:value})}),data=await r.json();message.textContent=r.ok?'Server address saved.':(data.detail||'That server address is not valid.')}catch(_){message.textContent='Unable to save the server address.'}}function setup(data){let status=data.runtime?.enrollment_status||'',message=document.querySelector('#message');if(screen.dataset.setup==='true'){if(message&&document.activeElement?.id!=='code')message.textContent=status;return}screen.dataset.setup='true';screen.innerHTML=`<div class="enroll"><div><h1>Signal</h1><h2>Connect this display</h2><label for="code">Enrollment Code</label><input id="code" placeholder="7F4-K9P" maxlength="7" autocomplete="off"><button id="connect">Connect</button><p id="message" class="message">${status}</p><details><summary>Advanced · Change Server</summary><label for="server">Signal Server</label><input id="server" class="server" value="${data.server_url||''}"><button id="saveServer" class="secondary">Save Server</button></details></div></div>`;document.querySelector('#connect').onclick=connect;document.querySelector('#saveServer').onclick=saveServer}async function load(){try{let data=await fetch('/state').then(r=>r.json());if(!data.enrolled){setup(data);return}state=data.manifest;draw()}catch(_){screen.innerHTML='<div class="enroll"><div><h1>Signal</h1><p>Unable to load player status.</p></div></div>'}}load();setInterval(load,5000);setInterval(()=>state&&draw(),1000);</script></body></html>'''
