import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
const { chromium } = createRequire(process.cwd()+'/frontend/package.json')('playwright')
const base=process.env.EVALUATION_BASE_URL || 'http://127.0.0.1:5188'
const out='/tmp/issue475-browser'
await mkdir(out,{recursive:true})
const browser=await chromium.launch({headless:true,channel:'chrome'})
const context=await browser.newContext({viewport:{width:1280,height:1000},reducedMotion:'reduce'})
await context.addInitScript(()=>localStorage.setItem('llm-harness-session',JSON.stringify({marker:'reuse-browser-owner',username:'fixture',expiresAt:Date.now()+3600000})))
const page=await context.newPage()
page.setDefaultTimeout(10000)
const errors=[],calls=[],unknown=[]
page.on('pageerror',e=>errors.push(e.message)); page.on('requestfailed',r=>console.log('REQUEST_FAILED',r.url(),r.failure())); page.on('response',r=>{if(r.status()>=400)console.log('HTTP',r.status(),r.url())})
const paged=items=>({items,total:items.length,limit:20,offset:0,has_more:false})
const evaluation={evaluation_id:'eval-new',created_at:'2026-11-25T00:00:00Z',updated_at:'2026-11-25T00:00:00Z',status:'completed',can_start:false,can_cancel:false,execution_progress:{completed_units:3,total_units:3,percentage:100},strategy_names:['vanilla'],model:'model-a',problem_count:3,spent_usd:0.05,known_cost_usd:0.05,unknown_cost_count:0,budget_status:'unlimited',budget_cap_usd:null,error_message:null,progress:null,reuse_history:true,reused_units:1,new_units:2}
const source={evaluation_id:'old-eval',run_id:'web-evaluation-old',result_id:'old-unit'}
let previewFailure=false
await context.route('**/api/v1/**',async route=>{
 const request=route.request(),method=request.method(),path=new URL(request.url()).pathname.replace('/api/v1','')
 calls.push({path,method})
 const headers={'access-control-allow-origin':base,'access-control-allow-credentials':'true','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,x-csrf-token'}
 const send=(data,status=200)=>route.fulfill({status,headers,json:{success:true,data,message:'fixture'}})
 if(method==='OPTIONS')return route.fulfill({status:204,headers})
 if(path==='/users/me')return send({username:'fixture',email:'fixture@example.org',role:'user'})
 if(path==='/notifications')return send({...paged([]),unread_count:0})
 if(path==='/api-keys')return send([{id:'key-a',key_name:'offline',provider:'openai',created_at:1795564800,last_used_at:null,verified:true,usage_count:0,masked_preview:null}])
 if(path==='/evaluation-options')return send({strategies:[{name:'vanilla'}],sources:[{id:'shared',label:'共享题库',problem_count:3}]})
 if(path==='/evaluation-options/models')return send({provider:'openai',models:['model-a'],complete:true})
 if(path==='/evaluation-options/problems')return send(paged(['p1','p2','p3'].map(problem_id=>({problem_id,title:'Problem '+problem_id,difficulty:'easy',source:'shared'}))))
 if(path==='/evaluations/reuse-preview'){
   if(previewFailure)return send(null,503)
   const body=request.postDataJSON(),total=body.problem_ids.length*body.strategy_names.length,reused=body.problem_ids.includes('p1')?1:0
   return send({total_units:total,reused_units:reused,new_units:total-reused,units:body.problem_ids.map(problem_id=>({problem_id,strategy:'vanilla',reason:problem_id==='p1'?'compatible_history':'no_compatible_history',...(problem_id==='p1'?{source}:{})}))})
 }
 if(path==='/evaluations'&&method==='POST'){
   assert.equal(request.postDataJSON().reuse_history,true)
   return send(evaluation,201)
 }
 if(path==='/evaluations/eval-new'||path==='/evaluations/eval-new/start')return send(evaluation)
 if(path==='/results/eval-new')return send({run_id:'web-evaluation-new',status:'completed',created_at:evaluation.created_at,completed_at:evaluation.updated_at,reuse:{total_units:3,reused_units:1,new_units:2,new_cost_usd:0.05,new_cost_unknown_count:0},strategies:[{name:'vanilla',success_rate:1,total_problems:3,solved_problems:3,avg_tokens:10,estimated_cost_usd:0.35,unknown_cost_count:0,avg_execution_time:1,by_difficulty:{easy:{success_rate:1,solved:3,total:3}}}],problems:paged(['p1','p2','p3'].map(problem_id=>({problem_id,strategy:'vanilla',status:'success',iterations:1,tokens:10,execution_time:1,reused:problem_id==='p1',reuse_source:problem_id==='p1'?source:null,original_cost_usd:problem_id==='p1'?0.3:0.025,new_cost_usd:problem_id==='p1'?0:0.025})))})
 if(path==='/evaluations'||path==='/results')return send(paged([]))
 if(path==='/results/eval-new/publication')return send({revision:0,published_revision:null,status:'unavailable',available:false,complete:false,recorded_units:3,expected_units:3,attempts:0,error_code:'not_published',retryable:true,updated_at:null})
 unknown.push(path)
 return send(null,404)
})
try{
 await page.goto(base+'/evaluations/new')
 const reuse=page.getByRole('checkbox',{name:'复用历史结果',exact:true})
 await reuse.waitFor()
 assert.equal(await reuse.isChecked(),false)
 await page.getByLabel('API 密钥',{exact:true}).click()
 await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({hasText:'offline · openai'}).click()
 await page.getByLabel('模型',{exact:true}).click()
 await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({hasText:'model-a'}).click()
 await page.getByLabel('策略',{exact:true}).click()
 await page.locator('.ant-select-dropdown:visible .ant-select-item-option').filter({hasText:'vanilla'}).click()
 await page.getByRole('heading',{name:'创建评估',exact:true}).click()
 await page.getByRole('checkbox',{name:'全选当前页',exact:true}).check()
 await reuse.check()
 await page.getByText('预计复用 1，新跑 2，共 3 个单元',{exact:true}).waitFor()
 await page.screenshot({path:out+'/create-desktop.png',fullPage:true})
 previewFailure=true
 await page.getByRole('checkbox',{name:'选择题目 p3',exact:true}).uncheck()
 await page.getByText('复用预览失败，请重试或关闭复用。',{exact:true}).waitFor()
 assert.equal(await page.getByRole('button',{name:'创建并启动',exact:true}).isEnabled(),false)
 previewFailure=false
 console.log('BUTTONS',await page.locator('button').allTextContents()); console.log('ALERTS',await page.getByRole('alert').allTextContents()); await page.getByRole('button',{name:/重\s*试/}).click()
 await page.getByText('预计复用 1，新跑 1，共 2 个单元',{exact:true}).waitFor()
 await page.getByRole('checkbox',{name:'选择题目 p3',exact:true}).check()
 await page.getByText('预计复用 1，新跑 2，共 3 个单元',{exact:true}).waitFor()
 await page.getByRole('button',{name:'创建并启动',exact:true}).click()
 await page.waitForURL('**/evaluations/eval-new')
 await page.getByText('复用 / 新跑单元',{exact:true}).waitFor()
 await page.goto(base+'/results/eval-new')
 await page.getByText('复用 1，新跑 2，共 3 个单元',{exact:true}).waitFor()
 await page.getByRole('link',{name:'web-evaluation-old',exact:true}).waitFor(); assert.equal(await page.getByRole('cell',{name:'通过',exact:true}).count(),3)
 assert.equal(await page.getByRole('link',{name:'web-evaluation-old',exact:true}).getAttribute('href'),'/results/old-eval')
 for(const width of [1280,390,320]){
   await page.setViewportSize({width,height:1000})
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,`overflow at ${width}`)
   await page.screenshot({path:out+`/results-${width}.png`,fullPage:true})
 }
 assert.deepEqual(errors,[])
 await writeFile(out+'/report.json',JSON.stringify({passed:true,checks:['default off','preview counts','preview failure blocks submit','retry','changed selection refresh','create carries reuse flag','final submitted counts','source link','original/new cost separation','320/390/1280px layout'],calls,unknown,pageErrors:errors},null,2))
 console.log('Browser reuse workflow and responsive checks passed; '+out+'/report.json')
}catch(error){await page.screenshot({path:out+'/failure.png',fullPage:true}); await writeFile(out+'/failure.txt',await page.locator('body').innerText()); console.log('PAGE_ERRORS',errors); throw error}finally{await browser.close()}
