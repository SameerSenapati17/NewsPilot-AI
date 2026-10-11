import type {NewsItem, RankedItem, Trend} from "../lib/api";

export function relativeTime(value?: string) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  if (minutes < 2880) return "Yesterday";
  return date.toLocaleDateString(undefined, {month: "short", day: "numeric"});
}

export function SkeletonCards({count = 3}: {count?: number}) {
  return <div className="skeleton-list" aria-label="Loading intelligence" aria-live="polite">
    {Array.from({length: count}, (_, index) => <div className="skeleton-card" key={index}><i/><i/><i/></div>)}
  </div>;
}

export function IntelligenceTicker({items}: {items: NewsItem[]}) {
  const labels = items.slice(0, 6).map(item => item.title);
  if (!labels.length) return null;
  return <div className="ticker" aria-label="Intelligence pulse">
    <span className="ticker-label">Intelligence pulse</span>
    <div className="ticker-viewport"><div className="ticker-track">{labels.map((label, index) => <span key={`${label}-${index}`}>● {label}</span>)}</div></div>
  </div>;
}

export function MetricStrip({news, trends}: {news: NewsItem[]; trends: Trend[]}) {
  const sources = new Set(news.map(item => item.source).filter(Boolean)).size;
  const latest = news[0]?.published_at;
  const topDomain = trends[0]?.topic;
  return <div className="metric-strip">
    <div><strong>{news.length}</strong><span>Stories loaded</span></div>
    <div><strong>{sources || "—"}</strong><span>Sources</span></div>
    <div><strong>{latest ? relativeTime(latest) : "—"}</strong><span>Latest update</span></div>
    <div><strong>{topDomain || "—"}</strong><span>Top signal</span></div>
  </div>;
}

export function StoryCard({item, compact = false}: {item: NewsItem; compact?: boolean}) {
  return <article className={`story-card${compact ? " compact" : ""}`}>
    <div className="story-kicker">{item.source}{relativeTime(item.published_at) === "Just now" ? <b>NEW</b> : null}</div>
    <h3><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a></h3>
    {!compact && item.description && <p>{item.description}</p>}
    <div className="story-meta">{item.source} · {relativeTime(item.published_at)}</div>
  </article>;
}

export function RankedCard({item}: {item: RankedItem}) {
  return <article className="story-card compact">
    <div className="story-kicker">Recommended</div>
    <h3>{item.title}</h3>
    <div className="score-line"><span>Match score</span><strong>{Math.round(item.final_score * 100)}%</strong></div>
    {item.explanation?.reasons?.length ? <p>{item.explanation.reasons[0]}</p> : null}
  </article>;
}

export function TrendCard({trend}: {trend: Trend}) {
  const recent = Number(trend.metrics.recent_content_count || 0);
  const stories = Number(trend.metrics.recent_story_count || 0);
  const sources = Number(trend.metrics.recent_source_count || 0);
  return <article className="trend-card">
    <div className="trend-title"><strong>{trend.topic}</strong>{trend.is_emerging && <span className="badge">↑ Emerging</span>}</div>
    <div className="trend-bar"><i style={{width: `${Math.min(100, Math.max(8, trend.score * 100))}%`}}/></div>
    <div className="metric-row"><span>Activity <b>{Math.round(trend.score * 100)}%</b></span><span>Stories <b>{stories || recent}</b></span><span>Sources <b>{sources}</b></span></div>
    {trend.explanation && <p className="reason">{trend.explanation}</p>}
  </article>;
}
