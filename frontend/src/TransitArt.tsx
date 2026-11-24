import { useEffect, useRef } from 'react'

// Editorial illustration of a Delhi city bus and India Gate.
export function TransitArt() {
  const ref=useRef<HTMLCanvasElement>(null)
  useEffect(()=>{
    const canvas=ref.current
    if(!canvas) return
    const ctx=canvas.getContext('2d')
    if(!ctx) return
    const draw=()=>{
      const scale=Math.min(devicePixelRatio || 1,3)*Math.max(canvas.clientWidth/580,1)
      canvas.width=580*scale; canvas.height=225*scale
      ctx.setTransform(scale,0,0,scale,0,0)
      const line=(points:number[][], color:string, width=1)=>{
        ctx.beginPath(); points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y))
        ctx.strokeStyle=color; ctx.lineWidth=width; ctx.stroke()
      }
      const rect=(x:number,y:number,w:number,h:number,fill:string,r=0)=>{
        ctx.fillStyle=fill; ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill()
      }
      const circle=(x:number,y:number,r:number,fill:string)=>{
        ctx.fillStyle=fill;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()
      }
      // Contour lines and distant blocks give the skyline depth.
      for(let i=0;i<12;i++) line([[70+i*44,0],[i*44-25,92],[i*44+5,122],[i*44-70,225]],'#4058d0',0.7)
      for(let i=0;i<6;i++) line([[0,15+i*37],[170,35+i*32],[310,5+i*34],[580,26+i*37]],'#4058d0',0.7)
      circle(464,64,38,'#697fee')
      for(let i=0;i<17;i++){
        const h=17+(i*31%53),x=i*36
        rect(x,169-h,29,h,'#415bd2')
        for(let j=0;j<3;j++) rect(x+4+j*8,175-h,3,5,'#6981e5')
      }
      // India Gate, drawn in layered sandstone-blue tones.
      rect(339,66,78,101,'#849beb');rect(333,62,90,7,'#c8d7ff')
      rect(342,53,72,9,'#b4c6ff');rect(349,46,58,7,'#d1dfff')
      rect(355,40,46,6,'#a8bcf4');rect(349,74,58,10,'#a1b6fa')
      ctx.fillStyle='#3b53cc';ctx.beginPath();ctx.moveTo(364,168);ctx.lineTo(364,117)
      ctx.bezierCurveTo(364,89,393,89,393,117);ctx.lineTo(393,168);ctx.fill()
      for(const x of [342,350,402,410])rect(x,89,2,75,'#b8cafe')
      rect(336,164,84,6,'#a1b7f3')
      for(const x of [35,69,447,486,527]){
        rect(x,145,3,27,'#688e94');circle(x+1,139,12,'#526bd4');circle(x-6,145,9,'#5773d8');circle(x+8,145,10,'#667ee0')
      }
      line([[0,172],[580,172]],'#7287dc',1)
      rect(0,178,580,2,'#6b81dd');rect(157,195,267,5,'#253bb1',3)
      // Front-facing flank and long glazed passenger cabin.
      rect(84,94,254,90,'#253478',12);rect(81,91,254,88,'#f4f6ff',10)
      rect(84,94,249,5,'#ffffff',3);rect(87,101,241,47,'#22366c',5)
      for(let i=0;i<7;i++){
        const x=91+25*i; rect(x,107,22,31,'#5077a8',2)
        line([[x+4,135],[x+16,110]],'#80a5d4',2)
      }
      rect(268,105,18,61,'#1a3d51',2);rect(271,109,5,40,'#548599');rect(279,109,5,40,'#548599')
      rect(292,106,32,32,'#365d74',3);line([[295,133],[311,108]],'#577d93',3)
      rect(86,150,177,3,'#bbcbff');rect(86,156,151,3,'#4c72e8')
      rect(300,149,23,4,'#d9eeeb',2);rect(84,166,182,7,'#7196f9')
      rect(291,167,39,5,'#6184df');rect(315,158,12,5,'#ffe2a0',2)
      rect(83,157,5,8,'#ed9e72',1);rect(304,173,13,4,'#f2cf82',1)
      for(const x of [126,286]){circle(x,177,15,'#132b40');circle(x,177,8,'#7196a6');circle(x,177,4,'#314f66')}
      line([[42,199],[136,199]],'#59768a');line([[302,204],[475,204]],'#47687a')
    }
    const observer=new ResizeObserver(draw);observer.observe(canvas);draw()
    return ()=>observer.disconnect()
  },[])
  return <canvas className="transit-art" ref={ref} aria-hidden="true"/>
}
