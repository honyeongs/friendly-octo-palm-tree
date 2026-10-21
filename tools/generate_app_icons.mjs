import {readFile,writeFile,mkdir} from "node:fs/promises";
import {fileURLToPath,pathToFileURL} from "node:url";
import {join} from "node:path";
const {chromium} = process.env.PLAYWRIGHT_MODULE ? await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href) : await import("playwright");
const [pkg,color] = process.argv.slice(2);
if (!["netsec","download_inspector","endpoint_lab"].includes(pkg) || !/^#[0-9a-fA-F]{6}$/.test(color || "")) throw new Error("Usage: node tools/generate_app_icons.mjs <package> <hex-color>");
const root = fileURLToPath(new URL("../",import.meta.url));
const svg = await readFile(join(root,"src",pkg,"web/assets/shield-check.svg"),"utf8");
const directory = join(root,"website/icons");
await mkdir(directory,{recursive:true});
const browser = await chromium.launch({headless:true});
try {
 const page=await browser.newPage(); let icoImage;
 for (const size of [192,256,512]) {
  const encoded=await page.evaluate(async({svg,size,color})=>{
    const source=new DOMParser().parseFromString(svg,"image/svg+xml").documentElement;
    source.setAttribute("stroke","#ffffff");source.setAttribute("style","color:#ffffff");
    source.setAttribute("width","256");source.setAttribute("height","256");
    const image=new Image();image.src="data:image/svg+xml;base64,"+btoa(new XMLSerializer().serializeToString(source));await image.decode();
    const canvas=document.createElement("canvas");canvas.width=canvas.height=size;const ctx=canvas.getContext("2d");
    ctx.fillStyle=color;ctx.fillRect(0,0,size,size);ctx.drawImage(image,size*.24,size*.24,size*.52,size*.52);
    return canvas.toDataURL("image/png").split(",")[1];
  },{svg,size,color});
  const png=Buffer.from(encoded,"base64");await writeFile(join(directory,`app-${size}.png`),png);
  if(size===256) icoImage=png;
 }
 const header=Buffer.alloc(22);header.writeUInt16LE(1,2);header.writeUInt16LE(1,4);
 header.writeUInt16LE(1,10);header.writeUInt16LE(32,12);header.writeUInt32LE(icoImage.length,14);header.writeUInt32LE(22,18);
 await writeFile(join(directory,"app.ico"),Buffer.concat([header,icoImage]));
} finally {await browser.close();}
