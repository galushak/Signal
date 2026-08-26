from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .agent import PlayerAgent
from .version import PLAYER_VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("signal.player").info("Starting Signal Player %s", PLAYER_VERSION)
agent = PlayerAgent()


class ConnectInput(BaseModel):
    code: str = Field(min_length=4, max_length=32)


class ServerInput(BaseModel):
    server_url: str = Field(min_length=8, max_length=512)


async def background() -> None:
    last_state_sync = 0.0
    while True:
        now = asyncio.get_running_loop().time()
        # Keep ordinary desired-state polling inexpensive, while checking the
        # outbound command queue once a second so Force Sync is responsive.
        await asyncio.to_thread(agent.cycle, sync_state=now - last_state_sync >= 15)
        if now - last_state_sync >= 15:
            last_state_sync = now
        await asyncio.sleep(1)


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
    return {"ok": True, "version": PLAYER_VERSION, "enrolled": agent.enrolled, "renderer": renderer, "cache": agent.runtime.get("cache", "empty"), "server_url": agent.server_url}


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
*{box-sizing:border-box}html,body,#screen{margin:0;width:100%;height:100%;overflow:hidden;background:#10121b;color:#fff;font-family:Arial,sans-serif}.enroll{height:100%;display:grid;place-items:center;text-align:center;background:radial-gradient(circle at 50% 30%,#493385,#11121c 65%)}.enroll>div{width:min(440px,88vw)}.enroll h1{font-size:38px;margin:0 0 10px}.enroll h2{font-size:21px;margin:0 0 25px}.enroll p{color:#d9d2f4;line-height:1.45}.enroll label{display:block;text-align:left;font-size:13px;font-weight:bold;margin:18px 0 7px}.enroll input{width:100%;padding:14px;border-radius:8px;border:1px solid #d9d2f4;background:#fff;color:#23163e;font-size:21px;letter-spacing:4px;text-align:center;text-transform:uppercase}.enroll input.server{font-size:14px;letter-spacing:0;text-align:left;text-transform:none}.enroll button{width:100%;margin-top:16px;border:0;border-radius:8px;background:#fff;color:#34215f;padding:13px 15px;font-weight:bold;cursor:pointer}.enroll button.secondary{background:transparent;border:1px solid #e6dcff;color:#fff}.enroll details{text-align:left;margin-top:22px}.enroll summary{cursor:pointer;color:#d9d2f4}.message{min-height:22px;color:#ffd3d3;margin:14px 0 0}.layout{position:relative;width:100%;height:100%;background:#111;cursor:none}.zone,.full-display{position:absolute;overflow:hidden}.full-display{inset:0}.item{width:100%;height:100%;position:absolute;animation:fade .45s ease}.element{position:absolute;overflow:hidden}.element img,.element video,.element iframe,.full-display img,.full-display video,.full-display iframe{width:100%;height:100%;object-fit:contain;border:0}.ticker{white-space:nowrap;animation:ticker 14s linear infinite}.clock{font-variant-numeric:tabular-nums}@keyframes fade{from{opacity:0}to{opacity:1}}@keyframes ticker{from{transform:translateX(100%)}to{transform:translateX(-100%)}}</style></head><body><div id="screen"></div><script>
let state;const screen=document.querySelector('#screen');
function valid(a,now,tz){if(!a.enabled)return false;let d=new Date(now),start=a.startsAt&&new Date(a.startsAt),end=a.endsAt&&new Date(a.endsAt);if(start&&d<start||end&&d>=end)return false;let p=new Intl.DateTimeFormat('en-US',{timeZone:tz,weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),get=t=>p.find(x=>x.type===t)?.value;let day=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(get('weekday'));if(a.weekdays&&a.weekdays.length&&!a.weekdays.includes(day))return false;let clock=get('hour')+':'+get('minute');return !((a.dailyStart&&clock<a.dailyStart)||(a.dailyEnd&&clock>=a.dailyEnd))}
function style(e){let o=e.style||{},fill=o.fill||e.fill||e.color||'#fff';return `left:${e.x||0}px;top:${e.y||0}px;width:${e.width||300}px;height:${e.height||100}px;z-index:${e.z_index??e.zIndex??0};opacity:${e.opacity??1};transform:rotate(${e.rotation||0}deg);color:${fill};font-family:${o.fontFamily||'Arial'};font-size:${o.fontSize||e.fontSize||42}px;font-weight:${o.fontStyle==='bold'?'bold':'normal'};font-style:${o.fontStyle==='italic'?'italic':'normal'};text-align:${o.textAlign||'left'};line-height:${o.lineHeight||1.15};letter-spacing:${o.letterSpacing||0}px;padding:${o.padding||e.padding||0}px`}
function renderElement(e){let s=style(e),type=e.type||'text',text=e.text||e.value||'',o=e.style||{};if(type==='image'||type==='video'){let id=e.assetId||e.asset_id||e.mediaId||e.media_id;return `<div class="element" style="${s}">${type==='video'?`<video autoplay muted loop style="object-fit:${o.fit==='fill'?'cover':'contain'}" src="/media/${id}"></video>`:`<img style="object-fit:${o.fit==='fill'?'cover':'contain'}" src="/media/${id}" alt="">`}</div>`}if(type==='shape')return `<div class="element" style="${s};background:${o.fill||e.fill||'#0000'};border-radius:${o.cornerRadius||0}px"></div>`;if(type==='clock')return `<div class="element clock" style="${s}">${new Intl.DateTimeFormat([],e.format||{timeStyle:'medium',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='date')return `<div class="element" style="${s}">${new Intl.DateTimeFormat([],e.format||{dateStyle:'full',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='ticker')return `<div class="element ticker" style="${s}">${text}</div>`;return `<div class="element" style="${s}">${text}</div>`}
function choose(candidates,now){let active=candidates.filter(c=>valid(c.assignment,now,state.timezone));if(!active.length)return null;let seconds=(now/1000)%active.reduce((total,c)=>total+(c.assignment.durationSeconds||20),0);for(let item of active){seconds-=item.assignment.durationSeconds||20;if(seconds<0)return item}return active[0]}
function mediaFrame(type,id,displayMode){let fit=displayMode==='fill'?'cover':'contain',frame='position:absolute;inset:0;overflow:hidden;background:#000',media=`position:absolute;inset:0;display:block;width:100%;height:100%;min-width:0;min-height:0;object-fit:${fit};object-position:center center;border:0`;if(type==='video')return `<div style="${frame}"><video autoplay muted loop playsinline style="${media}" src="/media/${id}"></video></div>`;if(type==='pdf')return `<div style="${frame}"><iframe style="${media}" src="/media/${id}"></iframe></div>`;return `<div style="${frame}"><img style="${media}" src="/media/${id}" alt=""></div>`}
function playable(item){if(!item)return '';if(item.source&&item.source.type!=='design')return mediaFrame(item.source.type,item.source.assetId,item.assignment?.displayMode||'fit');let canvas=item.design?.canvas||{width:1920,height:1080},scale=Math.min(innerWidth/canvas.width,innerHeight/canvas.height),left=(innerWidth-canvas.width*scale)/2,top=(innerHeight-canvas.height*scale)/2,background=canvas.background||'#172d43';return `<div class="design-canvas" style="position:absolute;overflow:hidden;transform-origin:top left;width:${canvas.width}px;height:${canvas.height}px;left:${left}px;top:${top}px;background:${background};transform:scale(${scale})">${(item.design?.elements||[]).map(renderElement).join('')}</div>`}
let renderedKey='';function emptyState(){let key='empty';if(renderedKey===key)return;renderedKey=key;screen.innerHTML='<div class="enroll"><div><h1>Signal</h1><h2>Connected</h2><p>No content is currently scheduled.</p></div></div>'}function draw(){screen.dataset.setup='';if(!state||!state.layout){emptyState();return}let now=Date.now(),full=choose(state.content.filter(c=>c.assignment.destinationId===state.playerId),now),zones=state.layout.zones,zoneContent=zones.map(z=>({zone:z,item:choose(state.content.filter(c=>c.assignment.destinationId===z.id),now)})),key=[state.revision||'',full?.assignment.id||'',...zoneContent.map(entry=>entry.zone.id+':' +(entry.item?.assignment.id||''))].join('|');if(!full&&!zoneContent.some(entry=>entry.item)){emptyState();return}if(renderedKey===key)return;renderedKey=key;screen.innerHTML='<div class="layout">'+(full?`<div class="full-display item">${playable(full)}</div>`:'')+zoneContent.map(({zone:z,item:candidate})=>`<div class="zone" style="left:${z.x/19.2}%;top:${z.y/10.8}%;width:${z.width/19.2}%;height:${z.height/10.8}%;background:${z.background||'transparent'}">${candidate?`<div class="item">${playable(candidate)}</div>`:''}</div>`).join('')+'</div>'}
async function connect(){let input=document.querySelector('#code'),message=document.querySelector('#message'),button=document.querySelector('#connect');button.disabled=true;message.textContent='Connecting to Signal…';try{let r=await fetch('/enrollment/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:input.value})}),data=await r.json();message.textContent=data.status==='enrolled'?'Display connected. Loading signage…':(data.message||'Unable to connect this display right now.')}catch(_){message.textContent='Unable to reach Signal. Check the server address and network connection.'}button.disabled=false;load()}async function saveServer(){let value=document.querySelector('#server').value,message=document.querySelector('#message');try{let r=await fetch('/server',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url:value})}),data=await r.json();message.textContent=r.ok?'Server address saved.':(data.detail||'That server address is not valid.')}catch(_){message.textContent='Unable to save the server address.'}}function setup(data){let status=data.runtime?.enrollment_status||'',message=document.querySelector('#message');if(screen.dataset.setup==='true'){if(message&&document.activeElement?.id!=='code')message.textContent=status;return}screen.dataset.setup='true';screen.innerHTML=`<div class="enroll"><div><h1>Signal</h1><h2>Connect this display</h2><label for="code">Enrollment Code</label><input id="code" placeholder="7F4-K9P" maxlength="7" autocomplete="off"><button id="connect">Connect</button><p id="message" class="message">${status}</p><details><summary>Advanced · Change Server</summary><label for="server">Signal Server</label><input id="server" class="server" value="${data.server_url||''}"><button id="saveServer" class="secondary">Save Server</button></details></div></div>`;document.querySelector('#connect').onclick=connect;document.querySelector('#saveServer').onclick=saveServer}async function load(){try{let data=await fetch('/state').then(r=>r.json());if(!data.enrolled){setup(data);return}state=data.manifest;draw()}catch(_){screen.innerHTML='<div class="enroll"><div><h1>Signal</h1><p>Unable to load player status.</p></div></div>'}}load();setInterval(load,5000);setInterval(()=>state&&draw(),1000);</script></body></html>'''
