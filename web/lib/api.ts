const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function clearTokenIfUnauthorized(response: Response): void {
  if (response.status === 401 && typeof window !== "undefined") {
    window.localStorage.removeItem("seo_token");
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data?.detail) && data.detail.length > 0) {
      const first = data.detail[0];
      if (typeof first?.msg === "string") {
        return first.msg;
      }
    }
  } catch {
    return fallback;
  }
  return fallback;
}

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") {
    return { "Content-Type": "application/json" };
  }
  const token = window.localStorage.getItem("seo_token");
  if (!token) {
    return { "Content-Type": "application/json" };
  }
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export type Project = {
  id: string;
  name: string;
  base_url: string;
};

export type AuditStatus = {
  audit_id: string;
  status: "queued" | "running" | "completed" | "failed";
};

export type ScheduleItem = {
  id: string;
  project_id: string;
  url: string;
  weekday: number;
  hour_utc: number;
  minute_utc: number;
  enabled: boolean;
};

export type AdminUserOverview = {
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

export async function register(email: string, password: string): Promise<void> {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  clearTokenIfUnauthorized(response);
  if (!response.ok && response.status !== 409) {
    throw new Error(await readError(response, "Failed to register user"));
  }
}

export async function login(email: string, password: string): Promise<void> {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to login"));
  }
  const data = await response.json();
  if (typeof window !== "undefined") {
    window.localStorage.setItem("seo_token", data.access_token);
  }
}

export async function createProject(name: string, baseUrl: string, notifyEmail?: string): Promise<Project> {
  const response = await fetch(`${API_URL}/projects`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ name, base_url: baseUrl, notify_email: notifyEmail || null })
  });

  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to create project"));
  }

  return response.json();
}

export async function startAudit(projectId: string, url: string): Promise<AuditStatus> {
  const response = await fetch(`${API_URL}/audits/start`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ project_id: projectId, url })
  });

  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to start audit"));
  }

  return response.json();
}

export async function getAuditStatus(auditId: string): Promise<AuditStatus> {
  const response = await fetch(`${API_URL}/audits/${auditId}/status`, { headers: authHeaders() });
  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to read audit status"));
  }
  return response.json();
}

export async function getAuditResults(auditId: string): Promise<any> {
  const response = await fetch(`${API_URL}/audits/${auditId}/results`, { headers: authHeaders() });
  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to read audit results"));
  }
  return response.json();
}

export function getAuditReportUrl(auditId: string): string {
  if (typeof window === "undefined") {
    return `${API_URL}/audits/${auditId}/report.pdf`;
  }
  const token = window.localStorage.getItem("seo_token");
  if (!token) {
    return `${API_URL}/audits/${auditId}/report.pdf`;
  }
  return `${API_URL}/audits/${auditId}/report.pdf?token=${encodeURIComponent(token)}`;
}

export async function createSchedule(projectId: string, url: string): Promise<ScheduleItem> {
  const response = await fetch(`${API_URL}/schedules`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      project_id: projectId,
      url,
      weekday: 1,
      hour_utc: 8,
      minute_utc: 0,
      enabled: true
    })
  });
  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to create schedule"));
  }
  return response.json();
}

export async function getAdminUsersOverview(): Promise<AdminUserOverview[]> {
  const response = await fetch(`${API_URL}/admin/users-overview`, { headers: authHeaders() });
  if (!response.ok) {
    clearTokenIfUnauthorized(response);
    throw new Error(await readError(response, "Failed to load admin users overview"));
  }
  const payload = await response.json();
  return payload.items || [];
}
