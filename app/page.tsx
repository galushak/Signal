"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { SignalDesigner, type DesignerDocument } from "./Designer";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
type User = {
  id: string;
  username: string;
  display_name: string;
  super_admin: boolean;
  grants: Grant[];
};
type Grant = {
  id: string;
  capability: string;
  scope_type: string;
  scope_id: string | null;
};
type Building = {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
};
type Player = {
  id: string;
  name: string;
  building_id: string;
  building_name: string;
  description?: string;
  enabled: boolean;
  health_state: string;
  last_seen_at?: string;
  cache_state: string;
};
type Layout = {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  locked: boolean;
  zones: Zone[];
};
type Zone = {
  id: string;
  layout_id: string;
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  background?: string;
  enabled: boolean;
  locked: boolean;
};
type ContentItem = {
  id: string;
  name: string;
  scope_type: string;
  scope_id?: string;
  published_version?: { revision: number; design_document: DesignDocument };
  draft_version?: { revision: number; design_document: DesignDocument };
};
type DesignDocument = {
  schema: "signal.design/v1";
  canvas: { width: number; height: number };
  elements: DesignElement[];
};
type DesignElement = { id: string; type: string; text?: string; x: number; y: number; width: number; height: number; z_index?: number; locked?: boolean; opacity?: number; url?: string; media_id?: string; style?: Record<string, string | number> };
type Media = {
  id: string;
  display_name: string;
  media_type: string;
  file_size: number;
  processing_state: string;
  processing_error?: string;
  created_at: string;
  tags: string[];
  thumbnail_url?: string;
};
type Dashboard = {
  players_total: number;
  players_online: number;
  players_never_connected: number;
  media_total: number;
  warnings: { player: Player }[];
};

function designFor(template: string): DesignDocument {
  const base = { schema: "signal.design/v1" as const, canvas: { width: 1920, height: 1080 } };
  const element = (type: string, text: string, x: number, y: number, width: number, height: number): DesignElement => ({ id: crypto.randomUUID(), type, text, x, y, width, height, z_index: 1 });
  if (template === "event") return { ...base, elements: [element("shape", "", 0, 0, 1920, 1080), element("text", "Event title", 140, 180, 1500, 170), element("text", "Date · Time · Location", 140, 410, 1200, 100)] };
  if (template === "menu") return { ...base, elements: [element("text", "Monday Lunch Menu", 130, 90, 1500, 140), element("text", "Entrée\nAlternative\nSides\nFruit\nNotes", 170, 310, 1400, 520)] };
  if (template === "announcement") return { ...base, elements: [element("text", "New announcement", 120, 120, 1500, 160), element("text", "Add the details your school community needs.", 120, 360, 1400, 140)] };
  return { ...base, elements: [element("text", "New content", 120, 120, 1200, 160)] };
}

async function request(
  path: string,
  token?: string,
  options: RequestInit = {},
) {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const body =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(body?.detail || "Something went wrong. Please try again.");
  return body;
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState("dashboard");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const saved = localStorage.getItem("signal_token");
    if (saved)
      request("/auth/me", saved)
        .then(setUser)
        .then(() => setToken(saved))
        .catch(() => localStorage.removeItem("signal_token"));
  }, []);
  const logout = async () => {
    if (token)
      await request("/auth/logout", token, { method: "POST" }).catch(
        () => undefined,
      );
    localStorage.removeItem("signal_token");
    setToken(null);
    setUser(null);
    setView("dashboard");
  };
  if (!token || !user)
    return (
      <Login
        onLogin={(nextToken, nextUser) => {
          localStorage.setItem("signal_token", nextToken);
          setToken(nextToken);
          setUser(nextUser);
        }}
      />
    );
  const show = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 4000);
  };
  const navigation = [
    ["dashboard", "▦", "Dashboard"],
    ["content", "✦", "Content"],
    ["media", "◫", "Media"],
    ["players", "▣", "Players"],
    ["buildings", "⌂", "Buildings"],
  ];
  if (user.super_admin)
    navigation.push(
      ["layouts", "▤", "Layouts"],
      ["users", "♙", "Users & access"],
      ["audit", "◷", "Audit log"],
    );
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">S</span>
          <span>Signal</span>
        </div>
        <div className="district">
          <span className="district-badge">WC</span>
          <div>
            <b>West Creek</b>
            <small>School District</small>
          </div>
        </div>
        <nav>
          {navigation.map(([id, icon, label]) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={view === id ? "nav-item active" : "nav-item"}
            >
              <span>{icon}</span>
              {label}
            </button>
          ))}
        </nav>
        <div className="nav-divider" />
        <nav className="secondary">
          <button className="nav-item">
            <span>◇</span>Help &amp; guides
          </button>
        </nav>
        <div className="profile">
          <div className="avatar">
            {user.display_name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <b>{user.display_name}</b>
            <small>{user.super_admin ? "Super Admin" : "Publisher"}</small>
          </div>
          <button onClick={logout} title="Sign out">
            ↪
          </button>
        </div>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            West Creek <span>/</span>{" "}
            {view === "users"
              ? "Users & access"
              : view[0].toUpperCase() + view.slice(1)}
          </div>
          <div className="top-actions">
            <span className="signed-in">Signed in as {user.username}</span>
            <button className="avatar small" onClick={logout}>
              ↪
            </button>
          </div>
        </header>
        <div className="page">
          {view === "dashboard" && <DashboardView token={token} />}
          {view === "content" && <ContentView token={token} notify={show} />}
          {view === "media" && <MediaView token={token} notify={show} />}
          {view === "players" && <PlayersView token={token} notify={show} />}
          {view === "buildings" && (
            <BuildingsView token={token} notify={show} />
          )}
          {view === "layouts" && <LayoutsView token={token} notify={show} />}
          {view === "users" && <UsersView token={token} notify={show} />}
          {view === "audit" && <AuditView token={token} />}
        </div>
      </section>
      {notice && (
        <div className="toast">
          <span>✓</span>
          {notice}
        </div>
      )}
    </main>
  );
}

function Login({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await request("/auth/login", undefined, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onLogin(result.access_token, result.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="login-screen">
      <section className="login-card">
        <div className="brand">
          <span className="brand-mark">S</span>
          <span>Signal</span>
        </div>
        <p className="eyebrow">DIGITAL SIGNAGE</p>
        <h1>Welcome back</h1>
        <p>Sign in to manage your assigned displays and media.</p>
        <form onSubmit={submit}>
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary login-button" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <small>Need an account? Ask your Signal administrator.</small>
      </section>
    </main>
  );
}

function DashboardView({ token }: { token: string }) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    request("/dashboard", token)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [token]);
  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">LIVE STATUS</p>
          <h1>Your displays</h1>
          <p>
            Real information from Signal. Devices that have not checked in are
            clearly marked.
          </p>
        </div>
      </div>
      <section className="status-strip">
        <div className="health-summary">
          <span
            className={
              data.players_never_connected ? "pulse warning-pulse" : "pulse"
            }
          />
          <div>
            <b>
              {data.players_total
                ? `${data.players_online} connected · ${data.players_never_connected} never connected`
                : "No players yet"}
            </b>
            <small>
              {data.players_total
                ? "Player status comes from actual device check-ins."
                : "Create your first player to begin."}
            </small>
          </div>
        </div>
      </section>
      <section className="stat-grid">
        <Stat
          label="Players"
          value={String(data.players_total)}
          detail="visible to you"
          accent="green"
        />
        <Stat
          label="Connected"
          value={String(data.players_online)}
          detail="reported by devices"
          accent="blue"
        />
        <Stat
          label="Never connected"
          value={String(data.players_never_connected)}
          detail="needs setup"
          accent="orange"
        />
        <Stat
          label="Media"
          value={String(data.media_total)}
          detail="available to you"
          accent="purple"
        />
      </section>
      <section className="panel functional-panel">
        <div className="panel-heading">
          <div>
            <h2>Needs attention</h2>
            <p>
              Signal does not invent player health. These players have never
              checked in.
            </p>
          </div>
        </div>
        {data.warnings.length ? (
          data.warnings.map((item) => (
            <div className="attention-item" key={item.player.id}>
              <span className="warning">!</span>
              <div>
                <b>{item.player.name}</b>
                <p>{item.player.building_name} · Never connected</p>
              </div>
            </div>
          ))
        ) : (
          <Empty text="Nothing needs attention right now." />
        )}
      </section>
    </>
  );
}
function Stat({
  label,
  value,
  detail,
  accent,
}: {
  label: string;
  value: string;
  detail: string;
  accent: string;
}) {
  return (
    <div className="stat">
      <span className={`stat-icon ${accent}`}>●</span>
      <div>
        <small>{label}</small>
        <b>
          {value} <em>{detail}</em>
        </b>
      </div>
    </div>
  );
}

function MediaView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [media, setMedia] = useState<Media[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      Promise.all([request("/media", token), request("/players", token)])
        .then(([assets, visiblePlayers]) => {
          setMedia(assets);
          setPlayers(visiblePlayers);
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const upload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    if (
      form
        .getAll("files")
        .filter((file) => file instanceof File && file.size > 0).length === 0
    ) {
      setError("Choose at least one file to upload.");
      return;
    }
    setBusy(true);
    try {
      await request("/media/upload", token, { method: "POST", body: form });
      notify("Media uploaded. Signal is preparing it in the background.");
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">MEDIA LIBRARY</p>
          <h1>Media</h1>
          <p>Only media within your access is shown here.</p>
        </div>
      </div>
      <section className="panel upload-panel">
        <h2>Upload media</h2>
        <p>
          Images, PDFs, and video are stored safely and prepared in the
          background.
        </p>
        <form onSubmit={upload} className="upload-form">
          <input
            name="files"
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,application/pdf,video/*"
            required
          />
          <select
            name="scope_type"
            defaultValue={players.length ? "player" : "district"}
          >
            <option value="district">District media</option>
            <option value="player">For a player</option>
          </select>
          <select name="scope_id" defaultValue={players[0]?.id}>
            <option value="">No player selected</option>
            {players.map((player) => (
              <option key={player.id} value={player.id}>
                {player.name}
              </option>
            ))}
          </select>
          <input name="tags" placeholder="tags, separated by commas" />
          <button className="primary" disabled={busy}>
            {busy ? "Uploading…" : "Upload media"}
          </button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="media-grid real-media">
          {media.length ? (
            media.map((asset) => (
              <article className="media-item" key={asset.id}>
                <div className="asset art-3">
                  <span>
                    {asset.media_type === "pdf"
                      ? "PDF"
                      : asset.media_type === "video"
                        ? "▶"
                        : "IMG"}
                  </span>
                </div>
                <b>{asset.display_name}</b>
                <small>
                  {asset.processing_state === "failed"
                    ? `Failed: ${asset.processing_error}`
                    : `${asset.media_type} · ${asset.processing_state}`}
                </small>
              </article>
            ))
          ) : (
            <Empty text="No media is available in your assigned areas yet." />
          )}
        </section>
      )}
    </>
  );
}

function PlayersView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [players, setPlayers] = useState<Player[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      Promise.all([request("/players", token), request("/buildings", token), request("/layouts", token)])
        .then(([p, b, l]) => {
          setPlayers(p);
          setBuildings(b);
          setLayouts(l);
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const add = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request("/players", token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          building_id: form.get("building_id"),
          description: form.get("description") || null,
          enabled: true,
        }),
      });
      notify(
        "Player created. It will show “Never connected” until a real device checks in.",
      );
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create player.");
    }
  };
  const enroll = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request("/players/enroll", token, { method: "POST", body: JSON.stringify({ code: String(form.get("code") || "").toUpperCase(), name: form.get("name"), building_id: form.get("building_id"), layout_id: form.get("layout_id") || null, description: form.get("description") || null }) });
      notify("Display enrolled. The player will retrieve its device credential automatically.");
      formElement.reset(); reload();
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to enroll display."); }
  };
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">YOUR DISPLAYS</p>
          <h1>Players</h1>
          <p>Player status is reported by real devices only.</p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Add a player</h2>
        <form onSubmit={add} className="inline-form">
          <input name="name" placeholder="e.g. HS Cafeteria" required />
          <select name="building_id" required defaultValue="">
            <option value="" disabled>
              Choose building
            </option>
            {buildings.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <input name="description" placeholder="Location (optional)" />
          <button className="secondary-button">Add player</button>
        </form>
      </section>
      <section className="panel create-panel">
        <h2>Enroll Display</h2>
        <form onSubmit={enroll} className="inline-form">
          <input name="code" placeholder="Code shown on player" required />
          <input name="name" placeholder="Display name" required />
          <select name="building_id" required defaultValue=""><option value="" disabled>Choose building</option>{buildings.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <select name="layout_id" defaultValue=""><option value="">Layout (assign later)</option>{layouts.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <input name="description" placeholder="Location (optional)" />
          <button className="primary">Enroll display</button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="panel functional-panel">
          <div className="table-head">
            <span>PLAYER</span>
            <span>BUILDING</span>
            <span>STATUS</span>
            <span>CACHE</span>
          </div>
          {players.length ? (
            players.map((player) => (
              <div className="content-line player-line" key={player.id}>
                <div>
                  <b>{player.name}</b>
                  <small>
                    {player.description || "No location details yet"}
                  </small>
                </div>
                <span>{player.building_name}</span>
                <span
                  className={
                    player.health_state === "never_connected"
                      ? "state scheduled"
                      : "state published"
                  }
                >
                  {player.health_state === "never_connected"
                    ? "Never connected"
                    : player.health_state}
                </span>
                <span>{player.cache_state}</span>
              </div>
            ))
          ) : (
            <Empty text="No players are assigned to you yet." />
          )}
        </section>
      )}
    </>
  );
}

function BuildingsView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [items, setItems] = useState<Building[]>([]);
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      request("/buildings", token)
        .then(setItems)
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request("/buildings", token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") || null,
          enabled: true,
        }),
      });
      notify("Building created.");
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create building.");
    }
  };
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">ORGANIZATION</p>
          <h1>Buildings</h1>
          <p>Buildings are the primary scope for access.</p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Add a building</h2>
        <form onSubmit={create} className="inline-form">
          <input name="name" placeholder="Building name" required />
          <input name="description" placeholder="Description (optional)" />
          <button className="secondary-button">Add building</button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="panel functional-panel">
          {items.length ? (
            items.map((item) => (
              <div className="content-line simple-line" key={item.id}>
                <div>
                  <b>{item.name}</b>
                  <small>{item.description || "No description"}</small>
                </div>
                <span
                  className={item.enabled ? "state published" : "state draft"}
                >
                  {item.enabled ? "Active" : "Disabled"}
                </span>
              </div>
            ))
          ) : (
            <Empty text="No buildings are visible to you yet." />
          )}
        </section>
      )}
    </>
  );
}

function LayoutsView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [selected, setSelected] = useState<Layout | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      request("/layouts", token)
        .then((items: Layout[]) => {
          setLayouts(items);
          setSelected(
            (current) =>
              items.find((item) => item.id === current?.id) || items[0] || null,
          );
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request("/layouts", token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") || null,
          enabled: true,
        }),
      });
      notify("Layout created at 1920 × 1080.");
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create layout.");
    }
  };
  const zone = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request(`/layouts/${selected.id}/zones`, token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          x: Number(form.get("x")),
          y: Number(form.get("y")),
          width: Number(form.get("width")),
          height: Number(form.get("height")),
        }),
      });
      notify("Zone added. Save a layout revision when you are ready.");
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to add zone.");
    }
  };
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">DISPLAY STRUCTURE</p>
          <h1>Layouts</h1>
          <p>Landscape 16:9 layouts use a 1920 × 1080 design space.</p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Create layout</h2>
        <form onSubmit={create} className="inline-form">
          <input name="name" placeholder="e.g. Cafeteria layout" required />
          <input name="description" placeholder="Description (optional)" />
          <button className="secondary-button">Create layout</button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      <section className="panel functional-panel">
        <div className="layout-list">
          {layouts.map((layout) => (
            <button
              key={layout.id}
              className={
                selected?.id === layout.id ? "selected-card" : "plain-card"
              }
              onClick={() => setSelected(layout)}
            >
              <b>{layout.name}</b>
              <small>{layout.zones.length} zones</small>
            </button>
          ))}
        </div>
        {selected ? (
          <>
            <h2>{selected.name}</h2>
            <div className="layout-canvas">
              {selected.zones.map((item) => (
                <div
                  key={item.id}
                  className="zone-block"
                  style={{
                    left: `${item.x / 19.2}%`,
                    top: `${item.y / 10.8}%`,
                    width: `${item.width / 19.2}%`,
                    height: `${item.height / 10.8}%`,
                  }}
                >
                  <b>{item.name}</b>
                  <small>
                    {item.width} × {item.height}
                  </small>
                </div>
              ))}
            </div>
            <form onSubmit={zone} className="inline-form">
              <input name="name" placeholder="Zone name" required />
              <input name="x" type="number" defaultValue="0" min="0" />
              <input name="y" type="number" defaultValue="0" min="0" />
              <input name="width" type="number" defaultValue="960" min="1" />
              <input name="height" type="number" defaultValue="1080" min="1" />
              <button className="secondary-button">Add zone</button>
            </form>
          </>
        ) : (
          <Empty text="Create a master layout to define display zones." />
        )}
      </section>
    </>
  );
}

function ContentView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [selected, setSelected] = useState<ContentItem | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      request("/content", token)
        .then((next: ContentItem[]) => {
          setItems(next);
          setSelected(
            (current) =>
              next.find((item) => item.id === current?.id) || next[0] || null,
          );
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const design = designFor(String(form.get("template") || "blank"));
    try {
      const created = await request("/content", token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          design_document: design,
        }),
      });
      notify("Content draft created.");
      formElement.reset();
      setSelected(created);
      setEditing(true);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create content.");
    }
  };
  const save = async () => {
    if (!selected) return;
    const prior =
      selected.draft_version?.design_document ||
      selected.published_version?.design_document;
    if (!prior) return;
    const design = {
      ...prior,
      elements: prior.elements.map((element, index) =>
        index === 0 ? { ...element, text } : element,
      ),
    };
    try {
      await request(`/content/${selected.id}/draft`, token, {
        method: "POST",
        body: JSON.stringify({ design_document: design }),
      });
      notify("Draft saved. Published signage is unchanged until you publish.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save draft.");
    }
  };
  const addElement = (type: string) => {
    if (!selected) return;
    const prior = selected.draft_version?.design_document || selected.published_version?.design_document;
    if (!prior) return;
    const labels: Record<string, string> = { text: "Text", image: "Choose media", video: "Choose video", shape: "", clock: "Clock", date: "Date", weather: "Weather", website: "https://example.org", qr: "QR destination", ticker: "Scrolling message", pdf: "Choose PDF" };
    const design = { ...prior, elements: [...prior.elements, { id: crypto.randomUUID(), type, text: labels[type], x: 180 + prior.elements.length * 30, y: 560, width: 600, height: 100, z_index: prior.elements.length + 1 }] };
    request(`/content/${selected.id}/draft`, token, { method: "POST", body: JSON.stringify({ design_document: design }) }).then(() => { notify(`${type} added to the draft.`); reload(); }).catch((reason) => setError(reason.message));
  };
  const publish = async () => {
    if (!selected) return;
    try {
      await request(`/content/${selected.id}/publish`, token, {
        method: "POST",
      });
      notify("Content published.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to publish content.");
    }
  };
  const persistDesign = async (design: DesignerDocument) => {
    if (!selected) return;
    try {
      await request(`/content/${selected.id}/draft`, token, { method: "POST", body: JSON.stringify({ design_document: design }) });
      setSelected(current => current ? { ...current, draft_version: { revision: current.draft_version?.revision || (current.published_version?.revision || 0) + 1, design_document: design } } : current);
      setItems(current => current.map(item => item.id === selected.id ? { ...item, draft_version: { revision: item.draft_version?.revision || (item.published_version?.revision || 0) + 1, design_document: design } } : item));
    } catch (reason) { setError(reason instanceof Error ? `Draft save failed: ${reason.message}` : "Draft save failed. Your changes remain in this browser."); }
  };
  const document =
    selected?.draft_version?.design_document ||
    selected?.published_version?.design_document;
  if (editing && selected && document) return <DesignerScreen content={selected} document={document as DesignerDocument} token={token} notify={notify} onBack={() => { setEditing(false); reload(); }} onChanged={persistDesign} />;
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">AUTHORING</p>
          <h1>Content</h1>
          <p>
            Draft changes stay separate from active signage until you publish.
          </p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Create content</h2>
        <form onSubmit={create} className="inline-form">
          <input name="name" placeholder="e.g. Welcome back" required />
          <select name="template" defaultValue="announcement">
            <option value="blank">Blank</option>
            <option value="announcement">Announcement</option>
            <option value="event">Event</option>
            <option value="menu">Cafeteria Menu</option>
          </select>
          <button className="secondary-button">Create content</button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      <section className="panel functional-panel">
        <div className="layout-list">
          {items.map((item) => (
            <button
              key={item.id}
              className={
                selected?.id === item.id ? "selected-card" : "plain-card"
              }
              onClick={() => {
                setSelected(item);
                setEditing(true);
                setText(
                  (item.draft_version || item.published_version)
                    ?.design_document.elements[0]?.text || "",
                );
              }}
            >
              <b>{item.name}</b>
              <small>
                {item.draft_version
                  ? "Draft changes"
                  : item.published_version
                    ? `Published v${item.published_version.revision}`
                    : "Draft"}
              </small>
            </button>
          ))}
        </div>
        {selected && document ? (
          <div className="designer">
            <SignalDesigner document={document as DesignerDocument} onChange={persistDesign} onPreview={() => notify("Preview shows the 16:9 design state. Player context is available from each Player's Preview action.")} onPublish={publish} />
            <AssignmentPanel
              content={selected}
              token={token}
              published={Boolean(selected.published_version)}
              notify={notify}
            />
            <small>
              Preview is a 1920 × 1080 server design document. Publishing does
              not change a display until you choose a destination below.
            </small>
          </div>
        ) : (
          <Empty text="Create content to start designing." />
        )}
      </section>
    </>
  );
}

function DesignerScreen({ content, document, token, notify, onBack, onChanged }: { content: ContentItem; document: DesignerDocument; token: string; notify: (message: string) => void; onBack: () => void; onChanged: (document: DesignerDocument) => void }) {
  const [saving, setSaving] = useState("Saved ✓");
  const [publishOpen, setPublishOpen] = useState(false);
  const [published, setPublished] = useState(Boolean(content.published_version));
  const save = (next: DesignerDocument) => { setSaving("Saving…"); onChanged(next); window.setTimeout(() => setSaving("Saved ✓"), 400); };
  const publish = async () => { try { await request(`/content/${content.id}/publish`, token, { method: "POST" }); setPublished(true); notify("Content published. Select one or more destinations below."); } catch (reason) { notify(reason instanceof Error ? reason.message : "Unable to publish content."); } };
  return <main className="designer-page"><header className="designer-header"><button className="back" onClick={onBack}>← Content</button><div className="designer-name"><b>{content.name}</b><small>{saving}</small></div><div className="designer-header-actions"><button className="secondary-button" onClick={() => notify("Preview uses the same 16:9 document as the canvas. This is a server-side design preview, not a player screenshot.")}>Preview</button><button className="primary" onClick={() => setPublishOpen(true)}>Publish</button></div></header><SignalDesigner document={document} onChange={save} onPreview={() => notify("Preview uses the same 16:9 document as the canvas.")} onPublish={() => setPublishOpen(true)} />{publishOpen && <div className="modal-backdrop"><section className="publish-drawer"><header><div><p className="eyebrow">PUBLISH</p><h2>Publish “{content.name}”</h2></div><button className="close" onClick={() => setPublishOpen(false)}>×</button></header>{!published && <section className="publish-step"><p>Your published revision remains unchanged until you confirm.</p><button className="primary" onClick={publish}>Publish revision</button></section>}<AssignmentPanel content={content} token={token} published={published} notify={notify} /><footer><button className="secondary-button" onClick={() => setPublishOpen(false)}>Done</button></footer></section></div>}</main>;
}

function AssignmentPanel({ content, token, published, notify }: { content: ContentItem; token: string; published: boolean; notify: (message: string) => void }) {
  const [players, setPlayers] = useState<Player[]>([]);
  const [zones, setZones] = useState<(Zone & { layout_name: string })[]>([]);
  const [assignments, setAssignments] = useState<{ id: string; destination_type: string; destination_id: string; priority: number; duration_seconds?: number; transition?: string; starts_at?: string; ends_at?: string }[]>([]);
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => Promise.all([request("/destinations", token), request(`/content/${content.id}/assignments`, token)]).then(([destinations, nextAssignments]) => { setPlayers(destinations.players); setZones(destinations.zones); setAssignments(nextAssignments); }).catch((reason) => setError(reason.message)), [content.id, token]);
  useEffect(() => { load(); }, [load]);
  const destinations = [{ id: "", label: "Choose a player or zone", type: "" }, ...players.map(player => ({ id: `player:${player.id}`, label: `${player.building_name} → ${player.name}`, type: "player" })), ...zones.map(zone => ({ id: `zone:${zone.id}`, label: `${zone.layout_name} → ${zone.name}`, type: "zone" }))];
  const assign = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!published) { setError("Publish this content before assigning it to a display."); return; } const form = new FormData(event.currentTarget); const [destinationType, destinationId] = destination.split(":"); if (!destinationType || !destinationId) { setError("Choose a destination."); return; } const endsAt = String(form.get("ends_at") || ""); if (!endsAt && !window.confirm("This content has no expiration date and will remain active until you remove it. Continue?")) return; try { await request(`/content/${content.id}/assignments`, token, { method: "POST", body: JSON.stringify({ destination_type: destinationType, destination_id: destinationId, priority: Number(form.get("priority")), duration_seconds: form.get("duration_seconds") ? Number(form.get("duration_seconds")) : null, transition: form.get("transition"), starts_at: form.get("starts_at") || null, ends_at: endsAt || null }) }); notify("Content assigned. Signal will use its schedule when creating player state."); setDestination(""); event.currentTarget.reset(); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to assign content."); } };
  const remove = async (id: string) => { if (!window.confirm("Remove this destination assignment? The content itself will not be deleted.")) return; try { await request(`/assignments/${id}`, token, { method: "DELETE" }); notify("Assignment removed."); load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to remove assignment."); } };
  return <section className="assignment-panel"><h3>Publish destinations</h3><p>Choose where this published content should appear. Schedule and rotation settings remain independent for each destination.</p><form onSubmit={assign} className="inline-form"><select value={destination} onChange={event => setDestination(event.target.value)} required>{destinations.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select><select name="priority" defaultValue="1"><option value="1">Normal priority</option><option value="2">Elevated priority</option><option value="3">High priority</option></select><input name="duration_seconds" type="number" min="1" placeholder="Duration (20 sec)" /><select name="transition" defaultValue="fade"><option value="none">No transition</option><option value="fade">Fade</option><option value="slide">Slide</option></select><input name="starts_at" type="datetime-local" aria-label="Start time" /><input name="ends_at" type="datetime-local" aria-label="Expiration time" /><button className="secondary-button" disabled={!published}>Assign</button></form>{error && <p className="form-error">{error}</p>}{assignments.length > 0 && <div className="grant-list">{assignments.map(item => <span className="grant-chip" key={item.id}>{item.destination_type} · {item.transition || "default"} · priority {item.priority}<button onClick={() => remove(item.id)} aria-label="Remove assignment">×</button></span>)}</div>}</section>;
}

function UsersView({
  token,
  notify,
}: {
  token: string;
  notify: (m: string) => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [scopeType, setScopeType] = useState("building");
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      Promise.all([
        request("/users", token),
        request("/buildings", token),
        request("/players", token),
      ])
        .then(([nextUsers, nextBuildings, nextPlayers]) => {
          setUsers(nextUsers);
          setBuildings(nextBuildings);
          setPlayers(nextPlayers);
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await request("/users", token, {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          display_name: form.get("display_name"),
          password: form.get("password"),
          enabled: true,
          super_admin: false,
        }),
      });
      notify("User created. Give them access below once they have a scope.");
      formElement.reset();
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create user.");
    }
  };
  const grant = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const userId = String(form.get("user_id"));
    try {
      await request(`/users/${userId}/grants`, token, {
        method: "POST",
        body: JSON.stringify({
          capability: form.get("capability"),
          scope_type: scopeType,
          scope_id: scopeType === "district" ? null : form.get("scope_id"),
        }),
      });
      notify("Access granted. Signal will apply it immediately.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to grant access.");
    }
  };
  const remove = async (userId: string, grantId: string) => {
    try {
      await request(`/users/${userId}/grants/${grantId}`, token, {
        method: "DELETE",
      });
      notify("Access removed.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to remove access.");
    }
  };
  const toggle = async (item: User) => {
    try {
      await request(`/users/${item.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !item.enabled }),
      });
      notify(item.enabled ? "User disabled." : "User enabled.");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update user.");
    }
  };
  const reset = async (item: User) => {
    const password = window.prompt(
      `Set a new temporary password for ${item.display_name} (12+ characters):`,
    );
    if (!password) return;
    if (password.length < 12) {
      setError("Use a password with at least 12 characters.");
      return;
    }
    try {
      await request(`/users/${item.id}/reset-password`, token, {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      notify("Password reset. Existing sessions were ended.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to reset password.");
    }
  };
  const options = scopeType === "building" ? buildings : players;
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">ADMINISTRATION</p>
          <h1>Users &amp; access</h1>
          <p>Access is granted in plain language and enforced by Signal.</p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Create local user</h2>
        <form onSubmit={create} className="inline-form">
          <input name="display_name" placeholder="Full name" required />
          <input name="username" placeholder="username" required />
          <input
            name="password"
            type="password"
            minLength={12}
            placeholder="Temporary password (12+ characters)"
            required
          />
          <button className="secondary-button">Create user</button>
        </form>
      </section>
      <section className="panel create-panel">
        <h2>Give access</h2>
        <p>Choose what a person can do and where they can do it.</p>
        <form onSubmit={grant} className="grant-form">
          <select name="user_id" required defaultValue="">
            <option value="" disabled>
              Choose a user
            </option>
            {users
              .filter((item) => !item.super_admin)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name}
                </option>
              ))}
          </select>
          <select name="capability" defaultValue="view">
            <option value="view">View</option>
            <option value="upload_media">Upload media</option>
            <option value="manage_media">Manage media</option>
            <option value="manage_players">Manage players</option>
            <option value="create_content">Create content</option>
            <option value="edit_content">Edit content</option>
            <option value="publish">Publish</option>
          </select>
          <select
            value={scopeType}
            onChange={(e) => setScopeType(e.target.value)}
          >
            <option value="district">District</option>
            <option value="building">Building</option>
            <option value="player">Player</option>
          </select>
          {scopeType === "district" ? (
            <span className="scope-note">All district resources</span>
          ) : (
            <select name="scope_id" required defaultValue="">
              <option value="" disabled>
                Choose {scopeType}
              </option>
              {options.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          )}
          <button className="secondary-button">Give access</button>
        </form>
      </section>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="panel functional-panel">
          {users.map((item) => (
            <div className="user-access" key={item.id}>
              <div className="user-summary">
                <div>
                  <b>{item.display_name}</b>
                  <small>
                    {item.username} · {item.enabled ? "Enabled" : "Disabled"}
                  </small>
                </div>
                <div className="user-actions">
                  <span
                    className={
                      item.super_admin ? "state published" : "state draft"
                    }
                  >
                    {item.super_admin ? "Super Admin" : "Local user"}
                  </span>
                  {!item.super_admin && (
                    <>
                      <button onClick={() => reset(item)}>
                        Reset password
                      </button>
                      <button onClick={() => toggle(item)}>
                        {item.enabled ? "Disable" : "Enable"}
                      </button>
                    </>
                  )}
                </div>
              </div>
              {!item.super_admin && (
                <div className="grant-list">
                  {item.grants.length ? (
                    item.grants.map((access) => (
                      <span className="grant-chip" key={access.id}>
                        {access.capability.replaceAll("_", " ")} ·{" "}
                        {access.scope_type}
                        <button
                          onClick={() => remove(item.id, access.id)}
                          aria-label="Remove access"
                        >
                          ×
                        </button>
                      </span>
                    ))
                  ) : (
                    <small>No access assigned yet.</small>
                  )}
                </div>
              )}
            </div>
          ))}
        </section>
      )}
    </>
  );
}
function AuditView({ token }: { token: string }) {
  const [items, setItems] = useState<
    { id: string; timestamp: string; action: string; resource_name?: string }[]
  >([]);
  const [error, setError] = useState("");
  useEffect(() => {
    request("/audit", token)
      .then(setItems)
      .catch((e) => setError(e.message));
  }, [token]);
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">ACCOUNTABILITY</p>
          <h1>Audit log</h1>
          <p>Audit history is append-only.</p>
        </div>
      </div>
      {error ? (
        <ErrorState message={error} />
      ) : (
        <section className="panel functional-panel">
          {items.length ? (
            items.map((item) => (
              <div className="audit-row" key={item.id}>
                <b>{item.action.replaceAll(".", " ")}</b>
                <span>{item.resource_name || "Signal resource"}</span>
                <small>{new Date(item.timestamp).toLocaleString()}</small>
              </div>
            ))
          ) : (
            <Empty text="No audit events are available yet." />
          )}
        </section>
      )}
    </>
  );
}
function Loading() {
  return <div className="loading-panel">Loading live Signal data…</div>;
}
function Empty({ text }: { text: string }) {
  return (
    <div className="empty-cta">
      <b>{text}</b>
    </div>
  );
}
function ErrorState({ message }: { message: string }) {
  return (
    <div className="error-panel">
      <b>Signal couldn’t complete that request.</b>
      <p>{message}</p>
    </div>
  );
}
