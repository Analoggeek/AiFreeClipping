#!/usr/bin/env python3
"""Real-browser website acceptance. Optional dev dependency: playwright + Chromium."""
from __future__ import annotations
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading


ROOT=Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*_):pass


def main():
    from playwright.sync_api import sync_playwright
    handler=functools.partial(QuietHandler,directory=str(ROOT/'docs'))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    checks=[]
    def check(name,result):
        assert result,name
        checks.append(name);print('PASS',name)
    try:
        with sync_playwright() as playwright:
            options=dict(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            if os.environ.get('CHROMIUM_EXECUTABLE'):options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=playwright.chromium.launch(**options)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page();errors=[];remote=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:remote.append(request.url) if not request.url.startswith(url) else None)
            page.goto(url,wait_until='networkidle')
            check('Product identity','Ai clipping PRO' in page.title())
            check('Desktop menu hidden',not page.locator('.menu-button').is_visible())
            check('All seven current downloads',page.locator('[data-asset]').count()==7)
            page.get_by_role('tab',name='02 Caption Studio').click()
            check('Screenshot tab selection',page.locator('#panel-captions').is_visible() and not page.locator('#panel-home').is_visible())
            page.get_by_role('tab',name='02 Caption Studio').press('ArrowLeft')
            check('Keyboard tab selection',page.locator('#panel-home').is_visible())
            page.get_by_role('tab',name='03 Multitrack editor').click()
            check('Real multitrack capture',page.locator('#panel-editor').is_visible())
            for platform,count in [('Windows',1),('macOS',2),('Linux',1),('All platforms',4)]:
                page.get_by_role('button',name=platform,exact=True).click()
                check(platform+' download filter',page.locator('.download-card:visible').count()==count)
            page.get_by_text('How do I install or upgrade?',exact=True).click()
            check('FAQ disclosure',page.locator('#install-command').is_visible())
            # Reject clipboard access to prove the truthful fallback is usable.
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('denied'))},configurable:true})")
            page.locator('#copy-command').click()
            check('Clipboard denied fallback','Clipboard unavailable' in page.locator('#copy-status').inner_text())
            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.resolve()},configurable:true})")
            page.locator('#copy-command').click()
            check('Clipboard success feedback',page.locator('#copy-status').inner_text()=='Install command copied.')
            page.locator('#motion-toggle').click()
            check('Reduced motion control',page.locator('body').evaluate("el=>el.classList.contains('reduce-motion')"))
            page.reload()
            check('Motion preference persists',page.locator('#motion-toggle').get_attribute('aria-pressed')=='true')
            for width in (320,390,768,1440,1920):
                page.set_viewport_size({'width':width,'height':900})
                check(f'No horizontal overflow at {width}px',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('button',name='Menu').click()
            check('Mobile menu opens',page.locator('.menu-button').get_attribute('aria-expanded')=='true')
            page.keyboard.press('Escape')
            check('Mobile Escape closes menu',page.locator('.menu-button').get_attribute('aria-expanded')=='false')
            page.get_by_role('button',name='Menu').click();page.locator('#nav-links a[href="#features"]').click()
            check('Mobile navigation closes after selection',page.locator('.menu-button').get_attribute('aria-expanded')=='false')
            check('No JavaScript errors',not errors)
            check('No third-party runtime requests',not remote)
            if os.environ.get('AXE_SCRIPT'):
                page.add_script_tag(path=os.environ['AXE_SCRIPT'])
                result=page.evaluate("async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})")
                violations=[(v['id'],[n['target'] for n in v['nodes']]) for v in result['violations']]
                check('Automated WCAG A/AA rules: '+str(violations),not violations)
            output=ROOT/'artifacts'/'website';output.mkdir(parents=True,exist_ok=True)
            page.set_viewport_size({'width':1440,'height':1000});page.goto(url,wait_until='networkidle')
            page.screenshot(path=str(output/'desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'mobile.png'),full_page=True)
            context.close()
            fallback=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
            page=fallback.new_page();page.goto(url,wait_until='networkidle')
            check('No-JS all direct downloads remain',page.locator('[data-asset]:visible').count()==7)
            check('No-JS all screenshots visible',page.locator('.studio-panel:visible').count()==3)
            check('No-JS dead enhancement buttons hidden',not page.locator('.menu-button').is_visible() and not page.locator('.download-filter').is_visible() and not page.locator('[role="tablist"]').is_visible())
            check('No-JS mobile navigation remains',page.locator('#nav-links a[href="#download"]').is_visible())
            fallback.close()
            reduced=browser.new_context(reduced_motion='reduce')
            page=reduced.new_page();page.goto(url)
            check('OS reduced motion respected',page.locator('#motion-toggle').get_attribute('aria-pressed')=='true')
            reduced.close();browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
    print(f'\n{len(checks)} browser checks passed')


if __name__=='__main__':main()
