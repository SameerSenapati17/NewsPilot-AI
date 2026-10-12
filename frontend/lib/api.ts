const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail || "NewsPilotAI API is currently unavailable.");
  }
  return response.json() as Promise<T>;
}

export type Trend = { topic:string; score:number; is_emerging:boolean; metrics:Record<string,number|string>; explanation:string };
export type NewsItem = { id:string; story_id?:string; title:string; url:string; description?:string; published_at:string; source:string };
export type SearchResult = { content_item_id:string; story_id?:string; title:string; url?:string; published_at?:string; similarity:number };
export type RankedItem = { content_item_id:string; story_id?:string; title:string; url?:string; final_score:number; explanation:{reasons:string[]} };
export type AskResponse = { query:string; answer:string; sources:Array<{title?:string;url?:string;published_at?:string;text?:string;content_item_id?:string}> };

export const api = {
  health: () => request<{status:string}>("/api/health"),
  news: (page=1, pageSize=20) => request<{items:NewsItem[];page:number;page_size:number;total:number}>(`/api/news?page=${page}&page_size=${pageSize}`),
  stories: (page=1, pageSize=20) => request<{items:Array<{story_id:string;title:string;representative?:NewsItem;content_item_count:number;latest_published_at?:string}>;page:number;page_size:number;total:number}>(`/api/stories?page=${page}&page_size=${pageSize}`),
  trends: (topK=6, recentDays?: number, previousDays?: number) => {
    const params = new URLSearchParams({top_k: String(topK)});
    if (recentDays !== undefined) params.set("recent_days", String(recentDays));
    if (previousDays !== undefined) params.set("previous_days", String(previousDays));
    return request<{trends:Trend[]}>(`/api/trends?${params.toString()}`);
  },
  search: (query:string, topK=10) => request<{query:string;results:SearchResult[]}>(`/api/search?q=${encodeURIComponent(query)}&top_k=${topK}`),
  ask: (query:string, topK=8) => request<AskResponse>("/api/ask",{method:"POST",body:JSON.stringify({query,top_k:topK})}),
  personalized: (query:string, userId="default", topK=10) => request<{user_id:string;items:RankedItem[]}>(`/api/personalized?q=${encodeURIComponent(query)}&user_id=${encodeURIComponent(userId)}&top_k=${topK}`),
};
