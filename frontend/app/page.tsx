"use client";
import {useEffect,useState} from "react";
import {api,NewsItem,RankedItem,Trend} from "../lib/api";
import {ErrorState,Empty} from "../components/States";
import {IntelligenceTicker,MetricStrip,RankedCard,StoryCard,TrendCard,SkeletonCards} from "../components/Intelligence";

export default function Dashboard(){
 const [data,setData]=useState<{trends:Trend[];ranked:RankedItem[];news:NewsItem[]}|null>(null),[error,setError]=useState("");
 const [today]=useState(()=>new Date());
 useEffect(()=>{Promise.all([api.trends(),api.personalized("latest AI developments", "default", 3),api.news(1,100)]).then(([t,p,n])=>setData({trends:t.trends,ranked:p.items,news:n.items})).catch(e=>setError("We couldn't load this intelligence feed."))},[]);
 const dateLabel=today.toLocaleDateString(undefined,{weekday:"long"}).toUpperCase();
 return <><section className="hero hero-brief"><div><div className="eyebrow">{dateLabel} · Intelligence brief</div><h1>See what is moving.</h1><p>A concise view of the signals, stories, and questions shaping the AI ecosystem.</p></div><div className="last-updated"><small>Last updated {data?.news[0] ? "from latest story" : "when data arrives"}</small></div></section>
 {error?<ErrorState message={error}/>:!data?<SkeletonCards count={4}/>:<><IntelligenceTicker items={data.news}/><MetricStrip news={data.news} trends={data.trends}/><div className="dashboard-grid">
   <section className="panel span-8"><div className="panel-head"><h2>What&apos;s moving</h2><a className="link" href="/discover">View all intelligence →</a></div><div className="story-grid">{data.news.slice(0,3).map(item=><StoryCard item={item} compact key={item.id}/>)}</div></section>
   <section className="panel span-4"><div className="panel-head"><h2>For you</h2><a className="link" href="/personalized">View feed →</a></div>{data.ranked.length?data.ranked.slice(0,3).map(item=><RankedCard item={item} key={item.content_item_id}/>):<Empty>We need more activity to build your feed.</Empty>}</section>
   <section className="panel span-8"><div className="panel-head"><h2>Emerging signals</h2><a className="link" href="/trends">Explore trends →</a></div>{data.trends.length? <div className="trend-grid">{data.trends.slice(0,3).map(t=><TrendCard trend={t} key={t.topic}/>)}</div>:<Empty>There isn&apos;t enough recent activity to identify a meaningful trend.</Empty>}</section>
   <section className="panel span-4 action-panel"><div className="eyebrow">Next investigation</div><h2>Ask the intelligence stream.</h2><p className="muted">Trace a development across the stories in your archive.</p><a className="button" href="/ask">Ask AI <span>→</span></a></section>
 </div></>}</>;
}
