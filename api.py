from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from concurrent.futures import ProcessPoolExecutor, TimeoutError
import tempfile, shutil, time, json, asyncio, uuid
from typing import Dict, Any, List, Optional
import undetected_chromedriver as uc

app = FastAPI()
pool = ProcessPoolExecutor(max_workers=4)
JOBS: Dict[str, Dict[str, Any]] = {}

def now_ms():
    return int(time.time() * 1000)

class VerifyReq(BaseModel):
    lastName: str = Field(min_length=1, max_length=50)
    ssn:      str = Field(pattern=r'^\d{9}$')
    dob:      str = Field(pattern=r'^\d{2}/\d{2}/\d{4}$')

class DynamicAction(BaseModel):
    kind:         str = Field(default="typeSlow")
    selector:     Optional[str] = None
    value:        Optional[str] = None
    waitSelector: Optional[str] = None
    script:       Optional[str] = None
    args:         Optional[List[Any]] = None

class DynamicStep(BaseModel):
    waitUrlContains:  Optional[str] = None
    actions:          List[DynamicAction] = Field(default_factory=list)

class DynamicVerifyReq(BaseModel):
    startUrl:  Optional[str] = None
    steps:     List[DynamicStep] = Field(default_factory=list)

def run_verification(last_name, ssn, dob):
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    user_data = tempfile.mkdtemp(prefix="cap1-")
    options.add_argument(f"--user-data-dir={user_data}")
    driver = None
    try:
        driver = uc.Chrome(options=options)
        driver.execute_cdp_cmd("Page.bringToFront", {})
        driver.get("https://verified.capitalone.com/")

        def wait_for_url_contains(sub, timeout=30):
            end = time.time() + timeout
            while time.time() < end:
                if sub in driver.current_url:
                    return True
                time.sleep(0.05)
            return True

        def wait_for_element_visible(selector, timeout=15):
            end = time.time() + timeout
            while time.time() < end:
                el = driver.execute_script("return document.querySelector(arguments[0]);", selector)
                if el:
                    vis = driver.execute_script("""
                        var el=arguments[0];var s=getComputedStyle(el);
                        if(s.visibility==='hidden'||s.display==='none'||parseFloat(s.opacity)===0) return false;
                        var r=el.getBoundingClientRect(); return r.width>0 && r.height>0;
                    """, el)
                    if vis:
                        return el
                time.sleep(0.05)
            return None

        type_slow = """
var selector = arguments[0];
var text = arguments[1];
function sleep(ms){ var end = Date.now()+ms; while(Date.now()<end){} }
var el = document.querySelector(selector);
if (!el) return false;
try { el.focus(); el.click(); } catch(e) {}
var cur = el.value || '';
for (var i=0;i<cur.length;i++){
  el.dispatchEvent(new KeyboardEvent('keydown',{key:'Backspace',bubbles:true}));
  el.value = el.value.slice(0,-1);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:'Backspace',bubbles:true}));
  sleep(20);
}
for (var j=0;j<text.length;j++){
  var ch = text[j];
  el.dispatchEvent(new KeyboardEvent('keydown',{key:ch,bubbles:true}));
  el.value = (el.value || '') + ch;
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:ch,bubbles:true}));
  sleep(60);
}
el.dispatchEvent(new Event('change',{bubbles:true}));
try { el.blur(); } catch(e) {}
return true;
"""

        wait_for_url_contains("auth/signin")
        btn = wait_for_element_visible('button[data-testtarget="linkToForgots"]')
        if btn:
            driver.execute_script("arguments[0].click();", btn)
        wait_for_url_contains("sign-in-help/pii?client=SIC")

        driver.execute_script(type_slow, "#lastname", last_name)
        driver.execute_script(type_slow, "#dob", dob)

        def cdp_click(selector):
            rect = driver.execute_script("""
var el=document.querySelector(arguments[0]);
if(!el){return null;}
var r=el.getBoundingClientRect();
return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
""", selector)
            if rect:
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rect["x"], "y": rect["y"]})
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "left", "x": rect["x"], "y": rect["y"], "clickCount": 1})
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "left", "x": rect["x"], "y": rect["y"], "clickCount": 1})

        def cdp_type(text, key_delay=0.01, clear_delay=0.02):
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace"})
            time.sleep(clear_delay)
            for ch in text:
                vk = ord(ch)
                driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch, "unmodifiedText": ch, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})
                driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "text": ch, "unmodifiedText": ch, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})
                time.sleep(key_delay)

        cdp_click("#fullSSN")
        cdp_type(ssn)

        driver.execute_cdp_cmd("Network.enable", {})
        submit_btn = wait_for_element_visible('button[data-testtarget="pii-form-submit-btn"]')
        if submit_btn:
            cdp_click('button[data-testtarget="pii-form-submit-btn"]')

        req_id = None
        headers = {}
        post_data = None
        end = time.time() + 15
        while time.time() < end:
            for e in driver.get_log("performance"):
                try:
                    m = json.loads(e["message"])["message"]
                    method = m.get("method")
                    p = m.get("params", {})
                    if method == "Network.requestWillBeSent":
                        r = p.get("request", {})
                        u = r.get("url", "")
                        mth = r.get("method", "")
                        if "customer-verification" in u and mth == "POST":
                            req_id = p.get("requestId")
                            headers.update(r.get("headers", {}))
                            if "postData" in r:
                                post_data = r["postData"]
                    elif method == "Network.requestWillBeSentExtraInfo":
                        if p.get("requestId") == req_id:
                            headers.update(p.get("headers", {}))
                except Exception:
                    pass
            if req_id and post_data is not None:
                break
            time.sleep(0.05)
            
        if req_id and post_data is None:
            try:
                pd = driver.execute_cdp_cmd("Network.getRequestPostData", {"requestId": req_id})
                post_data = pd.get("postData")
            except Exception:
                pass

        payload = json.loads(post_data) if isinstance(post_data, str) else post_data
        slp_map = {}
        for k, v in headers.items():
            lk = k.lower()
            if lk.startswith("x-slpf3jx2"):
                suffix = lk[len("x-slpf3jx2"):]
                if suffix and not suffix.startswith("-"):
                    suffix = "-" + suffix
                norm_key = "X-slpF3Jx2" + suffix
                slp_map[norm_key] = v

        slp_items = [{"key": k, "value": v} for k, v in slp_map.items()]
        ppi = payload.get("personalIdentifiableInfo") if isinstance(payload, dict) else None
        return {"x-slpF3Jx2": slp_items, "personalIdentifiableInfo": ppi}
    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass
        shutil.rmtree(user_data, ignore_errors=True)

def run_dynamic_verification(payload: Dict[str, Any]):
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    user_data = tempfile.mkdtemp(prefix="cap1-")
    options.add_argument(f"--user-data-dir={user_data}")
    driver = None
    try:
        driver = uc.Chrome(options=options)
        driver.execute_cdp_cmd("Page.bringToFront", {})
        start_url = payload.get("startUrl") or "https://verified.capitalone.com/" # default to capitalone's verified subdomain (publicly known system with Shape Security implemented for demonstration.)
        driver.get(start_url)

        def wait_for_url_contains(sub, timeout=30):
            end = time.time() + timeout
            while time.time() < end:
                if sub in driver.current_url:
                    return True
                time.sleep(0.05)
            return True

        def wait_for_element_visible(selector, timeout=15):
            end = time.time() + timeout
            while time.time() < end:
                el = driver.execute_script("return document.querySelector(arguments[0]);", selector)
                if el:
                    vis = driver.execute_script("""
                        var el=arguments[0];var s=getComputedStyle(el);
                        if(s.visibility==='hidden'||s.display==='none'||parseFloat(s.opacity)===0) return false;
                        var r=el.getBoundingClientRect(); return r.width>0 && r.height>0;
                    """, el)
                    if vis:
                        return el
                time.sleep(0.05)
            return None

        type_slow = """
var selector = arguments[0];
var text = arguments[1];
function sleep(ms){ var end = Date.now()+ms; while(Date.now()<end){} }
var el = document.querySelector(selector);
if (!el) return false;
try { el.focus(); el.click(); } catch(e) {}
var cur = el.value || '';
for (var i=0;i<cur.length;i++){
  el.dispatchEvent(new KeyboardEvent('keydown',{key:'Backspace',bubbles:true}));
  el.value = el.value.slice(0,-1);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:'Backspace',bubbles:true}));
  sleep(20);
}
for (var j=0;j<text.length;j++){
  var ch = text[j];
  el.dispatchEvent(new KeyboardEvent('keydown',{key:ch,bubbles:true}));
  el.value = (el.value || '') + ch;
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:ch,bubbles:true}));
  sleep(60);
}
el.dispatchEvent(new Event('change',{bubbles:true}));
try { el.blur(); } catch(e) {}
return true;
"""

        def cdp_click(selector):
            rect = driver.execute_script("""
var el=document.querySelector(arguments[0]);
if(!el){return null;}
var r=el.getBoundingClientRect();
return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
""", selector)
            if rect:
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": rect["x"], "y": rect["y"]})
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "left", "x": rect["x"], "y": rect["y"], "clickCount": 1})
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "left", "x": rect["x"], "y": rect["y"], "clickCount": 1})

        def cdp_type(text, key_delay=0.01, clear_delay=0.02):
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace"})
            driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace"})
            time.sleep(clear_delay)
            for ch in text or "":
                vk = ord(ch)
                driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": ch, "text": ch, "unmodifiedText": ch, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})
                driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch, "text": ch, "unmodifiedText": ch, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})
                time.sleep(key_delay)

        steps = payload.get("steps") or []
        for step in steps:
            sub = step.get("waitUrlContains")
            if isinstance(sub, str) and sub:
                wait_for_url_contains(sub)
            actions = step.get("actions") or []
            for a in actions:
                kind = (a.get("kind") or "typeSlow").lower()
                wsel = a.get("waitSelector")
                if isinstance(wsel, str) and wsel:
                    wait_for_element_visible(wsel)
                if kind == "typeslow":
                    sel = a.get("selector")
                    val = a.get("value")
                    if isinstance(sel, str) and sel is not None and val is not None:
                        driver.execute_script(type_slow, sel, str(val))
                elif kind == "click":
                    sel = a.get("selector")
                    if isinstance(sel, str) and sel:
                        cdp_click(sel)
                elif kind == "cdptype":
                    val = a.get("value")
                    if val is not None:
                        cdp_type(str(val))
                elif kind == "script":
                    scr = a.get("script")
                    args = a.get("args") or []
                    if isinstance(scr, str) and scr:
                        driver.execute_script(scr, *args)

        driver.execute_cdp_cmd("Network.enable", {})
        req_id = None
        headers = {}
        post_data = None
        end = time.time() + 15
        while time.time() < end:
            for e in driver.get_log("performance"):
                try:
                    m = json.loads(e["message"])["message"]
                    method = m.get("method")
                    p = m.get("params", {})
                    if method == "Network.requestWillBeSent":
                        r = p.get("request", {})
                        u = r.get("url", "")
                        mth = r.get("method", "")
                        if "customer-verification" in u and mth == "POST":
                            req_id = p.get("requestId")
                            headers.update(r.get("headers", {}))
                            if "postData" in r:
                                post_data = r["postData"]
                    elif method == "Network.requestWillBeSentExtraInfo":
                        if p.get("requestId") == req_id:
                            headers.update(p.get("headers", {}))
                except Exception:
                    pass
            if req_id and post_data is not None:
                break
            time.sleep(0.05)

        if req_id and post_data is None:
            try:
                pd = driver.execute_cdp_cmd("Network.getRequestPostData", {"requestId": req_id})
                post_data = pd.get("postData")
            except Exception:
                pass

        payload_out = json.loads(post_data) if isinstance(post_data, str) else post_data
        slp_map = {}
        for k, v in headers.items():
            lk = k.lower()
            if lk.startswith("x-slpf3jx2"):
                suffix = lk[len("x-slpf3jx2"):]
                if suffix and not suffix.startswith("-"):
                    suffix = "-" + suffix
                norm_key = "X-slpF3Jx2" + suffix
                slp_map[norm_key] = v

        slp_items = [{"key": k, "value": v} for k, v in slp_map.items()]
        ppi = payload_out.get("personalIdentifiableInfo") if isinstance(payload_out, dict) else None
        return {"x-slpF3Jx2": slp_items, "personalIdentifiableInfo": ppi}
    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass

        shutil.rmtree(user_data, ignore_errors=True) # probably not safe but oh well.

async def _run_job(job_id: str, req: VerifyReq):
    if job_id not in JOBS:
        return
    JOBS[job_id]["status"] = "running"
    JOBS[job_id]["stats"]["started_at_ms"] = now_ms()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(pool, run_verification, req.lastName, req.ssn, req.dob)
        JOBS[job_id]["data"] = result
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["stats"]["completed_at_ms"] = now_ms()
        JOBS[job_id]["stats"]["duration_ms"] = JOBS[job_id]["stats"]["completed_at_ms"] - JOBS[job_id]["stats"]["started_at_ms"]
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        JOBS[job_id]["stats"]["completed_at_ms"] = now_ms()
        JOBS[job_id]["stats"]["duration_ms"] = JOBS[job_id]["stats"]["completed_at_ms"] - JOBS[job_id]["stats"]["started_at_ms"]

@app.post("/verify") # DOESN'T USE JOBS
def verify(req: DynamicVerifyReq):
    fut = pool.submit(run_dynamic_verification, req.dict())
    try:
        return fut.result(timeout=40)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Timed out")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="internal server error")

@app.post("/jobs/verify")
async def jobs_verify(req: VerifyReq):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"id": job_id, "status": "queued", "stats": {"created_at_ms": now_ms()}, "data": None, "error": None}
    asyncio.create_task(_run_job(job_id, req))
    return {"jobId": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    resp = {"jobId": job["id"], "status": job["status"], "stats": job.get("stats", {})}
    if job["status"] == "completed":
        resp["data"]  = job.get("data")
    if job["status"] == "failed":
        resp["error"] = job.get("error")
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
