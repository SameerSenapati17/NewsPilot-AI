"use client";
import type React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [["Dashboard","/"],["Discover","/discover"],["Search","/search"],["Ask AI","/ask"],["Trends","/trends"],["For You","/personalized"]];
export function Shell({children}:{children:React.ReactNode}) {
  const path=usePathname();
  return <div className="app"><aside className="sidebar"><div className="brand">news<span>pilot</span><br/>intelligence</div><nav className="nav" aria-label="Main navigation">{links.map(([label,href])=><Link className={path===href?"active":""} href={href} key={href}><span className="nav-mark">◈</span>{label}</Link>)}</nav></aside><main className="main"><div className="topbar"><div className="eyebrow">Intelligence workspace</div><div className="status"><i className="dot"/> API connected</div></div>{children}</main></div>;
}
