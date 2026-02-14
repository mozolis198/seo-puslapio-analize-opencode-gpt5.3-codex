"use client";

import { useEffect, useMemo, useState } from "react";
import {
  createProject,
  createSchedule,
  getAdminUsersOverview,
  getAuditReportUrl,
  getAuditResults,
  getAuditStatus,
  login,
  register,
  startAudit
} from "../lib/api";

type ResultState = {
  score: number;
  issues: Array<{
    key: string;
    title: string;
    details: string;
    severity: string;
    fix_suggestion: string;
    priority_score: number;
  }>;
  recommendations: Array<{ title: string; reason: string; action: string; bucket: string }>;
  checklist: Array<{ key: string; label: string; target: string; value: string; passed: boolean; priority: string }>;
  metrics?: Record<string, number>;
} | null;

type ChecklistItem = { key: string; label: string; target: string; value: string; pass: boolean; priority: string };

type AdBlock = {
  title: string;
  note: string;
  url: string;
};

type AdminUserOverview = {
  user_id: string;
  email: string;
  created_at: string;
  projects_count: number;
  audits_count: number;
  average_score: number | null;
  last_audit_at: string | null;
  pages_checked: Array<{
    url: string;
    audits_count: number;
    last_status: string;
    last_score: number | null;
    last_audit_at: string;
  }>;
};

const defaultAdBlocks: AdBlock[] = [
  { title: "Reklama A1", note: "Vieta banneriui 300x250", url: "" },
  {
    title: "SE Ranking",
    note: "Raktazodziai, pozicijos ir SEO auditas vienoje vietoje",
    url: "https://seranking.com/?ga=79842&source=link&utm_source=seo-auditas&utm_medium=sidebar&utm_campaign=A2"
  },
  { title: "Reklama A3", note: "Vieta native reklamai", url: "" },
  { title: "Reklama A4", note: "Vieta partnerio baneriui", url: "" },
  { title: "Reklama B1", note: "Vieta banneriui 300x250", url: "" },
  { title: "Reklama B2", note: "Vieta partnerio nuorodai", url: "" },
  { title: "Reklama B3", note: "Vieta native reklamai", url: "" },
  { title: "Reklama B4", note: "Vieta remiamam straipsniui", url: "" }
];

function isNotMeasured(value: string): boolean {
  const normalized = value.toLowerCase();
  return normalized.includes("n/a") || normalized.includes("nepamatuota");
}

const statusText: Record<string, string> = {
  queued: "In queue",
  running: "Running scan",
  completed: "Completed",
  failed: "Failed"
};

const STORAGE_KEYS = {
  email: "seo_email",
  projectName: "seo_project_name",
  url: "seo_project_url",
  notifyEmail: "seo_notify_email",
  token: "seo_token",
  theme: "seo_theme",
  adBlocks: "seo_ad_blocks"
} as const;

const ADMIN_EMAIL = (process.env.NEXT_PUBLIC_ADMIN_EMAIL || "mozolis@gmail.com").toLowerCase();

export default function HomePage() {
  const [name, setName] = useState("Mano projektas");
  const [url, setUrl] = useState("https://example.com");
  const [notifyEmail, setNotifyEmail] = useState("");
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [authMode, setAuthMode] = useState<"register" | "login">("register");
  const [robotA, setRobotA] = useState(() => Math.floor(Math.random() * 8) + 1);
  const [robotB, setRobotB] = useState(() => Math.floor(Math.random() * 8) + 1);
  const [robotAnswer, setRobotAnswer] = useState("");
  const [theme, setTheme] = useState<"corporate" | "modern">("corporate");
  const [adminOpen, setAdminOpen] = useState(false);
  const [adminUsers, setAdminUsers] = useState<AdminUserOverview[]>([]);
  const [adminUsersLoading, setAdminUsersLoading] = useState(false);
  const [adminUsersError, setAdminUsersError] = useState("");
  const [adBlocks, setAdBlocks] = useState<AdBlock[]>(defaultAdBlocks);
  const [loggedIn, setLoggedIn] = useState(false);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string>("");
  const [authNotice, setAuthNotice] = useState<string>("");
  const [auditId, setAuditId] = useState<string>("");
  const [result, setResult] = useState<ResultState>(null);

  useEffect(() => {
    const savedEmail = window.localStorage.getItem(STORAGE_KEYS.email);
    const savedName = window.localStorage.getItem(STORAGE_KEYS.projectName);
    const savedUrl = window.localStorage.getItem(STORAGE_KEYS.url);
    const savedNotifyEmail = window.localStorage.getItem(STORAGE_KEYS.notifyEmail);
    const token = window.localStorage.getItem(STORAGE_KEYS.token);
    const savedTheme = window.localStorage.getItem(STORAGE_KEYS.theme);
    const savedAdBlocks = window.localStorage.getItem(STORAGE_KEYS.adBlocks);

    if (savedEmail) setEmail(savedEmail);
    if (savedName) setName(savedName);
    if (savedUrl) setUrl(savedUrl);
    if (savedNotifyEmail) setNotifyEmail(savedNotifyEmail);
    if (token) setLoggedIn(true);
    if (savedTheme === "corporate" || savedTheme === "modern") setTheme(savedTheme);
    if (savedAdBlocks) {
      try {
        const parsed = JSON.parse(savedAdBlocks) as AdBlock[];
        if (Array.isArray(parsed) && parsed.length === 8) {
          setAdBlocks(parsed);
        }
      } catch {
        setAdBlocks(defaultAdBlocks);
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.email, email);
  }, [email]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.projectName, name);
  }, [name]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.url, url);
  }, [url]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.notifyEmail, notifyEmail);
  }, [notifyEmail]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.theme, theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.adBlocks, JSON.stringify(adBlocks));
  }, [adBlocks]);

  function updateAdBlock(index: number, field: keyof AdBlock, value: string) {
    setAdBlocks((current) => current.map((item, idx) => (idx === index ? { ...item, [field]: value } : item)));
  }

  function resetAdBlocks() {
    setAdBlocks(defaultAdBlocks);
  }

  function resetRobotCheck() {
    setRobotA(Math.floor(Math.random() * 8) + 1);
    setRobotB(Math.floor(Math.random() * 8) + 1);
    setRobotAnswer("");
  }

  const isAdminEmail = loggedIn && email.trim().toLowerCase() === ADMIN_EMAIL;

  useEffect(() => {
    if (!isAdminEmail || !adminOpen) {
      return;
    }

    let cancelled = false;
    setAdminUsersLoading(true);
    setAdminUsersError("");

    getAdminUsersOverview()
      .then((items) => {
        if (!cancelled) {
          setAdminUsers(items);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setAdminUsersError(error instanceof Error ? error.message : "Nepavyko uzkrauti vartotoju saraso");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAdminUsersLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isAdminEmail, adminOpen]);

  const badge = useMemo(() => {
    if (!result) return "-";
    if (result.score >= 80) return "Good";
    if (result.score >= 60) return "Needs work";
    return "Critical";
  }, [result]);

  const technicalChecklist = useMemo<ChecklistItem[]>(() => {
    if (!result?.checklist) return [];
    return result.checklist.map((item) => ({
      key: item.key,
      label: item.label,
      target: item.target,
      value: item.value,
      pass: item.passed,
      priority: item.priority
    }));
  }, [result]);

  const checklistPassedCount = useMemo(() => technicalChecklist.filter((item) => item.pass).length, [technicalChecklist]);
  const checklistTotal = technicalChecklist.length || 20;

  const groupedChecklist = useMemo(() => {
    return {
      do_now: technicalChecklist.filter((item) => !item.pass && !isNotMeasured(item.value) && item.priority === "do_now"),
      this_week: technicalChecklist.filter((item) => !item.pass && !isNotMeasured(item.value) && item.priority === "this_week"),
      later: technicalChecklist.filter((item) => !item.pass && !isNotMeasured(item.value) && item.priority === "later")
    };
  }, [technicalChecklist]);

  const groupedRecommendations = useMemo(() => {
    const list = result?.recommendations ?? [];
    return {
      do_now: list.filter((item) => item.bucket === "do_now"),
      this_week: list.filter((item) => item.bucket === "this_week"),
      later: list.filter((item) => item.bucket === "later")
    };
  }, [result]);

  async function runAnalysis() {
    setStatus("creating");
    setError("");
    setAuditId("");
    setResult(null);

    try {
      const project = await createProject(name, url, notifyEmail || undefined);
      await createSchedule(project.id, url);
      const audit = await startAudit(project.id, url);
      setAuditId(audit.audit_id);
      setStatus(audit.status);

      let currentStatus = audit.status;
      while (currentStatus === "queued" || currentStatus === "running") {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        const fresh = await getAuditStatus(audit.audit_id);
        currentStatus = fresh.status;
        setStatus(currentStatus);
      }

      if (currentStatus === "completed") {
        const data = await getAuditResults(audit.audit_id);
        setResult({
          score: data.score,
          issues: data.issues,
          recommendations: data.recommendations,
          checklist: data.checklist ?? [],
          metrics: data.metrics
        });
      } else {
        setError("Analize nepavyko. Patikrink URL ir bandyk dar karta.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ivyko klaida.");
      setStatus("failed");
    }
  }

  async function handleRegisterUser() {
    setError("");
    setAuthNotice("");
    if (!email.includes("@")) {
      setError("Ivesk teisinga el. pasta.");
      return;
    }
    if (password.length < 8) {
      setError("Slaptazodis turi buti bent 8 simboliu.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Slaptazodziai nesutampa.");
      return;
    }
    if (Number(robotAnswer) !== robotA + robotB) {
      setError("Neteisingas roboto patikrinimas.");
      resetRobotCheck();
      return;
    }
    try {
      await register(email, password);
      setPassword("");
      setConfirmPassword("");
      setAuthNotice("Registracija sekminga. Dabar prisijunk su tuo paciu el. pastu.");
      resetRobotCheck();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth klaida.");
    }
  }

  async function handleUserLogin() {
    setError("");
    setAuthNotice("");
    if (!email.includes("@")) {
      setError("Ivesk teisinga el. pasta.");
      return;
    }
    if (password.length < 8) {
      setError("Slaptazodis turi buti bent 8 simboliu.");
      return;
    }
    try {
      await login(email, password);
      setLoggedIn(true);
      setPassword("");
      setConfirmPassword("");
      setAuthNotice("Prisijungimas sekmingas.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prisijungimo klaida.");
    }
  }

  async function handleAdminLogin() {
    setError("");
    setAuthNotice("");
    if (email.trim().toLowerCase() !== ADMIN_EMAIL) {
      setError(`Admin prisijungimui naudok admin el. pasta: ${ADMIN_EMAIL}`);
      return;
    }
    if (password.length < 8) {
      setError("Slaptazodis turi buti bent 8 simboliu.");
      return;
    }
    if (Number(robotAnswer) !== robotA + robotB) {
      setError("Neteisingas roboto patikrinimas.");
      resetRobotCheck();
      return;
    }

    try {
      await login(email, password);
      setLoggedIn(true);
      setPassword("");
      setConfirmPassword("");
      setAdminOpen(true);
      setAuthNotice("Admin prisijungimas sekmingas.");
      resetRobotCheck();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin auth klaida.");
    }
  }

  function handleAdminLogout() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEYS.token);
    }
    setLoggedIn(false);
    setAdminOpen(false);
    setStatus("idle");
    setError("");
    setResult(null);
    setAuditId("");
  }

  return (
    <main className={`layout-shell ${theme === "modern" ? "theme-modern" : "theme-corporate"}`}>
      <aside className="side-rail">
        {adBlocks.slice(0, 4).map((block, index) => (
          <article key={`left-ad-${index}`} className="side-block ad-block">
            <h4 className="ad-title">
              <span className="ad-badge">{index + 1}</span>
              <span>{block.title}</span>
            </h4>
            <p className="side-note">{block.note}</p>
            {block.url && (
              <a className="ad-link" href={block.url} target="_blank" rel="noreferrer">
                Atidaryti reklama
              </a>
            )}
          </article>
        ))}
      </aside>

      <div className="page">
      <section className="hero">
        <h1>SEO Puslapio Analize</h1>
        <p>Greitai gauk isvadas ir prioritetinius veiksmus puslapio matomumui gerinti.</p>
        <nav className="quick-links">
          <a href="/#auditas">SEO auditas</a>
          <a href="/#checklist">Techninis checklist</a>
          <a href="/#planas">Veiksmu planas</a>
          <a href="/#gidas">SEO gidas</a>
        </nav>
        <div className="theme-switch">
          <button
            className={theme === "corporate" ? "active" : ""}
            onClick={() => setTheme("corporate")}
            type="button"
          >
            Corporate Clean
          </button>
          <button
            className={theme === "modern" ? "active" : ""}
            onClick={() => setTheme("modern")}
            type="button"
          >
            Modern SEO Dashboard
          </button>
        </div>

        <div className="admin-access">
          {isAdminEmail ? (
            <>
              <button className={adminOpen ? "active" : ""} onClick={() => setAdminOpen((v) => !v)} type="button">
                {adminOpen ? "Uzdaryti admin meniu" : "Atidaryti admin meniu"}
              </button>
              <button type="button" className="secondary-btn" onClick={handleAdminLogout}>
                Atsijungti is admin
              </button>
            </>
          ) : (
            <p className="admin-hint">Admin meniu matomas tik prisijungus su admin el. pastu: {ADMIN_EMAIL}</p>
          )}
        </div>
      </section>

      {isAdminEmail && adminOpen && (
        <section className="panel admin-panel">
          <div className="admin-header">
            <h2>Reklamu valdymas</h2>
            <button type="button" onClick={resetAdBlocks}>
              Atstatyti numatytus blokus
            </button>
          </div>

          <article className="admin-users">
            <h3>Vartotoju sarasas ir tikrinti puslapiai</h3>
            {adminUsersLoading && <p>Kraunamas vartotoju sarasas...</p>}
            {adminUsersError && <p className="error">{adminUsersError}</p>}
            {!adminUsersLoading && !adminUsersError && adminUsers.length === 0 && <p>Kol kas nera vartotoju duomenu.</p>}

            {!adminUsersLoading && !adminUsersError && adminUsers.length > 0 && (
              <div className="admin-users-grid">
                {adminUsers.map((item) => (
                  <article key={item.user_id} className="admin-user-item">
                    <h4>{item.email}</h4>
                    <p>
                      Projektai: {item.projects_count} | Auditai: {item.audits_count}
                    </p>
                    <p>Vidutinis ivertinimas: {item.average_score !== null ? `${item.average_score}/100` : "-"}</p>
                    <p>Paskutinis auditas: {item.last_audit_at ? new Date(item.last_audit_at).toLocaleString() : "-"}</p>
                    <p>Tikrinti puslapiai:</p>
                    <ul>
                      {item.pages_checked.length > 0 ? (
                        item.pages_checked.map((page) => (
                          <li key={`${item.user_id}-${page.url}`}>
                            <strong>{page.url}</strong>
                            <p>
                              Status: {page.last_status} | Ivertinimas: {page.last_score ?? "-"} | Auditai: {page.audits_count}
                            </p>
                          </li>
                        ))
                      ) : (
                        <li>Nera nuskenuotu puslapiu</li>
                      )}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </article>

          <div className="admin-grid">
            {adBlocks.map((block, index) => (
              <article key={`admin-ad-${index}`} className="admin-item">
                <h4>Blokas {index + 1}</h4>
                <label>
                  Pavadinimas
                  <input
                    value={block.title}
                    onChange={(event) => updateAdBlock(index, "title", event.target.value)}
                    placeholder="Reklamos pavadinimas"
                  />
                </label>
                <label>
                  Tekstas
                  <input
                    value={block.note}
                    onChange={(event) => updateAdBlock(index, "note", event.target.value)}
                    placeholder="Trumpas aprasymas"
                  />
                </label>
                <label>
                  Nuoroda
                  <input
                    value={block.url}
                    onChange={(event) => updateAdBlock(index, "url", event.target.value)}
                    placeholder="https://..."
                  />
                </label>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <label>
          Projekto pavadinimas
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>

        <label>
          URL
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://..." />
        </label>

        <label>
          Pranesimu el. pastas (pasirinktinai)
          <input value={notifyEmail} onChange={(event) => setNotifyEmail(event.target.value)} placeholder="you@email.com" />
        </label>

        <button onClick={runAnalysis} disabled={!loggedIn}>
          Paleisti analize
        </button>

        {status !== "idle" && <p className="status">Statusas: {statusText[status] || status}</p>}
        {error && <p className="error">{error}</p>}
      </section>

      <section id="auditas" className="panel seo-content">
        <h2>Ka duoda SEO auditas tavo puslapiui</h2>
        <p>
          SEO auditas padeda aiskiai suprasti, kas stabdo tavo matomuma paieskoje. Dažniausiai problema nebuna viena: kartu veikia
          technines klaidos, silpna puslapio struktura, nepakankamas turinys ir netinkami puslapio signalai paieskos sistemoms.
          Kai viskas sudedama i viena ataskaita, gali greitai priimti sprendimus ir tvarkyti tai, kas duoda didziausia poveiki.
        </p>
        <p>
          Si sistema pirmiausia tikrina indeksavimo logika: HTTP statusa, canonical, robots taisykles ir sitemap buvima. Tada
          vertina turinio kokybe: title, meta aprasyma, H1-H2 struktura, turinio gyli, vidines nuorodas ir Open Graph signalus.
          Galiausiai pateikia prioritetus pagal darbus: ka daryti dabar, ka planuoti sia savaite ir ka palikti velesniam etapui.
          Tokia eiga leidzia isvengti chaoso ir nekaupti technines skolos.
        </p>
      </section>

      <section id="gidas" className="panel seo-content">
        <h2>Praktinis SEO gerinimo gidas</h2>
        <p>
          Pradek nuo puslapio pagrindo. Pirmas tikslas yra uztikrinti, kad puslapis butu pasiekiamas ir teisingai indeksuojamas.
          Jei canonical nerastas, paieskos sistema gali matyti kelias to paties turinio versijas. Jei nera sitemap, crawleriui
          sunkiau aptikti svarbius URL. Jei title ar meta aprasymas per trumpi, prarandi paspaudimus paieskos rezultatuose.
        </p>
        <p>
          Antras tikslas - turinio verte. Kiekvienas svarbus puslapis turi tureti aisku tiksla, bent viena stipru H2 skyriu ir
          pakankama teksto gyli, kad atsakytu i vartotojo klausima. Jei turinys labai trumpas, sunkiau konkuruoti su stipresniais
          rezultatais. Taip pat svarbu vidines nuorodos: jos padeda perduoti autoriteta tarp puslapiu ir rodo, kurie URL yra
          prioritetiniai tavo svetaineje.
        </p>
        <p>
          Trecias tikslas - nuoseklus tobulinimas. Po kiekvieno pakeitimo paleisk pakartotine analize ir stebek score pokyti.
          Jei score kyla, toliau gilink tas pacias kryptis. Jei score stovi vietoje, ziurek i checklist punktus su didziausiu
          poveikiu ir zemiausiu igyvendinimo sudetingumu. Tokiu budu gauni ne tik grazesne ataskaita, bet ir realu augima
          organiniame sraute.
        </p>
      </section>

      {result && (
        <section className="results">
          <div className="score">
            <h2>SEO Score: {result.score}/100</h2>
            <p>Busena: {badge}</p>
            {auditId && (
              <p>
                <a className="report-link" href={getAuditReportUrl(auditId)} target="_blank" rel="noreferrer">
                  Atsisiusti PDF ataskaita
                </a>
              </p>
            )}
            {result.metrics?.lighthouse_seo_score !== undefined && (
              <p>Lighthouse SEO: {Math.round(result.metrics.lighthouse_seo_score)}/100</p>
            )}
            {result.metrics?.lighthouse_performance_score !== undefined && (
              <p>Lighthouse Performance: {Math.round(result.metrics.lighthouse_performance_score)}/100</p>
            )}
          </div>

          <div className="grid">
            <article className="panel">
              <h3>Top problemos</h3>
              <ul>
                {result.issues.slice(0, 5).map((issue) => (
                  <li key={issue.title}>
                    <strong>{issue.title}</strong>
                    <p>
                      {issue.severity} | priority {issue.priority_score}
                    </p>
                    <p>
                      <strong>Kodel svarbu:</strong> {issue.details}
                    </p>
                    <p>{issue.fix_suggestion}</p>
                  </li>
                ))}
              </ul>
            </article>

            <article className="panel">
              <h3>Veiksmu planas</h3>
              <ul>
                {result.recommendations.slice(0, 7).map((item, index) => (
                  <li key={`${item.title}-${index}`}>
                    <strong>{item.title}</strong>
                    <p>Kada: {item.bucket}</p>
                    <p>
                      <strong>Paaiskinimas:</strong> {item.reason}
                    </p>
                    <p>{item.action}</p>
                  </li>
                ))}
              </ul>
            </article>
          </div>

          <article id="checklist" className="panel checklist-panel">
            <h3>Techninis checklist ({checklistPassedCount}/{checklistTotal})</h3>
            <ul className="checklist-list">
              {technicalChecklist.map((item) => (
                <li
                  key={item.key}
                  className={`check-item ${isNotMeasured(item.value) ? "na" : item.pass ? "pass" : "fail"}`}
                >
                  <strong>{item.label}</strong>
                  <p>{isNotMeasured(item.value) ? "N/A" : item.pass ? "PASS" : "FAIL"}</p>
                  <p>Tikslas: {item.target}</p>
                  <p>Reiksme: {item.value}</p>
                </li>
              ))}
            </ul>
          </article>

          <article id="planas" className="panel checklist-panel">
            <h3>Prioritetu grupes</h3>
            <div className="priority-grid">
              <div>
                <h4>Dabar</h4>
                <ul>
                  {groupedChecklist.do_now.slice(0, 6).map((item) => (
                    <li key={`now-${item.key}`}>{item.label}</li>
                  ))}
                  {groupedChecklist.do_now.length === 0 && <li>Nera kritiniu neatitikimu</li>}
                </ul>
              </div>
              <div>
                <h4>Sia savaite</h4>
                <ul>
                  {groupedChecklist.this_week.slice(0, 6).map((item) => (
                    <li key={`week-${item.key}`}>{item.label}</li>
                  ))}
                  {groupedChecklist.this_week.length === 0 && <li>Nera neatitikimu</li>}
                </ul>
              </div>
              <div>
                <h4>Veliau</h4>
                <ul>
                  {groupedChecklist.later.slice(0, 6).map((item) => (
                    <li key={`later-${item.key}`}>{item.label}</li>
                  ))}
                  {groupedChecklist.later.length === 0 && <li>Nera neatitikimu</li>}
                </ul>
              </div>
            </div>
          </article>

          <article className="panel checklist-panel">
            <h3>Veiksmu planas pagal prioritetus</h3>
            <div className="priority-grid">
              <div>
                <h4>Dabar</h4>
                <ul>
                  {groupedRecommendations.do_now.slice(0, 4).map((item, idx) => (
                    <li key={`r-now-${idx}`}>{item.title}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Sia savaite</h4>
                <ul>
                  {groupedRecommendations.this_week.slice(0, 4).map((item, idx) => (
                    <li key={`r-week-${idx}`}>{item.title}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Veliau</h4>
                <ul>
                  {groupedRecommendations.later.slice(0, 4).map((item, idx) => (
                    <li key={`r-later-${idx}`}>{item.title}</li>
                  ))}
                </ul>
              </div>
            </div>
          </article>
        </section>
      )}
      </div>

      <aside className="side-rail">
        {adBlocks.slice(4).map((block, index) => (
          <article key={`right-ad-${index}`} className="side-block ad-block">
            <h4 className="ad-title">
              <span className="ad-badge">{index + 5}</span>
              <span>{block.title}</span>
            </h4>
            <p className="side-note">{block.note}</p>
            {block.url && (
              <a className="ad-link" href={block.url} target="_blank" rel="noreferrer">
                Atidaryti reklama
              </a>
            )}
          </article>
        ))}

        <article className="side-block auth-block in-rail">
          <h3>Prisijungimas</h3>

          <label>
            El. pastas
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>

          <label>
            Slaptazodis
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>

          <div className="auth-mode-tabs">
            <button
              type="button"
              className={authMode === "register" ? "active" : ""}
              onClick={() => setAuthMode("register")}
            >
              Registracija
            </button>
            <button type="button" className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")}>
              Prisijungti
            </button>
          </div>

          {authMode === "register" && (
            <>
              <label>
                Pakartok slaptazodi
                <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
              </label>

              <label>
                Roboto patikrinimas: kiek yra {robotA} + {robotB}?
                <input value={robotAnswer} onChange={(event) => setRobotAnswer(event.target.value)} placeholder="Ivesk atsakyma" />
              </label>
            </>
          )}

          {authMode === "login" && (
            <label>
              Roboto patikrinimas: kiek yra {robotA} + {robotB}?
              <input value={robotAnswer} onChange={(event) => setRobotAnswer(event.target.value)} placeholder="Ivesk atsakyma" />
            </label>
          )}

          <div className="auth-buttons">
            {authMode === "register" ? (
              <button type="button" onClick={handleRegisterUser}>
                Registruoti nauja vartotoja
              </button>
            ) : (
              <button type="button" onClick={handleUserLogin}>
                Prisijungti kaip vartotojas
              </button>
            )}
            <button type="button" className="secondary-btn" onClick={handleAdminLogin}>
              Prisijungti kaip adminas
            </button>
          </div>

          {loggedIn && <p className="status">Prisijungta su: {email}</p>}
          {authNotice && <p className="status">{authNotice}</p>}
        </article>
      </aside>
    </main>
  );
}
