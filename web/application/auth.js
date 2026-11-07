"use strict";
const signUp=location.pathname==="/signup";
const title=document.getElementById("authTitle");
const hint=document.getElementById("authHint");
const inviteField=document.getElementById("inviteField");
const form=document.getElementById("authForm");
const error=document.getElementById("error");
title.textContent=signUp?"Create your account":"Sign in";
document.title=(signUp?"Create account":"Sign in")+" · Refit";
hint.textContent=signUp?"Use a one-time invitation to create an isolated developer workspace.":"Welcome back. Sign in to your Refit workspace.";
inviteField.hidden=!signUp;
document.getElementById("invite").required=signUp;
document.getElementById("password").autocomplete=signUp?"new-password":"current-password";
document.getElementById("switch").innerHTML=signUp?"Already have an account? <a href='/login'>Sign in</a>":"Need an account? <a href='/signup'>Create one with an invitation</a>";
const query=new URLSearchParams(location.search);
const next=query.get("next");
const destination=(next && /^\/app(?:\/|$)/.test(next) && !next.startsWith("//") && !next.includes("\\"))
   ?next:"/app";
if(!signUp){
  fetch("/api/application/session").then(r=>r.json()).then(s=>{
    if(s.mode==="account"&&s.username)location.replace(destination);
  }).catch(()=>{});
}
form.addEventListener("submit",async event=>{
  event.preventDefault();error.textContent="";
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  const body={username:document.getElementById("username").value.trim(),password:document.getElementById("password").value};
  if(signUp)body.invite=document.getElementById("invite").value.trim();
  try{
    const result=await fetch("/api/application/"+(signUp?"register":"login"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const payload=await result.json();
    if(!result.ok)throw Error(payload.error?.message || "Sign-in failed.");
    document.getElementById("password").value="";
    document.getElementById("invite").value="";
    location.replace(destination);
  }catch(e){error.textContent=e.message;}finally{button.disabled=false;}
});