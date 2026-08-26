"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { SignalDesigner, type DesignerDocument } from "./Designer";

const API =
  process.env.NEXT_PUBLIC_API_BASE ||
  (typeof window === "undefined"
    ? "http://localhost:8000/api/v1"
    : `${window.location.protocol}//${window.location.hostname}:8000/api/v1`);
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
  layout_id?: string | null;
  enrollment_status: string;
  resolution?: string | null;
  health_state: string;
  last_seen_at?: string;
  cache_state: string;
  content_count?: number;
  archived_at?: string | null;
  effective_layout?: { id: string; name: string; system: boolean };
};
type Layout = {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  locked: boolean;
  system?: boolean;
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
type DesignElement = {
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
  url?: string;
  media_id?: string;
  style?: Record<string, string | number>;
};
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
type LibraryItem = {
  id: string;
  kind: "design" | "image" | "video" | "pdf";
  name: string;
  status: string;
  updated_at: string;
  thumbnail_url?: string;
  tags?: string[];
};
type Dashboard = {
  players_total: number;
  players_online: number;
  players_never_connected: number;
  media_total: number;
  warnings: { player: Player }[];
};

function LibraryThumbnail({ item, token }: { item: LibraryItem; token: string }) {
  const [source, setSource] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!item.thumbnail_url) return;
    let live = true;
    let objectUrl = "";
    const thumbnailUrl = item.thumbnail_url.startsWith("/api/v1/") ? `${API.replace(/\/api\/v1$/, "")}${item.thumbnail_url}` : `${API}${item.thumbnail_url}`;
    fetch(thumbnailUrl, { headers: { Authorization: `Bearer ${token}` } })
      .then((response) => { if (!response.ok) throw new Error("Thumbnail unavailable"); return response.blob(); })
      .then((blob) => { objectUrl = URL.createObjectURL(blob); if (live) setSource(objectUrl); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [item.thumbnail_url, token]);
  const label = item.kind === "design" ? "DESIGN" : item.kind === "video" ? "▶ VIDEO" : item.kind === "pdf" ? "PDF" : "IMAGE";
  return source && !failed ? <img src={source} alt={`Preview of ${item.name}`} onError={() => setFailed(true)} /> : <span className="thumbnail-fallback">{item.thumbnail_url && !failed ? "Generating preview…" : label}</span>;
}

function designFor(template: string): DesignDocument {
  const base = {
    schema: "signal.design/v1" as const,
    canvas: { width: 1920, height: 1080 },
  };
  const element = (
    type: string,
    text: string,
    x: number,
    y: number,
    width: number,
    height: number,
  ): DesignElement => ({
    id: crypto.randomUUID(),
    type,
    text,
    x,
    y,
    width,
    height,
    z_index: 1,
  });
  if (template === "event")
    return {
      ...base,
      elements: [
        element("shape", "", 0, 0, 1920, 1080),
        element("text", "Event title", 140, 180, 1500, 170),
        element("text", "Date · Time · Location", 140, 410, 1200, 100),
      ],
    };
  if (template === "menu")
    return {
      ...base,
      elements: [
        element("text", "Monday Lunch Menu", 130, 90, 1500, 140),
        element(
          "text",
          "Entrée\nAlternative\nSides\nFruit\nNotes",
          170,
          310,
          1400,
          520,
        ),
      ],
    };
  if (template === "announcement")
    return {
      ...base,
      elements: [
        element("text", "New announcement", 120, 120, 1500, 160),
        element(
          "text",
          "Add the details your school community needs.",
          120,
          360,
          1400,
          140,
        ),
      ],
    };
  return {
    ...base,
    elements: [element("text", "New content", 120, 120, 1200, 160)],
  };
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
  const [libraryDesignId, setLibraryDesignId] = useState<string | null>(null);
  const [managedPlayerId, setManagedPlayerId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const saved = localStorage.getItem("signal_token");
    if (saved)
      request("/auth/me", saved)
        .then(setUser)
        .then(() => setToken(saved))
        .catch(() => localStorage.removeItem("signal_token"));
  }, []);
  const openLibraryDesign = useCallback((id: string) => {
    setLibraryDesignId(id);
    setView("content");
  }, []);
  const managePlayer = useCallback((id: string) => {
    setManagedPlayerId(id);
    setView("player-details");
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
    ["media", "◫", "Library"],
    ["players", "▣", "Players"],
    ["buildings", "⌂", "Buildings"],
  ];
  if (user.super_admin)
    navigation.push(
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
          <select
            className="mobile-nav"
            value={view}
            aria-label="Navigate Signal"
            onChange={(event) => setView(event.target.value)}
          >
            {navigation.map(([id, _icon, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
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
          {view === "content" && (
            <ContentView
              token={token}
              notify={show}
              initialContentId={libraryDesignId}
              onInitialContentOpened={() => setLibraryDesignId(null)}
            />
          )}
          {view === "media" && (
            <MediaView
              token={token}
              notify={show}
              onOpenDesign={openLibraryDesign}
            />
          )}
          {view === "players" && (
            <PlayersView
              token={token}
              notify={show}
              onManage={managePlayer}
            />
          )}
          {view === "player-details" && managedPlayerId && (
            <PlayerDetailsView
              playerId={managedPlayerId}
              token={token}
              notify={show}
              onBack={() => setView("players")}
            />
          )}
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
  onOpenDesign,
}: {
  token: string;
  notify: (m: string) => void;
  onOpenDesign: (id: string) => void;
}) {
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [kind, setKind] = useState("all");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sendItem, setSendItem] = useState<LibraryItem | null>(null);
  const reload = useCallback(
    () =>
      Promise.all([
        request(
          `/library?kind=${kind}&search=${encodeURIComponent(search)}`,
          token,
        ),
        request("/players", token),
      ])
        .then(([items, visiblePlayers]) => {
          setLibrary(items);
          setPlayers(visiblePlayers);
        })
        .catch((e) => setError(e.message)),
    [token, kind, search],
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
          <p className="eyebrow">SIGNAL LIBRARY</p>
          <h1>Library</h1>
          <p>
            Images, video, PDFs, and editable Signal designs within your access.
          </p>
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
      <section className="panel library-filter">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search designs, files, and tags"
        />
        <div className="button-row">
          {["all", "design", "image", "video", "pdf"].map((item) => (
            <button
              key={item}
              className={kind === item ? "primary" : "secondary-button"}
              onClick={() => setKind(item)}
            >
              {item === "all"
                ? "All"
                : item === "design"
                  ? "Designs"
                  : `${item[0].toUpperCase()}${item.slice(1)}s`}
            </button>
          ))}
        </div>
      </section>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="media-grid real-media">
          {library.length ? (
            library.map((asset) => (
              <article className="media-item" key={`${asset.kind}-${asset.id}`}>
                <div className="asset art-3">
                  <LibraryThumbnail item={asset} token={token} />
                </div>
                <b>{asset.name}</b>
                <small>
                  {asset.kind === "design"
                    ? `Design · ${asset.status}`
                    : `${asset.kind} · ${asset.status}`}
                </small>
                {asset.kind === "design" && (
                  <button
                    className="secondary-button"
                    onClick={() => onOpenDesign(asset.id)}
                  >
                    Open in Designer
                  </button>
                )}
                <button className="primary" onClick={() => setSendItem(asset)}>
                  Send to Display
                </button>
              </article>
            ))
          ) : (
            <Empty text="No media is available in your assigned areas yet." />
          )}
        </section>
      )}
      {sendItem && (
        <SendToDisplayDialog
          item={sendItem}
          token={token}
          onClose={() => setSendItem(null)}
          onSent={(display) => {
            notify(`“${sendItem.name}” was sent to ${display}.`);
            setSendItem(null);
          }}
        />
      )}
    </>
  );
}

function SendToDisplayDialog({
  item,
  token,
  onClose,
  onSent,
  initialDestination,
}: {
  item: LibraryItem;
  token: string;
  onClose: () => void;
  onSent: (display: string) => void;
  initialDestination?: string;
}) {
  const [destinations, setDestinations] = useState<{
    players: Player[];
    zones: (Zone & { layout_name: string })[];
  }>({ players: [], zones: [] });
  const [destination, setDestination] = useState(initialDestination || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    request("/destinations", token)
      .then(setDestinations)
      .catch((reason) => setError(reason.message));
  }, [token]);
  const send = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const [destinationType, destinationId] = destination.split(":");
    if (!destinationType || !destinationId) {
      setError("Choose a display destination.");
      return;
    }
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await request(
        item.kind === "design"
          ? `/content/${item.id}/assignments`
          : `/media/${item.id}/assignments`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            destination_type: destinationType,
            destination_id: destinationId,
            duration_seconds: Number(form.get("duration_seconds") || 20),
            transition: form.get("transition"),
            priority: Number(form.get("priority")),
            enabled: form.get("enabled") === "on",
            starts_at: form.get("start_mode") === "schedule" ? form.get("starts_at") || null : null,
            ends_at: form.get("expire") === "yes" ? form.get("ends_at") || null : null,
          }),
        },
      );
      const display = destinations.players.find((player) => player.id === destinationId)?.name || destinations.zones.find((zone) => zone.id === destinationId)?.name || "this display";
      onSent(display);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to send this item.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="enrollment-modal send-modal" role="dialog" aria-modal="true" aria-labelledby="send-title">
        <header>
          <div><p className="eyebrow">SEND TO DISPLAY</p><h2 id="send-title">Send “{item.name}”</h2></div>
          <button className="close" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <form onSubmit={send}>
          <label>Display
            <select value={destination} onChange={(event) => setDestination(event.target.value)} required>
              <option value="">Choose display</option>
              {destinations.players.map((player) => <option key={player.id} value={`player:${player.id}`}>{player.name} · {player.building_name}</option>)}
            </select>
          </label>
          <div className="playback-fields">
            <label>Duration<input name="duration_seconds" type="number" min="1" max="3600" defaultValue="20" /> seconds</label>
            <label>Transition<select name="transition" defaultValue="fade"><option value="fade">Fade</option><option value="none">None</option><option value="slide">Slide</option></select></label>
            <label>Priority<select name="priority" defaultValue="1"><option value="1">Normal</option><option value="2">Elevated</option><option value="3">High</option></select></label>
          </div>
          <label className="checkbox-label"><input name="enabled" type="checkbox" defaultChecked />Enabled</label>
          <fieldset className="send-schedule"><legend>When</legend><label className="radio-label"><input name="start_mode" type="radio" value="now" defaultChecked />Start now</label><label className="radio-label"><input name="start_mode" type="radio" value="schedule" />Schedule</label><input name="starts_at" type="datetime-local" aria-label="Start date and time" /></fieldset>
          <fieldset className="send-schedule"><legend>Expiration</legend><label className="radio-label"><input name="expire" type="radio" value="no" defaultChecked />No expiration</label><label className="radio-label"><input name="expire" type="radio" value="yes" />Expire</label><input name="ends_at" type="datetime-local" aria-label="Expiration date and time" /></fieldset>
          {error && <p className="enrollment-error">{error}</p>}
          <footer><button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" disabled={busy}>{busy ? "Sending…" : "Send"}</button></footer>
        </form>
      </section>
    </div>
  );
}

type PlayerAssignment = {
  id: string;
  destination_type: string;
  destination_id: string;
  destination_name: string;
  source_type: string;
  source?: { id: string; type: string; name: string; thumbnail_url?: string | null };
  enabled: boolean;
  position: number;
  priority: number;
  duration_seconds?: number | null;
  transition?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  weekdays?: number[] | null;
  daily_start?: string | null;
  daily_end?: string | null;
};

function PlayerDetailsView({
  playerId,
  token,
  notify,
  onBack,
}: {
  playerId: string;
  token: string;
  notify: (message: string) => void;
  onBack: () => void;
}) {
  const [details, setDetails] = useState<{ player: Player; layout: Layout; assignments: PlayerAssignment[] } | null>(null);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [sending, setSending] = useState<LibraryItem | null>(null);
  const [editing, setEditing] = useState<PlayerAssignment | null>(null);
  const [removing, setRemoving] = useState<PlayerAssignment | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const load = useCallback(() => request(`/players/${playerId}`, token).then(setDetails).catch((reason) => setError(reason.message)), [playerId, token]);
  useEffect(() => { load(); }, [load]);
  const forceSync = async () => {
    try {
      await request(`/players/${playerId}/commands`, token, { method: "POST", body: JSON.stringify({ command: "force_sync" }) });
      notify("Force Sync queued. The player will process it on its next check-in.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to queue a sync.");
    }
  };
  const reorder = async (destinationType: string, destinationId: string, movedId: string) => {
    if (!details || !dragging || dragging === movedId) return;
    const group = details.assignments.filter((item) => item.destination_type === destinationType && item.destination_id === destinationId);
    const from = group.findIndex((item) => item.id === dragging);
    const to = group.findIndex((item) => item.id === movedId);
    if (from < 0 || to < 0) return;
    const ordered = [...group];
    const [item] = ordered.splice(from, 1);
    ordered.splice(to, 0, item);
    try {
      await request(`/players/${playerId}/assignments/reorder`, token, { method: "POST", body: JSON.stringify({ destination_type: destinationType, destination_id: destinationId, assignment_ids: ordered.map((entry) => entry.id) }) });
      notify("Display content order updated.");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reorder display content.");
    } finally {
      setDragging(null);
    }
  };
  if (error) return <ErrorState message={error} />;
  if (!details) return <Loading />;
  const { player, assignments } = details;
  const groups = assignments.reduce<{ name: string; type: string; id: string; items: PlayerAssignment[] }[]>((result, item) => {
    const group = result.find((entry) => entry.type === item.destination_type && entry.id === item.destination_id);
    if (group) group.items.push(item);
    else result.push({ name: item.destination_name, type: item.destination_type, id: item.destination_id, items: [item] });
    return result;
  }, []);
  return (
    <>
      <button className="back" onClick={onBack}>← Players</button>
      <section className="display-detail-header">
        <div>
          <p className="eyebrow">DISPLAY</p>
          <h1>{player.name}</h1>
          <p>{player.building_name} · {player.description || "No location details"}</p>
          <p className="detail-layout">Display mode <b>Full Screen</b></p>
          <small>{player.health_state === "online" ? "● Online" : player.health_state === "offline" ? "◐ Offline" : "○ Waiting for connection"} · Last seen {player.last_seen_at ? new Date(player.last_seen_at).toLocaleString() : "never"} · Cache {player.cache_state}</small>
        </div>
        <div className="button-row"><button className="secondary-button" onClick={() => notify("Preview uses the server’s current desired state for this display.")}>Preview</button><button className="secondary-button" onClick={forceSync}>Force Sync</button><button className="primary" onClick={() => setAdding(true)}>+ Add from Library</button></div>
      </section>
      <section className="panel player-content-panel">
        <div className="panel-heading"><div><p className="eyebrow">PLAYBACK</p><h2>Content on this Display</h2><p>Drag items to set the predictable rotation order. Changes sync automatically.</p></div></div>
        {groups.length ? groups.map((group) => (
          <section className="assignment-group" key={`${group.type}:${group.id}`}>
            {groups.length > 1 && <h3>{group.name}</h3>}
            {group.items.map((assignment) => (
              <article className={`assigned-content ${assignment.enabled ? "" : "disabled"}`} key={assignment.id} draggable onDragStart={() => setDragging(assignment.id)} onDragOver={(event) => event.preventDefault()} onDrop={() => reorder(group.type, group.id, assignment.id)}>
                <span className="drag-handle" aria-label="Drag to reorder">☰</span>
                <div className="assignment-thumb">{assignment.source?.thumbnail_url ? <img src={`${API}${assignment.source.thumbnail_url}`} alt="" /> : <span>{assignment.source?.type === "video" ? "▶" : assignment.source?.type === "pdf" ? "PDF" : assignment.source?.type === "image" ? "IMG" : "DESIGN"}</span>}</div>
                <div className="assignment-main"><b>{assignment.source?.name || "Unavailable content"}</b><small>{assignment.source?.type || assignment.source_type} · {assignment.duration_seconds || 20} sec · {assignment.transition || "None"}{assignment.starts_at ? ` · Starts ${new Date(assignment.starts_at).toLocaleString()}` : ""}{assignment.ends_at ? ` · Expires ${new Date(assignment.ends_at).toLocaleString()}` : ""}</small></div>
                <span className={assignment.enabled ? "state published" : "state draft"}>{assignment.enabled ? "Active" : "Disabled"}</span>
                <div className="assignment-actions"><button className="secondary-button" onClick={() => setEditing(assignment)}>Edit Playback</button><button className="card-text-action" onClick={() => setRemoving(assignment)}>Remove</button></div>
              </article>
            ))}
          </section>
        )) : <Empty text="No content is assigned to this display yet. Add a design, image, video, or PDF from the real Library." />}
      </section>
      {adding && <LibraryPickerDialog token={token} onClose={() => setAdding(false)} onSelected={(item) => { setAdding(false); setSending(item); }} />}
      {sending && <SendToDisplayDialog item={sending} token={token} initialDestination={`player:${player.id}`} onClose={() => setSending(null)} onSent={() => { notify(`“${sending.name}” was sent to ${player.name}.`); setSending(null); load(); }} />}
      {editing && <AssignmentEditorDialog assignment={editing} token={token} onClose={() => setEditing(null)} onSaved={() => { notify("Playback settings updated."); setEditing(null); load(); }} />}
      {removing && <RemoveAssignmentDialog assignment={removing} token={token} onClose={() => setRemoving(null)} onRemoved={() => { notify("Content was removed from this display. The original item remains in Signal."); setRemoving(null); load(); }} />}
    </>
  );
}

function LayoutChangeDialog({ player, currentLayout, hasZoneAssignments, token, onClose, onSaved }: { player: Player; currentLayout?: Layout; hasZoneAssignments: boolean; token: string; onClose: () => void; onSaved: (message?: string) => void }) {
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [selected, setSelected] = useState(currentLayout?.id || player.effective_layout?.id || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { request("/player-enrollments/options", token).then((data) => { setLayouts(data.layouts); if (!selected && data.layouts[0]) setSelected(data.layouts[0].id); }).catch((reason) => setError(reason.message)); }, [token]);
  const apply = async () => { setBusy(true); setError(""); try { const result = await request(`/players/${player.id}/layout`, token, { method: "PATCH", body: JSON.stringify({ layout_id: selected }) }); onSaved(result.warning || `Layout changed to ${result.player.effective_layout.name}.`); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to change this display layout."); } finally { setBusy(false); } };
  const preview = layouts.find((layout) => layout.id === selected);
  const changing = Boolean(selected && selected !== currentLayout?.id);
  return <div className="modal-backdrop" role="presentation"><section className="enrollment-modal layout-change-modal" role="dialog" aria-modal="true" aria-labelledby="layout-change-title"><header><div><p className="eyebrow">DISPLAY LAYOUT</p><h2 id="layout-change-title">Change Layout</h2></div><button className="close" aria-label="Close" onClick={onClose}>×</button></header><div className="layout-change-body"><p>Current: <b>{currentLayout?.name || player.effective_layout?.name || "Full Screen"}</b></p><label>Choose Layout<select value={selected} onChange={(event) => setSelected(event.target.value)}>{layouts.map((layout) => <option key={layout.id} value={layout.id}>{layout.name}{layout.system ? " · System" : ""}</option>)}</select></label>{preview && <div className="layout-mini-preview" aria-label={`${preview.name} preview`}>{preview.zones.map((zone) => <span key={zone.id} style={{ left: `${zone.x / 19.2}%`, top: `${zone.y / 10.8}%`, width: `${zone.width / 19.2}%`, height: `${zone.height / 10.8}%` }}>{zone.name}</span>)}</div>}{changing && <p className="layout-warning">{hasZoneAssignments ? "This display has zone-specific content. Assignments not present in the new layout will be preserved for reassignment; direct display content remains available." : "Direct display content remains available after this layout change."}</p>}{error && <p className="enrollment-error">{error}</p>}</div><footer className="modal-footer"><button className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" onClick={apply} disabled={busy || !selected || selected === currentLayout?.id}>{busy ? "Applying…" : "Apply Layout"}</button></footer></section></div>;
}

function LibraryPickerDialog({ token, onClose, onSelected }: { token: string; onClose: () => void; onSelected: (item: LibraryItem) => void }) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("all");
  const [error, setError] = useState("");
  useEffect(() => { request(`/library?kind=${kind}&search=${encodeURIComponent(search)}`, token).then(setItems).catch((reason) => setError(reason.message)); }, [kind, search, token]);
  return <div className="modal-backdrop" role="presentation"><section className="enrollment-modal library-picker" role="dialog" aria-modal="true" aria-labelledby="picker-title"><header><div><p className="eyebrow">LIBRARY</p><h2 id="picker-title">Add Content</h2></div><button className="close" aria-label="Close" onClick={onClose}>×</button></header><div className="picker-controls"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search library" /><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">All types</option><option value="design">Designs</option><option value="image">Images</option><option value="video">Videos</option><option value="pdf">PDFs</option></select></div>{error ? <p className="enrollment-error">{error}</p> : <div className="picker-items">{items.map((item) => <button key={`${item.kind}-${item.id}`} className="picker-item" onClick={() => onSelected(item)}><span>{item.kind.toUpperCase()}</span><div><b>{item.name}</b><small>{item.status}</small></div></button>)}</div>}</section></div>;
}

function AssignmentEditorDialog({ assignment, token, onClose, onSaved }: { assignment: PlayerAssignment; token: string; onClose: () => void; onSaved: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); setBusy(true); try { await request(`/assignments/${assignment.id}`, token, { method: "PATCH", body: JSON.stringify({ destination_type: assignment.destination_type, destination_id: assignment.destination_id, enabled: form.get("enabled") === "on", priority: Number(form.get("priority")), duration_seconds: Number(form.get("duration_seconds") || 20), transition: form.get("transition"), starts_at: form.get("starts_at") || null, ends_at: form.get("ends_at") || null, weekdays: assignment.weekdays || null, daily_start: assignment.daily_start || null, daily_end: assignment.daily_end || null }) }); onSaved(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update playback."); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation"><section className="enrollment-modal" role="dialog" aria-modal="true" aria-labelledby="playback-title"><header><div><p className="eyebrow">PLAYBACK</p><h2 id="playback-title">Edit “{assignment.source?.name}”</h2></div><button className="close" aria-label="Close" onClick={onClose}>×</button></header><form onSubmit={save}><div className="playback-fields"><label>Duration<input name="duration_seconds" type="number" min="1" defaultValue={assignment.duration_seconds || 20} /> seconds</label><label>Transition<select name="transition" defaultValue={assignment.transition || "fade"}><option value="fade">Fade</option><option value="none">None</option><option value="slide">Slide</option></select></label><label>Priority<select name="priority" defaultValue={String(assignment.priority)}><option value="1">Normal</option><option value="2">Elevated</option><option value="3">High</option></select></label></div><label>Start <input name="starts_at" type="datetime-local" defaultValue={assignment.starts_at?.slice(0, 16) || ""} /></label><label>Expiration <input name="ends_at" type="datetime-local" defaultValue={assignment.ends_at?.slice(0, 16) || ""} /></label><label className="checkbox-label"><input name="enabled" type="checkbox" defaultChecked={assignment.enabled} />Enabled</label>{error && <p className="enrollment-error">{error}</p>}<footer><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button></footer></form></section></div>;
}

function RemoveAssignmentDialog({ assignment, token, onClose, onRemoved }: { assignment: PlayerAssignment; token: string; onClose: () => void; onRemoved: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const remove = async () => { setBusy(true); try { await request(`/assignments/${assignment.id}`, token, { method: "DELETE" }); onRemoved(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to remove this item."); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation"><section className="enrollment-modal" role="dialog" aria-modal="true" aria-labelledby="remove-assignment-title"><header><div><p className="eyebrow">REMOVE FROM DISPLAY</p><h2 id="remove-assignment-title">Remove “{assignment.source?.name}”?</h2></div><button className="close" aria-label="Close" onClick={onClose}>×</button></header><div className="remove-player-copy"><p>This removes “{assignment.source?.name}” from this display. The original content will remain in Signal.</p>{error && <p className="enrollment-error">{error}</p>}</div><footer className="modal-footer"><button className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button><button className="danger-button" onClick={remove} disabled={busy}>{busy ? "Removing…" : "Remove from Display"}</button></footer></section></div>;
}

function PlayersView({
  token,
  notify,
  onManage,
}: {
  token: string;
  notify: (m: string) => void;
  onManage: (id: string) => void;
}) {
  const [players, setPlayers] = useState<Player[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [showEnrollment, setShowEnrollment] = useState(false);
  const [editingPlayer, setEditingPlayer] = useState<Player | null>(null);
  const [removingPlayer, setRemovingPlayer] = useState<Player | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(
    () =>
      Promise.all([request("/players", token), request("/buildings", token)])
        .then(([p, b]) => {
          setPlayers(p);
          setBuildings(b);
        })
        .catch((e) => setError(e.message)),
    [token],
  );
  useEffect(() => {
    reload();
    const interval = window.setInterval(reload, 10_000);
    return () => window.clearInterval(interval);
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
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">YOUR DISPLAYS</p>
          <h1>Players</h1>
          <p>Player status is reported by real devices only.</p>
        </div>
        <button className="primary" onClick={() => setShowEnrollment(true)}>
          Enroll Display
        </button>
      </div>
      <details className="panel create-panel placeholder-player">
        <summary>Add Placeholder Display</summary>
        <p>
          Use this only for a record without a physical Signal Player. Real
          devices should be enrolled above.
        </p>
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
          <button className="secondary-button">Add placeholder</button>
        </form>
      </details>
      {error && <ErrorState message={error} />}
      {!error && (
        <section className="player-card-grid">
          {players.length ? (
            players.map((player) => (
              <article className="display-card" key={player.id}>
                <header>
                  <div>
                    <button className="display-name" onClick={() => onManage(player.id)}>
                      {player.name}
                    </button>
                    <p>{player.building_name}</p>
                  </div>
                  <span className={player.health_state === "online" ? "state published" : "state scheduled"}>
                    {player.health_state === "online"
                      ? "● Online"
                      : player.health_state === "offline"
                        ? "◐ Offline"
                        : player.health_state === "waiting_for_enrollment"
                          ? "Waiting for enrollment"
                          : player.health_state === "not_enrolled"
                            ? "Not enrolled"
                            : "Never connected"}
                  </span>
                </header>
                <p className="display-location">{player.description || "No location details"}</p>
                <dl className="display-facts">
                  <div><dt>Content</dt><dd>{player.content_count || 0} item{player.content_count === 1 ? "" : "s"}</dd></div>
                  <div><dt>Cache</dt><dd>{player.cache_state || "Unknown"}</dd></div>
                  <div><dt>Last seen</dt><dd>{player.last_seen_at ? new Date(player.last_seen_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "—"}</dd></div>
                </dl>
                <footer>
                  <button className="secondary-button" onClick={() => onManage(player.id)}>Preview</button>
                  <button className="primary" onClick={() => onManage(player.id)}>Manage Display</button>
                  <button className="card-text-action" onClick={() => setEditingPlayer(player)}>Edit</button>
                  <button className="card-text-action danger" onClick={() => setRemovingPlayer(player)}>Remove</button>
                </footer>
              </article>
            ))
          ) : (
            <Empty text="No players are assigned to you yet." />
          )}
        </section>
      )}
      {showEnrollment && (
        <EnrollmentDialog
          token={token}
          onClose={() => setShowEnrollment(false)}
          onPrepared={(name) => {
            notify(`${name} is waiting for its enrollment code.`);
            reload();
          }}
        />
      )}
      {editingPlayer && (
        <PlayerEditorDialog
          player={editingPlayer}
          buildings={buildings}
          token={token}
          onClose={() => setEditingPlayer(null)}
          onSaved={(name) => {
            setEditingPlayer(null);
            notify(`${name} was updated.`);
            reload();
          }}
        />
      )}
      {removingPlayer && (
        <RemovePlayerDialog
          player={removingPlayer}
          token={token}
          onClose={() => setRemovingPlayer(null)}
          onRemoved={() => {
            notify(`${removingPlayer.name} was removed from active Players.`);
            setRemovingPlayer(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function PlayerEditorDialog({
  player,
  buildings,
  token,
  onClose,
  onSaved,
}: {
  player: Player;
  buildings: Building[];
  token: string;
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    setBusy(true);
    setError("");
    try {
      await request(`/players/${player.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          building_id: form.get("building_id"),
          description: form.get("description") || null,
          enabled: form.get("enabled") === "on",
          resolution: player.resolution || null,
          layout_id: player.layout_id || null,
        }),
      });
      onSaved(name);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to update player.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="enrollment-modal" role="dialog" aria-modal="true" aria-labelledby="edit-player-title">
        <header>
          <div>
            <p className="eyebrow">DISPLAYS</p>
            <h2 id="edit-player-title">Edit Display</h2>
          </div>
          <button className="close" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <form onSubmit={save}>
          <label>
            Display name
            <input name="name" required defaultValue={player.name} autoFocus />
          </label>
          <label>
            Building
            <select name="building_id" required defaultValue={player.building_id}>
              {buildings.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
          <label>
            Location <small>(optional)</small>
            <input name="description" defaultValue={player.description || ""} />
          </label>
          <label className="checkbox-label">
            <input name="enabled" type="checkbox" defaultChecked={player.enabled} />
            Display is enabled
          </label>
          {error && <p className="enrollment-error">{error}</p>}
          <footer>
            <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="primary" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function RemovePlayerDialog({
  player,
  token,
  onClose,
  onRemoved,
}: {
  player: Player;
  token: string;
  onClose: () => void;
  onRemoved: () => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await request(`/players/${player.id}`, token, { method: "DELETE" });
      onRemoved();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Signal could not remove this display.",
      );
    } finally {
      setBusy(false);
    }
  };
  const enrolled = player.enrollment_status === "enrolled";
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="enrollment-modal" role="dialog" aria-modal="true" aria-labelledby="remove-player-title">
        <header>
          <div>
            <p className="eyebrow">REMOVE DISPLAY</p>
            <h2 id="remove-player-title">Remove “{player.name}”?</h2>
          </div>
          <button className="close" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="remove-player-copy">
          <p>This display will no longer appear in active Players. Existing content and media will not be deleted, and historical audit information will be preserved.</p>
          {enrolled && <p className="enrollment-error">This display is currently enrolled. Removing it revokes device access; the physical player will return to safe re-enrollment after its next checks.</p>}
          {error && <p className="enrollment-error">{error}</p>}
        </div>
        <footer className="modal-footer">
          <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="danger-button" onClick={remove} disabled={busy}>{busy ? "Removing…" : "Remove Display"}</button>
        </footer>
      </section>
    </div>
  );
}

function EnrollmentDialog({
  token,
  onClose,
  onPrepared,
}: {
  token: string;
  onClose: () => void;
  onPrepared: (name: string) => void;
}) {
  const [options, setOptions] = useState<{
    buildings: Building[];
    layouts: Layout[];
  }>({ buildings: [], layouts: [] });
  const [prepared, setPrepared] = useState<{
    player: Player;
    enrollment: { code: string; expires_at: string };
  } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    request("/player-enrollments/options", token)
      .then(setOptions)
      .catch((reason) => setError(reason.message));
  }, [token]);

  const prepare = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const result = await request("/players/prepare-enrollment", token, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          building_id: form.get("building_id"),
          layout_id: form.get("layout_id") || null,
          description: form.get("description") || null,
          enabled: true,
        }),
      });
      setPrepared(result);
      onPrepared(result.player.name);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to prepare this display.",
      );
    } finally {
      setBusy(false);
    }
  };
  const regenerate = async () => {
    if (!prepared) return;
    setBusy(true);
    setError("");
    try {
      const result = await request(
        `/players/${prepared.player.id}/enrollment/regenerate`,
        token,
        { method: "POST" },
      );
      setPrepared(result);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to regenerate code.",
      );
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    if (!prepared) return onClose();
    setBusy(true);
    try {
      await request(`/players/${prepared.player.id}/enrollment`, token, {
        method: "DELETE",
      });
      onClose();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to cancel enrollment.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="enrollment-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="enroll-title"
      >
        <header>
          <div>
            <p className="eyebrow">DISPLAYS</p>
            <h2 id="enroll-title">Prepare Display</h2>
          </div>
          <button className="close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        {!prepared ? (
          <form onSubmit={prepare}>
            <label>
              Display name
              <input name="name" placeholder="TEST PI" required autoFocus />
            </label>
            <label>
              Building
              <select name="building_id" required defaultValue="">
                <option value="" disabled>
                  Choose building
                </option>
                {options.buildings.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Location <small>(optional)</small>
              <input name="description" placeholder="Serving line" />
            </label>
            {error && <p className="enrollment-error">{error}</p>}
            <footer>
              <button type="button" className="secondary-button" onClick={onClose}>
                Cancel
              </button>
              <button className="primary" disabled={busy || !options.buildings.length}>
                {busy ? "Generating…" : "Generate Enrollment Code"}
              </button>
            </footer>
          </form>
        ) : (
          <div className="prepared-enrollment">
            <p>Enter this code on the Pi. Signal never needs the Pi’s IP address.</p>
            <div className="enrollment-code">
              <b>{prepared.enrollment.code}</b>
            </div>
            <p>
              Expires at{" "}
              {new Date(prepared.enrollment.expires_at).toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit",
              })}
            </p>
            {error && <p className="enrollment-error">{error}</p>}
            <footer>
              <button
                className="secondary-button"
                onClick={() => navigator.clipboard?.writeText(prepared.enrollment.code)}
              >
                Copy Code
              </button>
              <button className="secondary-button" onClick={regenerate} disabled={busy}>
                Regenerate Code
              </button>
              <button className="primary" onClick={cancel} disabled={busy}>
                Cancel Enrollment
              </button>
            </footer>
          </div>
        )}
      </section>
    </div>
  );
}

function LegacyEnrollmentDialog({
  token,
  onClose,
  onEnrolled,
}: {
  token: string;
  onClose: () => void;
  onEnrolled: (name: string) => void;
}) {
  const [step, setStep] = useState<"code" | "setup">("code");
  const [code, setCode] = useState("");
  const [options, setOptions] = useState<{
    buildings: Building[];
    layouts: Layout[];
  }>({ buildings: [], layouts: [] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const continueCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await request("/player-enrollments/validate", token, {
        method: "POST",
        body: JSON.stringify({ code: code.toUpperCase() }),
      });
      if (result.status !== "valid") {
        setError(
          result.status === "expired"
            ? "This enrollment code has expired. Check the display for its new code."
            : result.status === "used"
              ? "This enrollment code has already been used."
              : "We couldn't find that enrollment code.",
        );
        return;
      }
      setOptions(await request("/player-enrollments/options", token));
      setStep("setup");
    } catch {
      setError(
        "We couldn't validate that enrollment code. Check your permission and try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const claim = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await request("/players/enroll", token, {
        method: "POST",
        body: JSON.stringify({
          code: code.toUpperCase(),
          name: form.get("name"),
          building_id: form.get("building_id"),
          layout_id: form.get("layout_id") || null,
          description: form.get("description") || null,
        }),
      });
      onEnrolled(String(form.get("name")));
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "Unable to enroll display.";
      setError(
        message.includes("expired")
          ? "This enrollment code has expired. Check the display for its new code."
          : message.includes("already been used")
            ? "This enrollment code has already been used."
            : "We couldn't enroll this display. Please check the details and try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="enrollment-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="enroll-title"
      >
        <header>
          <div>
            <p className="eyebrow">DISPLAYS</p>
            <h2 id="enroll-title">Enroll a Display</h2>
          </div>
          <button className="close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        {step === "code" ? (
          <form onSubmit={continueCode}>
            <label>
              Enrollment code
              <input
                autoFocus
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                placeholder="523-UKJ"
                required
              />
            </label>
            <p>The enrollment code is shown on the display you want to add.</p>
            {error && <p className="enrollment-error">{error}</p>}
            <footer>
              <button
                type="button"
                className="secondary-button"
                onClick={onClose}
              >
                Cancel
              </button>
              <button className="primary" disabled={busy}>
                {busy ? "Checking…" : "Continue"}
              </button>
            </footer>
          </form>
        ) : (
          <form onSubmit={claim}>
            <div className="enrollment-code">
              Code: <b>{code} ✓</b>
            </div>
            <label>
              Display name
              <input
                name="name"
                placeholder="HS Cafeteria"
                required
                autoFocus
              />
            </label>
            <label>
              Building
              <select name="building_id" required defaultValue="">
                <option value="" disabled>
                  Choose building
                </option>
                {options.buildings.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Layout
              <select name="layout_id" defaultValue={options.layouts.find((item) => item.system)?.id || options.layouts[0]?.id || ""}>
                {options.layouts.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Location <small>(optional)</small>
              <input name="description" placeholder="Serving line" />
            </label>
            {error && <p className="enrollment-error">{error}</p>}
            <footer>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setStep("code")}
              >
                Back
              </button>
              <button
                className="primary"
                disabled={busy || !options.buildings.length}
              >
                {busy ? "Enrolling…" : "Enroll Display"}
              </button>
            </footer>
          </form>
        )}
      </section>
    </div>
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
  const remove = async () => {
    if (!selected || selected.system) return;
    const confirmed = window.confirm(`Remove “${selected.name}”? Displays assigned to it will return to the Full Screen layout. Content is preserved.`);
    if (!confirmed) return;
    try {
      const result = await request(`/layouts/${selected.id}`, token, { method: "DELETE" });
      notify(`“${selected.name}” was removed. ${result.players_returned_to_full_screen || 0} display(s) returned to Full Screen.`);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to remove layout.");
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
              <small>{layout.system ? "System · Default" : `${layout.zones.length} zones`}</small>
            </button>
          ))}
        </div>
        {selected ? (
          <>
            <div className="layout-detail-title"><div><h2>{selected.name}</h2>{selected.system && <small>Protected system fallback · 1 Main zone</small>}</div>{!selected.system && <button className="card-text-action danger" onClick={remove}>Remove layout</button>}</div>
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
            {selected.system ? <p className="layout-system-note">Full Screen is read-only so every display always has a safe fallback. Create a new layout to customize zones.</p> : <form onSubmit={zone} className="inline-form">
              <input name="name" placeholder="Zone name" required />
              <input name="x" type="number" defaultValue="0" min="0" />
              <input name="y" type="number" defaultValue="0" min="0" />
              <input name="width" type="number" defaultValue="960" min="1" />
              <input name="height" type="number" defaultValue="1080" min="1" />
              <button className="secondary-button">Add zone</button>
            </form>}
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
  initialContentId,
  onInitialContentOpened,
}: {
  token: string;
  notify: (m: string) => void;
  initialContentId: string | null;
  onInitialContentOpened: () => void;
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
          const requested = initialContentId
            ? next.find((item) => item.id === initialContentId)
            : null;
          if (requested) {
            setSelected(requested);
            setEditing(true);
            onInitialContentOpened();
            return;
          }
          setSelected(
            (current) =>
              next.find((item) => item.id === current?.id) || next[0] || null,
          );
        })
        .catch((e) => setError(e.message)),
    [token, initialContentId, onInitialContentOpened],
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
    const prior =
      selected.draft_version?.design_document ||
      selected.published_version?.design_document;
    if (!prior) return;
    const labels: Record<string, string> = {
      text: "Text",
      image: "Choose media",
      video: "Choose video",
      shape: "",
      clock: "Clock",
      date: "Date",
      weather: "Weather",
      website: "https://example.org",
      qr: "QR destination",
      ticker: "Scrolling message",
      pdf: "Choose PDF",
    };
    const design = {
      ...prior,
      elements: [
        ...prior.elements,
        {
          id: crypto.randomUUID(),
          type,
          text: labels[type],
          x: 180 + prior.elements.length * 30,
          y: 560,
          width: 600,
          height: 100,
          z_index: prior.elements.length + 1,
        },
      ],
    };
    request(`/content/${selected.id}/draft`, token, {
      method: "POST",
      body: JSON.stringify({ design_document: design }),
    })
      .then(() => {
        notify(`${type} added to the draft.`);
        reload();
      })
      .catch((reason) => setError(reason.message));
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
      await request(`/content/${selected.id}/draft`, token, {
        method: "POST",
        body: JSON.stringify({ design_document: design }),
      });
      setSelected((current) =>
        current
          ? {
              ...current,
              draft_version: {
                revision:
                  current.draft_version?.revision ||
                  (current.published_version?.revision || 0) + 1,
                design_document: design,
              },
            }
          : current,
      );
      setItems((current) =>
        current.map((item) =>
          item.id === selected.id
            ? {
                ...item,
                draft_version: {
                  revision:
                    item.draft_version?.revision ||
                    (item.published_version?.revision || 0) + 1,
                  design_document: design,
                },
              }
            : item,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? `Draft save failed: ${reason.message}`
          : "Draft save failed. Your changes remain in this browser.",
      );
    }
  };
  const document =
    selected?.draft_version?.design_document ||
    selected?.published_version?.design_document;
  if (editing && selected && document)
    return (
      <DesignerScreen
        content={selected}
        document={document as DesignerDocument}
        token={token}
        notify={notify}
        onBack={() => {
          setEditing(false);
          reload();
        }}
        onChanged={persistDesign}
      />
    );
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">AUTHORING</p>
          <h1>Content</h1>
          <p>Create and save designs here. Send saved versions to displays from Library.</p>
        </div>
      </div>
      <section className="panel create-panel">
        <h2>Create design</h2>
        <form onSubmit={create} className="inline-form">
          <input name="name" placeholder="e.g. Welcome back" required />
          <select name="template" defaultValue="announcement">
            <option value="blank">Blank</option>
            <option value="announcement">Announcement</option>
            <option value="event">Event</option>
            <option value="menu">Cafeteria Menu</option>
          </select>
          <button className="secondary-button">Create design</button>
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
          <div className="content-summary"><b>{selected.name}</b><p>{selected.draft_version ? "Draft saved. Save Version when this design is ready for live displays." : "No working draft."}</p><button className="primary" onClick={() => setEditing(true)}>Edit design</button></div>
        ) : <Empty text="Create a design to start designing." />}
      </section>
    </>
  );
}

function DesignerScreen({
  content,
  document,
  token,
  notify,
  onBack,
  onChanged,
}: {
  content: ContentItem;
  document: DesignerDocument;
  token: string;
  notify: (message: string) => void;
  onBack: () => void;
  onChanged: (document: DesignerDocument) => void;
}) {
  const [saving, setSaving] = useState("Saved ✓");
  const save = (next: DesignerDocument) => {
    setSaving("Saving…");
    onChanged(next);
    window.setTimeout(() => setSaving("Saved ✓"), 400);
  };
  const publish = async () => {
    try {
      await request(`/content/${content.id}/publish`, token, {
        method: "POST",
      });
      notify("Saved as the current display version. Distribution remains in Library.");
    } catch (reason) {
      notify(
        reason instanceof Error ? reason.message : "Unable to publish content.",
      );
    }
  };
  return (
    <main className="designer-page">
      <header className="designer-header">
        <button className="back" onClick={onBack}>
          ← Library
        </button>
        <div className="designer-name">
          <b>{content.name}</b>
          <small>{saving}</small>
        </div>
        <div className="designer-header-actions">
          <button
            className="secondary-button"
            onClick={() =>
              notify(
                "Preview uses the same 16:9 document as the canvas. This is a server-side design preview, not a player screenshot.",
              )
            }
          >
            Preview
          </button>
          <button className="primary" onClick={publish}>Save Version</button>
          <button className="secondary-button" onClick={onBack}>Done</button>
        </div>
      </header>
      <SignalDesigner
        document={document}
        onChange={save}
        onPreview={() =>
          notify("Preview uses the same 16:9 document as the canvas.")
        }
        onPublish={publish}
      />
    </main>
  );
}

function AssignmentPanel({
  content,
  token,
  published,
  notify,
}: {
  content: ContentItem;
  token: string;
  published: boolean;
  notify: (message: string) => void;
}) {
  const [players, setPlayers] = useState<Player[]>([]);
  const [zones, setZones] = useState<(Zone & { layout_name: string })[]>([]);
  const [assignments, setAssignments] = useState<
    {
      id: string;
      destination_type: string;
      destination_id: string;
      priority: number;
      duration_seconds?: number;
      transition?: string;
      starts_at?: string;
      ends_at?: string;
    }[]
  >([]);
  const [destination, setDestination] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      Promise.all([
        request("/destinations", token),
        request(`/content/${content.id}/assignments`, token),
      ])
        .then(([destinations, nextAssignments]) => {
          setPlayers(destinations.players);
          setZones(destinations.zones);
          setAssignments(nextAssignments);
        })
        .catch((reason) => setError(reason.message)),
    [content.id, token],
  );
  useEffect(() => {
    load();
  }, [load]);
  const destinations = [
    { id: "", label: "Choose a player or zone", type: "" },
    ...players.map((player) => ({
      id: `player:${player.id}`,
      label: `${player.building_name} → ${player.name}`,
      type: "player",
    })),
    ...zones.map((zone) => ({
      id: `zone:${zone.id}`,
      label: `${zone.layout_name} → ${zone.name}`,
      type: "zone",
    })),
  ];
  const assign = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!published) {
      setError("Publish this content before assigning it to a display.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const [destinationType, destinationId] = destination.split(":");
    if (!destinationType || !destinationId) {
      setError("Choose a destination.");
      return;
    }
    const endsAt = String(form.get("ends_at") || "");
    if (
      !endsAt &&
      !window.confirm(
        "This content has no expiration date and will remain active until you remove it. Continue?",
      )
    )
      return;
    try {
      await request(`/content/${content.id}/assignments`, token, {
        method: "POST",
        body: JSON.stringify({
          destination_type: destinationType,
          destination_id: destinationId,
          priority: Number(form.get("priority")),
          duration_seconds: form.get("duration_seconds")
            ? Number(form.get("duration_seconds"))
            : null,
          transition: form.get("transition"),
          starts_at: form.get("starts_at") || null,
          ends_at: endsAt || null,
        }),
      });
      notify(
        "Content assigned. Signal will use its schedule when creating player state.",
      );
      setDestination("");
      event.currentTarget.reset();
      load();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to assign content.",
      );
    }
  };
  const remove = async (id: string) => {
    if (
      !window.confirm(
        "Remove this destination assignment? The content itself will not be deleted.",
      )
    )
      return;
    try {
      await request(`/assignments/${id}`, token, { method: "DELETE" });
      notify("Assignment removed.");
      load();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to remove assignment.",
      );
    }
  };
  return (
    <section className="assignment-panel">
      <h3>Publish destinations</h3>
      <p>
        Choose where this published content should appear. Schedule and rotation
        settings remain independent for each destination.
      </p>
      <form onSubmit={assign} className="inline-form">
        <select
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
          required
        >
          {destinations.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
        <select name="priority" defaultValue="1">
          <option value="1">Normal priority</option>
          <option value="2">Elevated priority</option>
          <option value="3">High priority</option>
        </select>
        <input
          name="duration_seconds"
          type="number"
          min="1"
          placeholder="Duration (20 sec)"
        />
        <select name="transition" defaultValue="fade">
          <option value="none">No transition</option>
          <option value="fade">Fade</option>
          <option value="slide">Slide</option>
        </select>
        <input name="starts_at" type="datetime-local" aria-label="Start time" />
        <input
          name="ends_at"
          type="datetime-local"
          aria-label="Expiration time"
        />
        <button className="secondary-button" disabled={!published}>
          Assign
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
      {assignments.length > 0 && (
        <div className="grant-list">
          {assignments.map((item) => (
            <span className="grant-chip" key={item.id}>
              {item.destination_type} · {item.transition || "default"} ·
              priority {item.priority}
              <button
                onClick={() => remove(item.id)}
                aria-label="Remove assignment"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </section>
  );
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
