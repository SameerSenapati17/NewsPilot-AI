import type React from "react";
import {SkeletonCards} from "./Intelligence";
export function Loading(){return <SkeletonCards/>}
export function ErrorState({message,onRetry}:{message:string;onRetry?:()=>void}){return <div className="state-card error" role="alert"><strong>Something went wrong</strong><span>{message}</span>{onRetry&&<button className="button secondary" onClick={onRetry}>Retry</button>}</div>}
export function Empty({children}:{children:React.ReactNode}){return <div className="state-card empty"><strong>No emerging intelligence yet</strong><span>{children}</span></div>}
