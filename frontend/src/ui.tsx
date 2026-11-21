import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { AlertCircle, LoaderCircle, SearchX } from 'lucide-react'

export function Card({children, className=''}: {children:ReactNode;className?:string}) {
  return <section className={'card '+className}>{children}</section>
}
export function Badge({children}: {children:ReactNode}) { return <span className="badge">{children}</span> }
export function Button(props: ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...props} className={'btn '+(props.className || '')}/> }
export function Field({id,label,children}: {id:string;label:string;children:ReactNode}) {
  return <div className="field"><label htmlFor={id}>{label}</label>{children}</div>
}
export function State({kind,children,retry}: {kind:'loading'|'empty'|'error';children:ReactNode;retry?:()=>void}) {
  const Icon = kind==='loading'?LoaderCircle:kind==='error'?AlertCircle:SearchX
  return <div role={kind==='error'?'alert':'status'} className={'state '+kind}><Icon size={18}/><span>{children}</span>{retry && <button type="button" onClick={retry}>Retry</button>}</div>
}
type RequestState<T> = {kind:'loading'} | {kind:'error';message:string} | {kind:'ready';data:T}
export function useRequest<T>(request: (signal:AbortSignal)=>Promise<T>) {
  const [attempt,setAttempt]=useState(0)
  const [state,setState]=useState<RequestState<T>>({kind:'loading'})
  useEffect(()=>{
    const controller=new AbortController()
    setState({kind:'loading'})
    request(controller.signal).then(data=>{
      if(!controller.signal.aborted) setState({kind:'ready',data})
    }).catch(error=>{
      if(!controller.signal.aborted) setState({kind:'error',message:error instanceof TypeError?'Could not connect to the transit service.':String(error.message || error)})
    })
    return ()=>controller.abort()
  },[request,attempt])
  return {state,retry:()=>setAttempt(i=>i+1)}
}

