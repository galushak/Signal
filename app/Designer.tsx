"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, Group, Layer, Line, Rect, Stage, Text, Transformer } from "react-konva";

export type DesignerElement = { id: string; type: string; text?: string; x: number; y: number; width: number; height: number; z_index?: number; locked?: boolean; opacity?: number; rotation?: number; style?: Record<string, string | number> };
export type DesignerDocument = { schema: "signal.design/v1"; canvas: { width: number; height: number; background?: string }; elements: DesignerElement[] };

const W = 1920;
const H = 1080;
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

function makeElement(type: string, index: number): DesignerElement {
  const id = crypto.randomUUID();
  const x = 180 + (index % 5) * 40;
  const y = 170 + (index % 4) * 35;
  const presets: Record<string, Partial<DesignerElement>> = {
    heading: { type: "text", text: "Heading", width: 1080, height: 120, style: { fontSize: 76, fill: "#ffffff", fontStyle: "bold" } },
    subheading: { type: "text", text: "Subheading", width: 960, height: 80, style: { fontSize: 44, fill: "#ffffff" } },
    body: { type: "text", text: "Add your message here", width: 960, height: 120, style: { fontSize: 30, fill: "#ffffff" } },
    shape: { type: "shape", text: "", width: 500, height: 260, style: { fill: "#245b88", cornerRadius: 18 } },
    circle: { type: "circle", text: "", width: 260, height: 260, style: { fill: "#2f9f86" } },
    image: { type: "image", text: "Drop an image here", width: 560, height: 380, style: { fill: "#dce7f1" } },
    video: { type: "video", text: "Video", width: 560, height: 320, style: { fill: "#1f2937" } },
    pdf: { type: "pdf", text: "PDF page", width: 500, height: 620, style: { fill: "#f6e6d2" } },
    clock: { type: "clock", text: "12:34 PM", width: 420, height: 90, style: { fontSize: 56, fill: "#ffffff" } },
    date: { type: "date", text: "Tuesday, August 25", width: 560, height: 72, style: { fontSize: 36, fill: "#ffffff" } },
    weather: { type: "weather", text: "☀ 72° · Sample weather", width: 540, height: 90, style: { fontSize: 38, fill: "#ffffff" } },
    website: { type: "website", text: "https://example.org", width: 640, height: 360, style: { fill: "#edf4fb" } },
    qr: { type: "qr", text: "QR", width: 260, height: 260, style: { fill: "#ffffff" } },
    ticker: { type: "ticker", text: "Important school announcement", width: 1400, height: 88, style: { fontSize: 38, fill: "#ffffff" } },
  };
  return { id, x, y, width: 300, height: 100, z_index: index + 1, opacity: 1, ...presets[type] } as DesignerElement;
}

export function SignalDesigner({ document, onChange, onPreview, onPublish }: { document: DesignerDocument; onChange: (document: DesignerDocument) => void; onPreview: () => void; onPublish: () => void }) {
  const [zoom, setZoom] = useState(0.42);
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<DesignerDocument[]>([]);
  const [future, setFuture] = useState<DesignerDocument[]>([]);
  const [showSafe, setShowSafe] = useState(true);
  const nodes = useRef<Record<string, any>>({});
  const transformer = useRef<any>(null);
  const selectedElements = document.elements.filter(element => selected.includes(element.id));

  useEffect(() => { transformer.current?.nodes(selected.map(id => nodes.current[id]).filter(Boolean)); transformer.current?.getLayer()?.batchDraw(); }, [selected, document.elements]);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") { event.preventDefault(); duplicate(); return; }
      if (["Backspace", "Delete"].includes(event.key)) { event.preventDefault(); remove(); return; }
      const movement: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (movement[event.key]) { event.preventDefault(); moveSelected(movement[event.key][0] * (event.shiftKey ? 10 : 1), movement[event.key][1] * (event.shiftKey ? 10 : 1)); }
      if (event.key === "Escape") { setSelected([]); setEditing(null); }
    };
    window.addEventListener("keydown", keydown); return () => window.removeEventListener("keydown", keydown);
  });

  const commit = (next: DesignerDocument) => { setHistory(old => [...old.slice(-49), document]); setFuture([]); onChange(next); };
  const update = (id: string, values: Partial<DesignerElement>, record = true) => { const next = { ...document, elements: document.elements.map(element => element.id === id ? { ...element, ...values } : element) }; record ? commit(next) : onChange(next); };
  const undo = () => { const previous = history.at(-1); if (!previous) return; setHistory(old => old.slice(0, -1)); setFuture(old => [document, ...old].slice(0, 50)); onChange(previous); };
  const redo = () => { const following = future[0]; if (!following) return; setFuture(old => old.slice(1)); setHistory(old => [...old, document].slice(-50)); onChange(following); };
  const add = (type: string) => { const next = { ...document, elements: [...document.elements, makeElement(type, document.elements.length)] }; commit(next); setSelected([next.elements.at(-1)!.id]); };
  const remove = () => { const removable = selected.filter(id => !document.elements.find(element => element.id === id)?.locked); if (!removable.length) return; commit({ ...document, elements: document.elements.filter(element => !removable.includes(element.id)) }); setSelected([]); };
  const duplicate = () => { const copies = selectedElements.filter(element => !element.locked).map(element => ({ ...element, id: crypto.randomUUID(), x: clamp(element.x + 32, 0, W - element.width), y: clamp(element.y + 32, 0, H - element.height), z_index: document.elements.length + 1 })); if (!copies.length) return; commit({ ...document, elements: [...document.elements, ...copies] }); setSelected(copies.map(copy => copy.id)); };
  const moveSelected = (dx: number, dy: number) => { if (!selected.length) return; commit({ ...document, elements: document.elements.map(element => selected.includes(element.id) && !element.locked ? { ...element, x: clamp(element.x + dx, 0, W - element.width), y: clamp(element.y + dy, 0, H - element.height) } : element) }); };
  const snap = (element: DesignerElement, x: number, y: number) => { const threshold = 16; const candidatesX = [0, W / 2 - element.width / 2, W - element.width]; const candidatesY = [0, H / 2 - element.height / 2, H - element.height]; for (const other of document.elements) if (other.id !== element.id) { candidatesX.push(other.x, other.x + other.width - element.width, other.x + other.width / 2 - element.width / 2); candidatesY.push(other.y, other.y + other.height - element.height, other.y + other.height / 2 - element.height / 2); } const snappedX = candidatesX.find(value => Math.abs(value - x) < threshold); const snappedY = candidatesY.find(value => Math.abs(value - y) < threshold); return { x: clamp(snappedX ?? x, 0, W - element.width), y: clamp(snappedY ?? y, 0, H - element.height) }; };
  const layer = (direction: "front" | "back" | "forward" | "backward") => { if (selected.length !== 1) return; const id = selected[0]; const items = [...document.elements]; const index = items.findIndex(element => element.id === id); if (index < 0) return; const destination = direction === "front" ? items.length - 1 : direction === "back" ? 0 : clamp(index + (direction === "forward" ? 1 : -1), 0, items.length - 1); const [item] = items.splice(index, 1); items.splice(destination, 0, item); commit({ ...document, elements: items.map((element, position) => ({ ...element, z_index: position + 1 })) }); };
  const render = (element: DesignerElement) => {
    const common: any = { ref: (node: any) => { nodes.current[element.id] = node; }, key: element.id, id: element.id, x: element.x, y: element.y, width: element.width, height: element.height, rotation: element.rotation || 0, opacity: element.opacity ?? 1, draggable: !element.locked, onClick: (event: any) => { event.cancelBubble = true; setSelected(current => event.evt.shiftKey ? current.includes(element.id) ? current.filter(id => id !== element.id) : [...current, element.id] : [element.id]); }, onDblClick: () => element.type === "text" && setEditing(element.id), onDragEnd: (event: any) => { const position = snap(element, event.target.x(), event.target.y()); update(element.id, position); }, onTransformEnd: () => { const node = nodes.current[element.id]; update(element.id, { x: node.x(), y: node.y(), rotation: node.rotation(), width: Math.max(20, node.width() * node.scaleX()), height: Math.max(20, node.height() * node.scaleY()) }); node.scaleX(1); node.scaleY(1); } };
    if (["shape", "image", "video", "pdf", "website", "ticker"].includes(element.type)) return <Group {...common}><Rect width={element.width} height={element.height} fill={String(element.style?.fill || (element.type === "image" ? "#dbeafe" : "#334155"))} cornerRadius={Number(element.style?.cornerRadius || 8)} stroke={selected.includes(element.id) ? "#65c6ad" : "#ffffff"} strokeWidth={element.type === "shape" ? 0 : 2} /><Text text={element.text || element.type} width={element.width} height={element.height} align="center" verticalAlign="middle" fill={element.type === "image" ? "#20405f" : "#ffffff"} fontSize={Number(element.style?.fontSize || 30)} /></Group>;
    if (element.type === "circle" || element.type === "qr") return <Group {...common}><Circle radius={Math.min(element.width, element.height) / 2} x={element.width / 2} y={element.height / 2} fill={String(element.style?.fill || "#ffffff")} stroke={selected.includes(element.id) ? "#65c6ad" : "#d6e1ea"} strokeWidth={3} /><Text text={element.text || ""} width={element.width} height={element.height} align="center" verticalAlign="middle" fill="#14283b" fontSize={28} /></Group>;
    return <Text {...common} text={element.type === "clock" ? new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : element.type === "date" ? new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }) : element.text || element.type} fontSize={Number(element.style?.fontSize || 44)} fontStyle={String(element.style?.fontStyle || "normal")} fill={String(element.style?.fill || "#ffffff")} />;
  };
  const active = selectedElements[0];
  return <div className="signal-designer"><aside className="designer-add"><b>Add to design</b><small>Templates</small><button onClick={() => add("heading")}>Heading</button><button onClick={() => add("subheading")}>Subheading</button><button onClick={() => add("body")}>Body text</button><small>Media</small><button onClick={() => add("image")}>Image</button><button onClick={() => add("video")}>Video</button><button onClick={() => add("pdf")}>PDF page</button><small>Elements & widgets</small><button onClick={() => add("shape")}>Rectangle</button><button onClick={() => add("circle")}>Circle</button><button onClick={() => add("clock")}>Clock</button><button onClick={() => add("date")}>Date</button><button onClick={() => add("weather")}>Weather</button><button onClick={() => add("website")}>Website</button><button onClick={() => add("qr")}>QR code</button><button onClick={() => add("ticker")}>Ticker</button></aside><section className="designer-workspace"><div className="designer-toolbar"><button onClick={() => setZoom(value => clamp(value - .08, .2, 1))}>−</button><b>{Math.round(zoom * 100)}%</b><button onClick={() => setZoom(value => clamp(value + .08, .2, 1))}>+</button><button onClick={() => setZoom(.42)}>Fit</button><button onClick={undo} disabled={!history.length}>Undo</button><button onClick={redo} disabled={!future.length}>Redo</button><button onClick={() => setShowSafe(value => !value)}>{showSafe ? "Hide" : "Show"} safe area</button><button className="secondary-button" onClick={onPreview}>Preview</button><button className="primary" onClick={onPublish}>Publish</button></div><div className="stage-scroll"><div className="stage-frame" style={{ width: W * zoom, height: H * zoom }}><Stage width={W * zoom} height={H * zoom} scaleX={zoom} scaleY={zoom} onMouseDown={(event: any) => { if (event.target === event.target.getStage()) setSelected([]); }}><Layer><Rect width={W} height={H} fill={document.canvas.background || "#172d43"} />{showSafe && <Rect x={96} y={54} width={1728} height={972} stroke="#f6b74d" dash={[12, 12]} strokeWidth={2} listening={false} />}{[...document.elements].sort((a, b) => (a.z_index || 0) - (b.z_index || 0)).map(render)}<Transformer ref={transformer} rotateEnabled enabledAnchors={["top-left", "top-center", "top-right", "middle-right", "bottom-right", "bottom-center", "bottom-left", "middle-left"]} boundBoxFunc={(_oldBox: any, nextBox: any) => nextBox.width < 20 || nextBox.height < 20 ? _oldBox : nextBox} /></Layer></Stage>{editing && active && <textarea autoFocus className="designer-inline-editor" style={{ left: active.x * zoom, top: active.y * zoom, width: active.width * zoom, height: active.height * zoom, fontSize: Number(active.style?.fontSize || 44) * zoom }} defaultValue={active.text} onBlur={event => { update(active.id, { text: event.target.value }); setEditing(null); }} onKeyDown={event => { if (event.key === "Escape") setEditing(null); }} />}</div></div></section><aside className="designer-properties"><b>{active ? active.type : "Canvas"}</b>{active ? <><label>Text<textarea value={active.text || ""} onChange={event => update(active.id, { text: event.target.value })} /></label><label>Color<input type="color" value={String(active.style?.fill || "#ffffff")} onChange={event => update(active.id, { style: { ...active.style, fill: event.target.value } })} /></label><label>Font size<input type="number" value={Number(active.style?.fontSize || 44)} onChange={event => update(active.id, { style: { ...active.style, fontSize: Number(event.target.value) } })} /></label><label>Rotation<input type="number" value={active.rotation || 0} onChange={event => update(active.id, { rotation: Number(event.target.value) })} /></label><div className="button-row"><button onClick={duplicate}>Duplicate</button><button onClick={remove} disabled={active.locked}>Delete</button><button onClick={() => update(active.id, { locked: !active.locked })}>{active.locked ? "Unlock" : "Lock"}</button></div><div className="button-row"><button onClick={() => layer("back")}>Back</button><button onClick={() => layer("backward")}>− Layer</button><button onClick={() => layer("forward")}>+ Layer</button><button onClick={() => layer("front")}>Front</button></div></> : <><label>Canvas background<input type="color" value={document.canvas.background || "#172d43"} onChange={event => commit({ ...document, canvas: { ...document.canvas, background: event.target.value } })} /></label><small>Click an object on the canvas to edit it. The dashed guide is not published.</small></>}<div className="designer-layers"><b>Layers</b>{[...document.elements].sort((a, b) => (b.z_index || 0) - (a.z_index || 0)).map(element => <button key={element.id} className={selected.includes(element.id) ? "active" : ""} onClick={() => setSelected([element.id])}>{element.locked ? "🔒 " : ""}{element.text || element.type}</button>)}</div></aside></div>;
}
