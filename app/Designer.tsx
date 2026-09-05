"use client";

import { useEffect, useRef, useState } from "react";
import {
  Circle,
  Group,
  Layer,
  Rect,
  Stage,
  Text,
  Transformer,
} from "react-konva";
import { newClientId } from "./ids";

export type DesignerElement = {
  id: string;
  type: string;
  text?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index?: number;
  locked?: boolean;
  opacity?: number;
  rotation?: number;
  style?: Record<string, string | number>;
  refresh?: {
    mode?: "hourly" | "interval" | "manual";
    interval_minutes?: number;
    intervalMinutes?: number;
  };
};
export type DesignerDocument = {
  schema: "signal.design/v1";
  canvas: { width: number; height: number; background?: string };
  elements: DesignerElement[];
};

const W = 1920;
const H = 1080;
const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

function makeElement(type: string, index: number): DesignerElement {
  const id = newClientId();
  const x = 180 + (index % 5) * 40;
  const y = 170 + (index % 4) * 35;
  const presets: Record<string, Partial<DesignerElement>> = {
    heading: {
      type: "text",
      text: "Heading",
      width: 1080,
      height: 120,
      style: { fontSize: 76, fill: "#ffffff", fontStyle: "bold" },
    },
    subheading: {
      type: "text",
      text: "Subheading",
      width: 960,
      height: 80,
      style: { fontSize: 44, fill: "#ffffff" },
    },
    body: {
      type: "text",
      text: "Add your message here",
      width: 960,
      height: 120,
      style: { fontSize: 30, fill: "#ffffff" },
    },
    shape: {
      type: "shape",
      text: "",
      width: 500,
      height: 260,
      style: { fill: "#245b88", cornerRadius: 18 },
    },
    circle: {
      type: "circle",
      text: "",
      width: 260,
      height: 260,
      style: { fill: "#2f9f86" },
    },
    image: {
      type: "image",
      text: "Drop an image here",
      width: 560,
      height: 380,
      style: { fill: "#dce7f1" },
    },
    video: {
      type: "video",
      text: "Video",
      width: 560,
      height: 320,
      style: { fill: "#1f2937" },
    },
    pdf: {
      type: "pdf",
      text: "PDF page",
      width: 500,
      height: 620,
      style: { fill: "#f6e6d2" },
    },
    clock: {
      type: "clock",
      text: "12:34 PM",
      width: 420,
      height: 90,
      style: { fontSize: 56, fill: "#ffffff" },
    },
    date: {
      type: "date",
      text: "Tuesday, August 25",
      width: 560,
      height: 72,
      style: { fontSize: 36, fill: "#ffffff" },
    },
    weather: {
      type: "weather",
      text: "☀ 72° · Sample weather",
      width: 540,
      height: 90,
      style: { fontSize: 38, fill: "#ffffff" },
    },
    website: {
      type: "website",
      text: "https://example.org",
      width: 640,
      height: 360,
      style: { fill: "#edf4fb" },
      refresh: { mode: "hourly" },
    },
    qr: {
      type: "qr",
      text: "QR",
      width: 260,
      height: 260,
      style: { fill: "#ffffff" },
    },
    ticker: {
      type: "ticker",
      text: "Important school announcement",
      width: 1400,
      height: 88,
      style: { fontSize: 38, fill: "#ffffff" },
    },
  };
  return {
    id,
    x,
    y,
    width: 300,
    height: 100,
    z_index: index + 1,
    opacity: 1,
    ...presets[type],
  } as DesignerElement;
}

export function SignalDesigner({
  document,
  onChange,
  onPickAsset,
  onUploadMedia,
  slideDuration = 10,
  onSlideDurationChange,
}: {
  document: DesignerDocument;
  onChange: (document: DesignerDocument) => void;
  onPickAsset?: (type: "image" | "video" | "pdf" | "website") => void;
  onUploadMedia?: () => void;
  slideDuration?: number;
  onSlideDurationChange?: (duration: number) => void;
}) {
  const [zoom, setZoom] = useState(0.42);
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<DesignerDocument[]>([]);
  const [future, setFuture] = useState<DesignerDocument[]>([]);
  const [showSafe, setShowSafe] = useState(true);
  const [panel, setPanel] = useState<"design" | "slide" | "arrange">("slide");
  const nodes = useRef<Record<string, any>>({});
  const transformer = useRef<any>(null);
  const clipboard = useRef<DesignerElement[]>([]);
  const selectedElements = document.elements.filter((element) =>
    selected.includes(element.id),
  );

  useEffect(() => {
    transformer.current?.nodes(
      selected
        .filter(
          (id) =>
            !document.elements.find((element) => element.id === id)?.locked,
        )
        .map((id) => nodes.current[id])
        .filter(Boolean),
    );
    transformer.current?.getLayer()?.batchDraw();
  }, [selected, document.elements]);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
        event.preventDefault();
        duplicate();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "c") {
        event.preventDefault();
        copy();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "v") {
        event.preventDefault();
        paste();
        return;
      }
      if (["Backspace", "Delete"].includes(event.key)) {
        event.preventDefault();
        remove();
        return;
      }
      const movement: Record<string, [number, number]> = {
        ArrowLeft: [-1, 0],
        ArrowRight: [1, 0],
        ArrowUp: [0, -1],
        ArrowDown: [0, 1],
      };
      if (movement[event.key]) {
        event.preventDefault();
        moveSelected(
          movement[event.key][0] * (event.shiftKey ? 10 : 1),
          movement[event.key][1] * (event.shiftKey ? 10 : 1),
        );
      }
      if (event.key === "Escape") {
        setSelected([]);
        setEditing(null);
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  });

  const commit = (next: DesignerDocument) => {
    setHistory((old) => [...old.slice(-49), document]);
    setFuture([]);
    onChange(next);
  };
  const update = (
    id: string,
    values: Partial<DesignerElement>,
    record = true,
  ) => {
    const next = {
      ...document,
      elements: document.elements.map((element) =>
        element.id === id ? { ...element, ...values } : element,
      ),
    };
    record ? commit(next) : onChange(next);
  };
  const undo = () => {
    const previous = history.at(-1);
    if (!previous) return;
    setHistory((old) => old.slice(0, -1));
    setFuture((old) => [document, ...old].slice(0, 50));
    onChange(previous);
  };
  const redo = () => {
    const following = future[0];
    if (!following) return;
    setFuture((old) => old.slice(1));
    setHistory((old) => [...old, document].slice(-50));
    onChange(following);
  };
  const add = (type: string) => {
    const next = {
      ...document,
      elements: [
        ...document.elements,
        makeElement(type, document.elements.length),
      ],
    };
    commit(next);
    setSelected([next.elements.at(-1)!.id]);
  };
  const remove = () => {
    const removable = selected.filter(
      (id) => !document.elements.find((element) => element.id === id)?.locked,
    );
    if (!removable.length) return;
    commit({
      ...document,
      elements: document.elements.filter(
        (element) => !removable.includes(element.id),
      ),
    });
    setSelected([]);
  };
  const duplicate = () => {
    const copies = selectedElements
      .filter((element) => !element.locked)
      .map((element) => ({
        ...element,
        id: newClientId(),
        x: clamp(element.x + 32, 0, W - element.width),
        y: clamp(element.y + 32, 0, H - element.height),
        z_index: document.elements.length + 1,
      }));
    if (!copies.length) return;
    commit({ ...document, elements: [...document.elements, ...copies] });
    setSelected(copies.map((copy) => copy.id));
  };
  const copy = () => {
    clipboard.current = selectedElements
      .filter((element) => !element.locked)
      .map((element) => ({ ...element, style: { ...element.style } }));
  };
  const paste = () => {
    const copies = clipboard.current.map((element, index) => ({
      ...element,
      id: newClientId(),
      x: clamp(element.x + 32, 0, W - element.width),
      y: clamp(element.y + 32, 0, H - element.height),
      z_index: document.elements.length + index + 1,
    }));
    if (!copies.length) return;
    commit({ ...document, elements: [...document.elements, ...copies] });
    setSelected(copies.map((copy) => copy.id));
  };
  const moveSelected = (dx: number, dy: number) => {
    if (!selected.length) return;
    commit({
      ...document,
      elements: document.elements.map((element) =>
        selected.includes(element.id) && !element.locked
          ? {
              ...element,
              x: clamp(element.x + dx, 0, W - element.width),
              y: clamp(element.y + dy, 0, H - element.height),
            }
          : element,
      ),
    });
  };
  const snap = (element: DesignerElement, x: number, y: number) => {
    const threshold = 16;
    const candidatesX = [0, W / 2 - element.width / 2, W - element.width];
    const candidatesY = [0, H / 2 - element.height / 2, H - element.height];
    for (const other of document.elements)
      if (other.id !== element.id) {
        candidatesX.push(
          other.x,
          other.x + other.width - element.width,
          other.x + other.width / 2 - element.width / 2,
        );
        candidatesY.push(
          other.y,
          other.y + other.height - element.height,
          other.y + other.height / 2 - element.height / 2,
        );
      }
    const snappedX = candidatesX.find(
      (value) => Math.abs(value - x) < threshold,
    );
    const snappedY = candidatesY.find(
      (value) => Math.abs(value - y) < threshold,
    );
    return {
      x: clamp(snappedX ?? x, 0, W - element.width),
      y: clamp(snappedY ?? y, 0, H - element.height),
    };
  };
  const layer = (direction: "front" | "back" | "forward" | "backward") => {
    if (selected.length !== 1) return;
    const id = selected[0];
    const items = [...document.elements];
    const index = items.findIndex((element) => element.id === id);
    if (index < 0) return;
    const destination =
      direction === "front"
        ? items.length - 1
        : direction === "back"
          ? 0
          : clamp(
              index + (direction === "forward" ? 1 : -1),
              0,
              items.length - 1,
            );
    const [item] = items.splice(index, 1);
    items.splice(destination, 0, item);
    commit({
      ...document,
      elements: items.map((element, position) => ({
        ...element,
        z_index: position + 1,
      })),
    });
  };
  const align = (
    kind: "left" | "center" | "right" | "top" | "middle" | "bottom",
  ) => {
    if (!selectedElements.length) return;
    const multiple = selectedElements.length > 1;
    const minX = Math.min(...selectedElements.map((element) => element.x));
    const maxX = Math.max(
      ...selectedElements.map((element) => element.x + element.width),
    );
    const minY = Math.min(...selectedElements.map((element) => element.y));
    const maxY = Math.max(
      ...selectedElements.map((element) => element.y + element.height),
    );
    const next = {
      ...document,
      elements: document.elements.map((element) => {
        if (!selected.includes(element.id) || element.locked) return element;
        if (kind === "left") return { ...element, x: multiple ? minX : 0 };
        if (kind === "right")
          return {
            ...element,
            x: multiple ? maxX - element.width : W - element.width,
          };
        if (kind === "center")
          return {
            ...element,
            x: multiple
              ? (minX + maxX - element.width) / 2
              : (W - element.width) / 2,
          };
        if (kind === "top") return { ...element, y: multiple ? minY : 0 };
        if (kind === "bottom")
          return {
            ...element,
            y: multiple ? maxY - element.height : H - element.height,
          };
        return {
          ...element,
          y: multiple
            ? (minY + maxY - element.height) / 2
            : (H - element.height) / 2,
        };
      }),
    };
    commit(next);
  };
  const distribute = (axis: "x" | "y") => {
    if (selectedElements.length < 3) return;
    const ordered = [...selectedElements].sort((a, b) =>
      axis === "x" ? a.x - b.x : a.y - b.y,
    );
    const first = axis === "x" ? ordered[0].x : ordered[0].y;
    const last =
      axis === "x"
        ? ordered.at(-1)!.x + ordered.at(-1)!.width
        : ordered.at(-1)!.y + ordered.at(-1)!.height;
    const occupied = ordered.reduce(
      (sum, element) => sum + (axis === "x" ? element.width : element.height),
      0,
    );
    const gap = (last - first - occupied) / (ordered.length - 1);
    let cursor = first;
    const positions = new Map<string, number>();
    for (const element of ordered) {
      positions.set(element.id, cursor);
      cursor += (axis === "x" ? element.width : element.height) + gap;
    }
    commit({
      ...document,
      elements: document.elements.map((element) =>
        positions.has(element.id) && !element.locked
          ? {
              ...element,
              [axis === "x" ? "x" : "y"]: positions.get(element.id)!,
            }
          : element,
      ),
    });
  };
  const render = (element: DesignerElement) => {
    const common: any = {
      ref: (node: any) => {
        nodes.current[element.id] = node;
      },
      key: element.id,
      id: element.id,
      x: element.x,
      y: element.y,
      width: element.width,
      height: element.height,
      rotation: element.rotation || 0,
      opacity: element.opacity ?? 1,
      draggable: !element.locked,
      onClick: (event: any) => {
        event.cancelBubble = true;
        setPanel("design");
        setSelected((current) =>
          event.evt.shiftKey
            ? current.includes(element.id)
              ? current.filter((id) => id !== element.id)
              : [...current, element.id]
            : [element.id],
        );
      },
      onDblClick: () => element.type === "text" && setEditing(element.id),
      onDragEnd: (event: any) => {
        if (element.locked) return;
        const position = snap(element, event.target.x(), event.target.y());
        update(element.id, position);
      },
      onTransformEnd: () => {
        if (element.locked) return;
        const node = nodes.current[element.id];
        update(element.id, {
          x: node.x(),
          y: node.y(),
          rotation: node.rotation(),
          width: Math.max(20, node.width() * node.scaleX()),
          height: Math.max(20, node.height() * node.scaleY()),
        });
        node.scaleX(1);
        node.scaleY(1);
      },
    };
    if (
      ["shape", "image", "video", "pdf", "website", "ticker"].includes(
        element.type,
      )
    )
      return (
        <Group {...common}>
          <Rect
            width={element.width}
            height={element.height}
            fill={String(
              element.style?.fill ||
                (element.type === "image" ? "#dbeafe" : "#334155"),
            )}
            cornerRadius={Number(element.style?.cornerRadius || 8)}
            stroke={selected.includes(element.id) ? "#65c6ad" : "#ffffff"}
            strokeWidth={element.type === "shape" ? 0 : 2}
          />
          <Text
            text={element.text || element.type}
            width={element.width}
            height={element.height}
            align="center"
            verticalAlign="middle"
            fill={element.type === "image" ? "#20405f" : "#ffffff"}
            fontSize={Number(element.style?.fontSize || 30)}
          />
        </Group>
      );
    if (element.type === "circle" || element.type === "qr")
      return (
        <Group {...common}>
          <Circle
            radius={Math.min(element.width, element.height) / 2}
            x={element.width / 2}
            y={element.height / 2}
            fill={String(element.style?.fill || "#ffffff")}
            stroke={selected.includes(element.id) ? "#65c6ad" : "#d6e1ea"}
            strokeWidth={3}
          />
          <Text
            text={element.text || ""}
            width={element.width}
            height={element.height}
            align="center"
            verticalAlign="middle"
            fill="#14283b"
            fontSize={28}
          />
        </Group>
      );
    return (
      <Text
        {...common}
        text={
          element.type === "clock"
            ? new Date().toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
              })
            : element.type === "date"
              ? new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })
              : element.text || element.type
        }
        fontSize={Number(element.style?.fontSize || 44)}
        fontFamily={String(element.style?.fontFamily || "Arial")}
        fontStyle={String(element.style?.fontStyle || "normal")}
        textDecoration={String(element.style?.textDecoration || "")}
        align={String(element.style?.textAlign || "left")}
        verticalAlign={String(element.style?.verticalAlign || "top")}
        lineHeight={Number(element.style?.lineHeight || 1.15)}
        letterSpacing={Number(element.style?.letterSpacing || 0)}
        fill={String(element.style?.fill || "#ffffff")}
      />
    );
  };
  const active = selectedElements[0];
  const supportsTextStyle =
    active &&
    ["text", "clock", "date", "weather", "ticker"].includes(active.type);
  const applyStyle = (values: Record<string, string | number>) =>
    active && update(active.id, { style: { ...active.style, ...values } });
  const selectLayer = (id: string) => {
    setSelected([id]);
    setPanel("design");
  };
  const changeCanvasBackground = (color: string) =>
    commit({ ...document, canvas: { ...document.canvas, background: color } });
  return (
    <div className="signal-designer designer-studio">
      <section className="designer-workspace">
        <div className="studio-toolbar">
          <div className="studio-toolset">
            <button onClick={() => add("body")} title="Insert text"><strong>T</strong><span>Text</span></button>
            <button onClick={() => onPickAsset ? onPickAsset("image") : add("image")} title="Add image from Library"><strong>▧</strong><span>Image</span></button>
            <button onClick={() => onPickAsset ? onPickAsset("video") : add("video")} title="Add video from Library"><strong>▷</strong><span>Video</span></button>
            <button onClick={() => onPickAsset ? onPickAsset("pdf") : add("pdf")} title="Add PDF from Library"><strong>▤</strong><span>PDF</span></button>
            <button onClick={() => add("shape")} title="Insert shape"><strong>◇</strong><span>Shape</span></button>
            <button onClick={() => onPickAsset ? onPickAsset("website") : add("website")} title="Insert web link"><strong>↗</strong><span>Web link</span></button>
            {onUploadMedia && <button onClick={onUploadMedia} title="Upload images, video, or PDFs"><strong>↑</strong><span>Upload</span></button>}
            <label className="studio-background" title="Canvas background"><i style={{ background: document.canvas.background || "#172d43" }} /><span>Background</span><input type="color" value={document.canvas.background || "#172d43"} onChange={(event) => changeCanvasBackground(event.target.value)} /></label>
          </div>
          <div className="studio-history">
            <button onClick={undo} disabled={!history.length} title="Undo" aria-label="Undo">↶</button>
            <button onClick={redo} disabled={!future.length} title="Redo" aria-label="Redo">↷</button>
          </div>
        </div>
        <div className="stage-scroll">
          <div className="studio-zoom" aria-label="Canvas zoom">
            <button onClick={() => setZoom((value) => clamp(value - 0.08, 0.2, 1))} aria-label="Zoom out">−</button>
            <output>{Math.round(zoom * 100)}%</output>
            <button onClick={() => setZoom((value) => clamp(value + 0.08, 0.2, 1))} aria-label="Zoom in">＋</button>
            <button onClick={() => setZoom(0.42)} aria-label="Fit canvas">⛶</button>
          </div>
          <div
            className="stage-frame"
            style={{ width: W * zoom, height: H * zoom }}
          >
            <Stage
              width={W * zoom}
              height={H * zoom}
              scaleX={zoom}
              scaleY={zoom}
              onMouseDown={(event: any) => {
                if (event.target === event.target.getStage()) setSelected([]);
              }}
            >
              <Layer>
                <Rect
                  width={W}
                  height={H}
                  fill={document.canvas.background || "#172d43"}
                />
                {showSafe && (
                  <Rect
                    x={96}
                    y={54}
                    width={1728}
                    height={972}
                    stroke="#f6b74d"
                    dash={[12, 12]}
                    strokeWidth={2}
                    listening={false}
                  />
                )}
                {[...document.elements]
                  .sort((a, b) => (a.z_index || 0) - (b.z_index || 0))
                  .map(render)}
                <Transformer
                  ref={transformer}
                  rotateEnabled
                  enabledAnchors={[
                    "top-left",
                    "top-center",
                    "top-right",
                    "middle-right",
                    "bottom-right",
                    "bottom-center",
                    "bottom-left",
                    "middle-left",
                  ]}
                  boundBoxFunc={(_oldBox: any, nextBox: any) =>
                    nextBox.width < 20 || nextBox.height < 20
                      ? _oldBox
                      : nextBox
                  }
                />
              </Layer>
            </Stage>
            {editing && active && (
              <textarea
                autoFocus
                className="designer-inline-editor"
                style={{
                  left: active.x * zoom,
                  top: active.y * zoom,
                  width: active.width * zoom,
                  height: active.height * zoom,
                  fontSize: Number(active.style?.fontSize || 44) * zoom,
                }}
                defaultValue={active.text}
                onBlur={(event) => {
                  update(active.id, { text: event.target.value });
                  setEditing(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") setEditing(null);
                }}
              />
            )}
          </div>
        </div>
      </section>
      <aside className="designer-properties studio-inspector">
        <div className="studio-tabs" role="tablist" aria-label="Designer controls">
          {(["design", "slide", "arrange"] as const).map((value) => <button key={value} className={panel === value ? "active" : ""} onClick={() => setPanel(value)} role="tab" aria-selected={panel === value}>{value[0].toUpperCase() + value.slice(1)}</button>)}
        </div>
        <div className="studio-panel">
          {panel === "design" && (active ? <>
            <p className="inspector-heading">{active.type === "text" ? "Text" : active.type[0].toUpperCase() + active.type.slice(1)}</p>
            <label>Text<textarea value={active.text || ""} onChange={(event) => update(active.id, { text: event.target.value })} /></label>
            {active.type === "website" && <div className="designer-control-group"><label>Automatic refresh<select value={active.refresh?.mode || "hourly"} onChange={(event) => update(active.id, { refresh: { ...active.refresh, mode: event.target.value as "hourly" | "interval" | "manual" } })}><option value="hourly">Top of every hour</option><option value="interval">Custom interval</option><option value="manual">Only when Force Sync is used</option></select></label>{(active.refresh?.mode || "hourly") === "interval" && <label>Refresh every <input type="number" min="5" max="1440" value={active.refresh?.interval_minutes || active.refresh?.intervalMinutes || 60} onChange={(event) => update(active.id, { refresh: { ...active.refresh, mode: "interval", interval_minutes: Math.min(1440, Math.max(5, Number(event.target.value) || 60)) } })} /> minutes</label>}<small>Web content reloads at the selected time. Force Sync reloads it immediately.</small></div>}
            <div className="studio-field-row"><label>Color<input type="color" value={String(active.style?.fill || "#ffffff")} onChange={(event) => update(active.id, { style: { ...active.style, fill: event.target.value } })} /></label><label>Rotation<input type="number" value={active.rotation || 0} onChange={(event) => update(active.id, { rotation: Number(event.target.value) })} /></label></div>
            {supportsTextStyle && <>
              <label>Font size<input type="number" value={Number(active.style?.fontSize || 44)} onChange={(event) => applyStyle({ fontSize: Number(event.target.value) })} /></label>
              <label>Font family<select value={String(active.style?.fontFamily || "Arial")} onChange={(event) => applyStyle({ fontFamily: event.target.value })}><option>Arial</option><option>Georgia</option><option>Trebuchet MS</option><option>Verdana</option><option>Impact</option></select></label>
              <div className="designer-control-group"><small>Text alignment</small><div className="button-row">{(["left", "center", "right"] as const).map((value) => <button key={value} className={active.style?.textAlign === value ? "active" : ""} onClick={() => applyStyle({ textAlign: value })}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div></div>
              <div className="button-row"><button className={active.style?.fontStyle === "bold" ? "active" : ""} onClick={() => applyStyle({ fontStyle: active.style?.fontStyle === "bold" ? "normal" : "bold" })}>Bold</button><button className={active.style?.fontStyle === "italic" ? "active" : ""} onClick={() => applyStyle({ fontStyle: active.style?.fontStyle === "italic" ? "normal" : "italic" })}>Italic</button><button className={active.style?.textDecoration === "underline" ? "active" : ""} onClick={() => applyStyle({ textDecoration: active.style?.textDecoration === "underline" ? "" : "underline" })}>Underline</button></div>
            </>}
          </> : <div className="studio-empty"><b>Select a layer</b><span>Click something on the canvas to edit its details.</span></div>)}
          {panel === "slide" && <>
            <p className="inspector-heading">Slide settings</p>
            <label>Duration<div className="duration-input"><span>◷</span><input type="number" min="1" max="3600" value={slideDuration} onChange={(event) => onSlideDurationChange?.(Number(event.target.value) || 10)} /><em>seconds</em></div></label>
            <label>Background<div className="background-input"><input type="color" value={document.canvas.background || "#172d43"} onChange={(event) => changeCanvasBackground(event.target.value)} /><span>{document.canvas.background || "#172d43"}</span></div></label>
            <button className="studio-safe-toggle" onClick={() => setShowSafe((value) => !value)}>{showSafe ? "Hide" : "Show"} safe area</button>
          </>}
          {panel === "arrange" && <>
            <p className="inspector-heading">{active ? "Position & size" : "Arrange layers"}</p>
            {active && <><div className="studio-field-row"><label>X<input type="number" value={Math.round(active.x)} onChange={(event) => update(active.id, { x: clamp(Number(event.target.value), 0, W - active.width) })} /></label><label>Y<input type="number" value={Math.round(active.y)} onChange={(event) => update(active.id, { y: clamp(Number(event.target.value), 0, H - active.height) })} /></label></div><div className="studio-field-row"><label>Width<input type="number" value={Math.round(active.width)} onChange={(event) => update(active.id, { width: Math.max(20, Number(event.target.value)) })} /></label><label>Height<input type="number" value={Math.round(active.height)} onChange={(event) => update(active.id, { height: Math.max(20, Number(event.target.value)) })} /></label></div><div className="button-row"><button onClick={() => align("left")}>Left</button><button onClick={() => align("center")}>Center</button><button onClick={() => align("right")}>Right</button></div><div className="button-row"><button onClick={() => layer("back")}>Back</button><button onClick={() => layer("backward")}>− Layer</button><button onClick={() => layer("forward")}>+ Layer</button><button onClick={() => layer("front")}>Front</button></div><div className="button-row"><button onClick={duplicate}>Duplicate</button><button onClick={() => update(active.id, { locked: !active.locked })}>{active.locked ? "Unlock" : "Lock"}</button><button className="danger" onClick={remove} disabled={active.locked}>Delete</button></div></>}
          </>}
          <div className="designer-layers"><b>Layers</b>{[...document.elements].sort((a, b) => (b.z_index || 0) - (a.z_index || 0)).map((element) => <button key={element.id} className={selected.includes(element.id) ? "active" : ""} onClick={() => selectLayer(element.id)}><span>{element.locked ? "🔒" : element.type === "text" ? "T" : element.type === "image" ? "▧" : "◇"}</span>{element.text || element.type}</button>)}{!document.elements.length && <small>No layers yet.</small>}</div>
          <div className="studio-add-layer"><button onClick={() => add("heading")}>＋ Add text</button><button onClick={() => onPickAsset ? onPickAsset("image") : add("image")}>＋ Add media</button></div>
        </div>
      </aside>
    </div>
  );
}
