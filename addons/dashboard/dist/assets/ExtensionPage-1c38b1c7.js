import{x as _,o as s,c as l,w as t,a as e,$ as f,b as r,a0 as h,e as i,t as d,G as g,d as m,A as V,O as v,a1 as x,S as k,D as p,s as C,F as w,u as S,f as y,j as b,V as B}from"./index-96c19dfb.js";const P={class:"d-sm-flex align-center justify-space-between"},$=_({__name:"ExtensionCard",props:{title:String,link:String},setup(u){const n=u,c=o=>{window.open(o,"_blank")};return(o,a)=>(s(),l(k,{variant:"outlined",elevation:"0",class:"withbg"},{default:t(()=>[e(f,{style:{padding:"10px 20px"}},{default:t(()=>[r("div",P,[e(h,null,{default:t(()=>[i(d(n.title),1)]),_:1}),e(g),e(m,{icon:"mdi-link",variant:"plain",onClick:a[0]||(a[0]=E=>c(n.link))})])]),_:1}),e(V),e(v,null,{default:t(()=>[x(o.$slots,"default")]),_:3})]),_:3}))}}),G={style:{"min-height":"180px","max-height":"180px",overflow:"hidden"}},N={class:"d-flex align-center gap-3"},D=`
{
    "data": [
        {
            "name": "GoodPlugins",
            "repo": "https://gitee.com/soulter/goodplugins",
            "author": "soulter",
            "desc": "一些好用的插件，一些好用的插件，一些好用的插件。一些好用的插件。一些好用的插件，一些好用的插件。一些好用的插件，一些好用的插件。一些好用的插件，一些好用的插件，一些好用的插件。一些好用的插件。一些好用的插件，一些好用的插件。一些好用的插件，一些好用的插件",
            "version": "1.0"
        },
        {
            "name": "GoodPlugins",
            "repo": "https://gitee.com/soulter/goodplugins",
            "author": "soulter",
            "desc": "一些好用的插件",
            "version": "1.0"
        },
        {
            "name": "GoodPlugins",
            "repo": "https://gitee.com/soulter/goodplugins",
            "author": "soulter",
            "desc": "一些好用的插件",
            "version": "1.0"
        }
    ]
}`,j=_({__name:"ExtensionPage",setup(u){p({title:"Sample Page"});const n=p(JSON.parse(D));return(c,o)=>(s(),l(B,null,{default:t(()=>[(s(!0),C(w,null,S(n.value.data,a=>(s(),l(y,{cols:"12",md:"6",lg:"4"},{default:t(()=>[(s(),l($,{key:a.name,title:a.name,link:a.repo,style:{"margin-bottom":"16px"}},{default:t(()=>[r("p",G,d(a.desc),1),r("div",N,[e(b,null,{default:t(()=>[i("mdi-account")]),_:1}),r("span",null,d(a.author),1),e(g),e(m,{variant:"plain"},{default:t(()=>[i("安 装")]),_:1})])]),_:2},1032,["title","link"]))]),_:2},1024))),256))]),_:1}))}});export{j as default};
