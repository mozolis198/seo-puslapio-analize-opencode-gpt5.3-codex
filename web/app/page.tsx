"use client";

import { useEffect, useMemo, useState } from "react";
import {
  createProject,
  createSchedule,
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
  theme: "seo_theme"
} as const;

export default function HomePage() {
  const [name, setName] = useState("Mano projektas");
  const [url, setUrl] = useState("https://example.com");
  const [notifyEmail, setNotifyEmail] = useState("");
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("");
  const [theme, setTheme] = useState<"corporate" | "modern">("corporate");
  const [loggedIn, setLoggedIn] = useState(false);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string>("");
  const [auditId, setAuditId] = useState<string>("");
  const [result, setResult] = useState<ResultState>(null);

  useEffect(() => {
    const savedEmail = window.localStorage.getItem(STORAGE_KEYS.email);
    const savedName = window.localStorage.getItem(STORAGE_KEYS.projectName);
    const savedUrl = window.localStorage.getItem(STORAGE_KEYS.url);
    const savedNotifyEmail = window.localStorage.getItem(STORAGE_KEYS.notifyEmail);
    const token = window.localStorage.getItem(STORAGE_KEYS.token);
    const savedTheme = window.localStorage.getItem(STORAGE_KEYS.theme);

    if (savedEmail) setEmail(savedEmail);
    if (savedName) setName(savedName);
    if (savedUrl) setUrl(savedUrl);
    if (savedNotifyEmail) setNotifyEmail(savedNotifyEmail);
    if (token) setLoggedIn(true);
    if (savedTheme === "corporate" || savedTheme === "modern") setTheme(savedTheme);
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
      do_now: technicalChecklist.filter((item) => !item.pass && item.priority === "do_now"),
      this_week: technicalChecklist.filter((item) => !item.pass && item.priority === "this_week"),
      later: technicalChecklist.filter((item) => !item.pass && item.priority === "later")
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

  async function handleAuth() {
    setError("");
    if (password.length < 8) {
      setError("Slaptazodis turi buti bent 8 simboliu.");
      return;
    }
    try {
      await register(email, password);
      await login(email, password);
      setLoggedIn(true);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth klaida.");
    }
  }

  return (
    <main className={`layout-shell ${theme === "modern" ? "theme-modern" : "theme-corporate"}`}>
      <aside className="side-rail">
        <article className="side-block">
          <h4>Dabar</h4>
          <p className="side-value">{groupedChecklist.do_now.length}</p>
          <p className="side-note">Kritiniai neatitikimai</p>
        </article>
        <article className="side-block">
          <h4>Sia savaite</h4>
          <p className="side-value">{groupedChecklist.this_week.length}</p>
          <p className="side-note">Vidutinio prioriteto darbai</p>
        </article>
        <article className="side-block ad-block">
          <h4>Reklama A1</h4>
          <p className="side-note">Vieta banneriui 300x250</p>
        </article>
        <article className="side-block ad-block">
          <h4>Reklama A2</h4>
          <p className="side-note">Vieta remiamam pasiulymui</p>
        </article>
      </aside>

      <div className="page">
      <section className="hero">
        <h1>SEO Puslapio Analize</h1>
        <p>Greitai gauk isvadas ir prioritetinius veiksmus puslapio matomumui gerinti.</p>
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
      </section>

      <section className="card">
        <label>
          El. pastas
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>

        <label>
          Slaptazodis
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>

        <button onClick={handleAuth}>{loggedIn ? "Prisijungta" : "Registruotis ir prisijungti"}</button>

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

          <article className="panel checklist-panel">
            <h3>Techninis checklist ({checklistPassedCount}/{checklistTotal})</h3>
            <ul className="checklist-list">
              {technicalChecklist.map((item) => (
                <li key={item.key} className={`check-item ${item.pass ? "pass" : "fail"}`}>
                  <strong>{item.label}</strong>
                  <p>{item.pass ? "PASS" : "FAIL"}</p>
                  <p>Tikslas: {item.target}</p>
                  <p>Reiksme: {item.value}</p>
                </li>
              ))}
            </ul>
          </article>

          <article className="panel checklist-panel">
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
        <article className="side-block">
          <h4>Veliau</h4>
          <p className="side-value">{groupedChecklist.later.length}</p>
          <p className="side-note">Zemo prioriteto darbai</p>
        </article>
        <article className="side-block">
          <h4>Progresas</h4>
          <p className="side-value">
            {checklistPassedCount}/{checklistTotal}
          </p>
          <p className="side-note">TOP 20 checklist rezultatas</p>
        </article>
        <article className="side-block ad-block">
          <h4>Reklama B1</h4>
          <p className="side-note">Vieta banneriui 300x250</p>
        </article>
        <article className="side-block ad-block">
          <h4>Reklama B2</h4>
          <p className="side-note">Vieta partnerio nuorodai</p>
        </article>
      </aside>
    </main>
  );
}
