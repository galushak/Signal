from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .agent import PlayerAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
agent = PlayerAgent()


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
    return {"enrolled": agent.enrolled, "enrollment_code": None if agent.enrolled else agent.identity.get("enrollment_code"), "manifest": agent.active_manifest(), "runtime": agent.runtime}


@app.get("/media/{asset_id}")
def media(asset_id: str):
    # The id originates from a validated cached manifest; keep path handling fixed.
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
*{box-sizing:border-box}html,body,#screen{margin:0;width:100%;height:100%;overflow:hidden;background:#10121b;color:#fff;font-family:Arial,sans-serif}.enroll{height:100%;display:grid;place-items:center;text-align:center;background:radial-gradient(circle at 50% 30%,#493385,#11121c 65%)}.enroll h1{font-size:38px;margin:0 0 20px}.enroll p{color:#d9d2f4}.code{font-size:46px;letter-spacing:8px;font-weight:bold;background:#fff;color:#34215f;border-radius:14px;padding:20px 28px;margin-top:24px}.layout{position:relative;width:100%;height:100%;background:#111}.zone{position:absolute;overflow:hidden}.item{width:100%;height:100%;position:absolute;animation:fade .45s ease}.element{position:absolute;overflow:hidden}.element img,.element video,.element iframe{width:100%;height:100%;object-fit:contain;border:0}.ticker{white-space:nowrap;animation:ticker 14s linear infinite}.clock{font-variant-numeric:tabular-nums}@keyframes fade{from{opacity:0}to{opacity:1}}@keyframes ticker{from{transform:translateX(100%)}to{transform:translateX(-100%)}}</style></head><body><div id="screen"></div><script>
let state, rotations={}; const screen=document.querySelector('#screen');
function valid(a,now,tz){if(!a.enabled)return false;let d=new Date(now),start=a.startsAt&&new Date(a.startsAt),end=a.endsAt&&new Date(a.endsAt);if(start&&d<start||end&&d>=end)return false;let p=new Intl.DateTimeFormat('en-US',{timeZone:tz,weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(d),get=t=>p.find(x=>x.type===t)?.value;let day=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(get('weekday'));if(a.weekdays&&a.weekdays.length&&!a.weekdays.includes(day))return false;let clock=get('hour')+':'+get('minute');return !((a.dailyStart&&clock<a.dailyStart)||(a.dailyEnd&&clock>=a.dailyEnd))}
function style(e){return `left:${e.x||0}px;top:${e.y||0}px;width:${e.width||300}px;height:${e.height||100}px;z-index:${e.zIndex||0};${e.style||''}`}
function renderElement(e){let s=style(e), type=e.type||'text', text=e.text||e.value||'';if(type==='image'||type==='video'){let id=e.assetId||e.asset_id||e.mediaId||e.media_id;return `<div class="element" style="${s}">${type==='video'?`<video autoplay muted loop src="/media/${id}"></video>`:`<img src="/media/${id}" alt="">`}</div>`}if(type==='clock')return `<div class="element clock" style="${s};font-size:${e.fontSize||42}px">${new Intl.DateTimeFormat([],e.format||{timeStyle:'medium',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='date')return `<div class="element" style="${s};font-size:${e.fontSize||34}px">${new Intl.DateTimeFormat([],e.format||{dateStyle:'full',timeZone:state.timezone}).format(new Date())}</div>`;if(type==='ticker')return `<div class="element ticker" style="${s};font-size:${e.fontSize||34}px">${text}</div>`;if(type==='website')return `<div class="element" style="${s};background:#222;padding:16px">Live website unavailable offline</div>`;if(type==='qr'||type==='qrcode')return `<div class="element" style="${s};background:#fff;color:#111;padding:12px">QR: ${text||e.url||''}</div>`;return `<div class="element" style="${s};color:${e.fill||e.color||'#fff'};font-size:${e.fontSize||42}px;background:${type==='shape'?(e.fill||'#0000'):''};padding:${e.padding||0}px">${text}</div>`}
function draw(){if(!state||!state.layout){screen.innerHTML='<div class="enroll"><div><h1>Signal</h1><p>Enrolled — waiting for a Layout assignment.</p></div></div>';return}let now=Date.now(), zones=state.layout.zones;screen.innerHTML='<div class="layout">'+zones.map(z=>{let candidates=state.content.filter(c=>c.assignment.destinationId===z.id&&valid(c.assignment,now,state.timezone));if(!candidates.length)return `<div class="zone" style="left:${z.x/19.2}%;top:${z.y/10.8}%;width:${z.width/19.2}%;height:${z.height/10.8}%;background:${z.background||'transparent'}"></div>`;let weighted=candidates.flatMap(c=>Array(c.assignment.priority||1).fill(c)), duration=Math.max(...weighted.map(c=>c.assignment.durationSeconds||20)), ix=Math.floor(now/(duration*1000))%weighted.length,c=weighted[ix];return `<div class="zone" style="left:${z.x/19.2}%;top:${z.y/10.8}%;width:${z.width/19.2}%;height:${z.height/10.8}%;background:${z.background||'transparent'}"><div class="item">${(c.design.elements||[]).map(renderElement).join('')}</div></div>`}).join('')+'</div>'}
async function load(){let data=await fetch('/state').then(r=>r.json());if(!data.enrolled){screen.innerHTML=`<div class="enroll"><div><h1>Signal</h1><p>Ready to Enroll</p><div class="code">${data.enrollment_code||'...'}</div><p>Enter this code in Signal → Displays → Enroll Display.</p></div></div>`;return}state=data.manifest;draw()}load();setInterval(load,5000);setInterval(()=>state&&draw(),1000);</script></body></html>'''
