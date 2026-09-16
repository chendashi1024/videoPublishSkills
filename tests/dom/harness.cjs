// 只执行本地夹具，禁止加载页面资源或连接浏览器。
const {JSDOM} = require('jsdom');
const readline = require('node:readline');
let window, nodes, nextId, shadows;
function id(node) {
  for (const [key, value] of nodes) if (value === node) return key;
  const key = nextId++; nodes.set(key, node); return key;
}
function tree(node) {
  const value = {nodeId:id(node),nodeName:node.nodeName,nodeValue:node.nodeValue || '',
    attributes: node.attributes ? [...node.attributes].flatMap(a=>[a.name,a.value]) : [],
    children:[...node.childNodes].map(tree)};
  if (shadows.has(node)) value.shadowRoots = [tree(shadows.get(node))];
  return value;
}
function run(request) {
  if (request.op === 'init') {
    window = new JSDOM(request.html, {runScripts:'outside-only'}).window;
    nodes = new Map(); nextId = 1; shadows = new Map();
    const proto = window.HTMLElement.prototype;
    Object.defineProperty(proto, 'innerText', {get(){return this.textContent;}});
    proto.scrollIntoView = function(){};
    proto.getBoundingClientRect = function(){
      const key = id(this), x = key * 120, y = 10;
      let hidden = false;
      for (let el = this; el && el.nodeType === 1; el = el.parentElement) {
        if (el.hidden || el.style.display === 'none') hidden = true;
      }
      const width = hidden ? 0 : +(this.dataset.width || 100);
      const height = hidden ? 0 : +(this.dataset.height || 40);
      return {x,y,width,height,left:x,top:y,right:x+width,bottom:y+height};
    };
    const attach = proto.attachShadow;
    proto.attachShadow = function(options) {const root=attach.call(this,options);shadows.set(this,root);return root;};
    window.eval(request.setup || '');
    tree(window.document);
    return true;
  }
  if (request.op === 'eval') return window.eval(request.expression);
  if (request.op === 'tick') {if(window.tick) window.tick();return true;}
  const p=request.params || {};
  switch (request.method) {
    case 'DOM.getDocument': return {root:tree(window.document)};
    case 'DOM.querySelectorAll': return {nodeIds:[...nodes.get(p.nodeId).querySelectorAll(p.selector)].map(id)};
    case 'DOM.setFileInputFiles': {
      const el=nodes.get(p.nodeId);
      Object.defineProperty(el,'files',{configurable:true,value:p.files.map(f=>new window.File(['fixture'],f,{type:'image/png'}))});
      el.dispatchEvent(new window.Event('change',{bubbles:true}));return {};
    }
    case 'DOM.resolveNode': return {object:{objectId:String(p.nodeId)}};
    case 'DOM.scrollIntoViewIfNeeded': return {};
    case 'Runtime.releaseObject': return {};
    case 'Runtime.callFunctionOn': return {result:{value:window.eval('('+p.functionDeclaration+')').apply(nodes.get(+p.objectId),(p.arguments || []).map(a=>a.value))}};
    case 'Input.dispatchMouseEvent': {
      if(p.type==='mouseReleased') {
        const hits=[...nodes.values()].filter(n=>n.getBoundingClientRect).filter(n=>{
          const r=n.getBoundingClientRect();return r.width>0 && p.x>=r.left && p.x<=r.right && p.y>=r.top && p.y<=r.bottom;
        });
        if(hits.length!==1) throw new Error('夹具点击目标不唯一: '+hits.length);
        hits[0].click();
      }
      return {};
    }
    case 'Input.dispatchKeyEvent': return {};
    default: throw new Error('夹具尚未实现协议: '+request.method);
  }
}
readline.createInterface({input:process.stdin}).on('line',line=>{
  try {process.stdout.write(JSON.stringify({value:run(JSON.parse(line)) ?? null})+'\n');}
  catch(error){process.stdout.write(JSON.stringify({error:String(error.stack)})+'\n');}
});
