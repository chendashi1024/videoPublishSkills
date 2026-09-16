"""以现场结构复现新版封面和封闭组件，不连接生产网页。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import publish_pipeline as pipeline
from scripts.xiaohongshu.publisher_core import XiaohongshuPublisherCore
from core.ui_automator import UIAutomator
from core.cdp_client import CDPError
from xhs_dom import DomCDP

COVER = '''<button>确定</button><div class="publish-page-content-cover"><div class="default" data-width="75" data-height="100" style="background-image:url(old.jpg)"></div></div>
<section id="editor"><div class="cover-choose-container"><input type="file" accept="image/*" aria-label="上传封面图片"><img id="photo"></div><span id="crop">裁剪</span>
<div id="ratios" hidden><button class="ratio-option">3:4</button><button class="ratio-option active">4:3</button></div><span class="slider-value">100%</span><button id="save">完成</button></section>'''
SETUP = '''window.saves=0; window.uploads=0;
document.querySelector('input').onchange=()=>{window.uploads++;const img=document.querySelector('#photo');Object.defineProperties(img,{naturalWidth:{value:1263},naturalHeight:{value:1684}});};
document.querySelector('#crop').onclick=()=>document.querySelector('#ratios').hidden=false;
for(const button of document.querySelectorAll('.ratio-option')) button.onclick=()=>{for(const b of document.querySelectorAll('.ratio-option'))b.classList.remove('active');button.classList.add('active');};
document.querySelector('#save').onclick=()=>{window.saves++;document.querySelector('#save').disabled=true;window.pending=true;};
window.tick=()=>{if(window.pending && !window.stuck){document.querySelector('#editor').remove();document.querySelector('.default').style.backgroundImage='url(new.jpg)';window.pending=false;}};'''


class XhsDomTest(unittest.TestCase):
    def dom(self, html=COVER, setup=SETUP):
        cdp=DomCDP(html, setup);self.addCleanup(cdp.close);return cdp

    def test_current_editor_confirm_scoped_not_global(self):
        cdp=self.dom()
        actual=pipeline._find_xiaohongshu_cover_confirm_rect(SimpleNamespace(cdp=cdp))
        expected=cdp.evaluate("(()=>{const r=document.querySelector('#save').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
        self.assertEqual(actual, expected)

    def test_current_cover_upload_crop_and_real_save(self):
        cdp=self.dom()
        with patch.object(pipeline.time, 'sleep', side_effect=cdp.sleep):
            pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)
        self.assertEqual(cdp.evaluate('[window.uploads,window.saves]'),[1,1])
        self.assertFalse(cdp.evaluate("!!document.querySelector('#editor')"))
        self.assertIn('new.jpg', cdp.evaluate("document.querySelector('.default').style.backgroundImage"))

    def test_scheduled_shadow_submit_not_draft(self):
        cdp=self.dom('<div class="post-time-wrapper"><input type="checkbox" checked></div><xhs-publish-btn submit-text="定时发布" submit-disabled="false" submit-loading="false"></xhs-publish-btn>', '''
        window.submits=0;window.drafts=0;
        const root=document.querySelector('xhs-publish-btn').attachShadow({mode:'closed'});
        root.innerHTML='<button id="draft">暂存离开</button><button id="submit">定时发布</button>';
        root.querySelector('#submit').onclick=()=>window.submits++;
        root.querySelector('#draft').onclick=()=>window.drafts++;
        ''')
        publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
        publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
        publisher._click_publish()
        self.assertEqual(cdp.evaluate('[window.submits,window.drafts]'),[1,0])


class XhsSafetyDomTest(unittest.TestCase):
    dom = XhsDomTest.dom

    def test_save_pending_keeps_editor_and_does_not_retry(self):
        cdp=self.dom(setup=SETUP+'window.stuck=true;')
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep):
            with self.assertRaisesRegex(Exception,'保存超时'):
                pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0,save_timeout=0)
        self.assertTrue(cdp.evaluate("!!document.querySelector('#editor')"))
        self.assertEqual(cdp.evaluate('[window.uploads,window.saves]'),[1,1])

    def test_missing_cover_entry_fails_instead_of_silent_success(self):
        cdp=self.dom('<main>视频</main>','')
        with self.assertRaisesRegex(Exception,'封面编辑入口未找到'):
            pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)

    def test_bad_ratio_is_not_accepted_by_one_hundred_percent(self):
        cdp=self.dom(setup=SETUP+"document.querySelector('.ratio-option').onclick=()=>{};")
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep):
            with self.assertRaisesRegex(Exception,'3:4'):
                pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)
        self.assertEqual(cdp.evaluate('window.saves'),0)

    def test_crop_tab_with_nested_label(self):
        cdp=self.dom(html=COVER.replace('<span id="crop">裁剪</span>', '<div id="crop"><span>裁剪</span></div>'))
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep):
            pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)
        self.assertEqual(cdp.evaluate('window.saves'),1)

    def test_image_preview_must_change_after_upload(self):
        cdp=self.dom(setup=SETUP+"document.querySelector('input').onchange=()=>{window.uploads++;};Object.defineProperties(document.querySelector('#photo'),{naturalWidth:{value:1263},naturalHeight:{value:1684}});")
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep), patch.object(pipeline.time,'monotonic',side_effect=range(100)):
            with self.assertRaisesRegex(Exception,'原图'):
                pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)
        self.assertEqual(cdp.evaluate('window.saves'),0)

    def test_legacy_confirm_scoped_and_disabled_rejected(self):
        cdp=self.dom('<button>确定</button><div class="cover-modal"><input type="file" accept="image/*"><button id="save">确定</button></div>','')
        publisher=SimpleNamespace(cdp=cdp)
        self.assertIsNotNone(pipeline._find_xiaohongshu_cover_confirm_rect(publisher))
        cdp.evaluate("document.querySelector('#save').disabled=true")
        self.assertIsNone(pipeline._find_xiaohongshu_cover_confirm_rect(publisher))

    def test_legacy_cover_upload_still_works(self):
        html = COVER.replace('<section id="editor">','<section id="editor" class="cover-modal">').replace(' aria-label="上传封面图片"','').replace('ratio-option active','crop-ratio-item crop-ratio-item-active').replace('ratio-option','crop-ratio-item').replace('>完成<','>确定<')
        setup = SETUP.replace('.ratio-option','.crop-ratio-item').replace("'active'","'crop-ratio-item-active'")
        cdp=self.dom(html,setup)
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep):
            pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0)
        self.assertEqual(cdp.evaluate('[window.uploads,window.saves]'),[1,1])

    def test_loading_editor_with_updated_background_is_not_saved(self):
        setup = SETUP + "window.stuck=true;document.querySelector('#save').onclick=()=>{window.saves++;document.querySelector('#save').remove();document.querySelector('.default').style.backgroundImage='url(new.jpg)';};"
        cdp=self.dom(setup=setup)
        with patch.object(pipeline.time,'sleep',side_effect=cdp.sleep):
            with self.assertRaisesRegex(Exception,'保存超时'):
                pipeline._upload_xiaohongshu_video_cover(SimpleNamespace(cdp=cdp),'/fixture/cover.png',0,save_timeout=0)
        self.assertTrue(cdp.evaluate("!!document.querySelector('#editor')"))
        self.assertEqual(cdp.evaluate('window.saves'),1)

    def test_shadow_button_label_changes_before_final_click(self):
        cdp=self.dom('<xhs-publish-btn submit-text="发布" submit-disabled="false" submit-loading="false"></xhs-publish-btn>', "window.submits=0;const root=document.querySelector('xhs-publish-btn').attachShadow({mode:'closed'});root.innerHTML='<button>发布</button>';window.submitButton=root.querySelector('button');window.submitButton.onclick=()=>window.submits++;")
        original=cdp.send
        def send(method, params=None):
            if method=='DOM.scrollIntoViewIfNeeded':
                cdp.evaluate("window.submitButton.textContent='暂存离开'")
            return original(method,params)
        cdp.send=send
        publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
        publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
        with self.assertRaises(CDPError):publisher._click_publish()
        self.assertEqual(cdp.evaluate('window.submits'),0)

    def test_scheduled_button_with_switch_off_is_rejected(self):
        cdp=self.dom('<div class="post-time-wrapper"><input type="checkbox"></div><xhs-publish-btn submit-text="定时发布" submit-disabled="false" submit-loading="false"></xhs-publish-btn>', "window.submits=0;const root=document.querySelector('xhs-publish-btn').attachShadow({mode:'closed'});root.innerHTML='<button>定时发布</button>';root.querySelector('button').onclick=()=>window.submits++;")
        publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
        publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
        with self.assertRaises(CDPError):publisher._click_publish()
        self.assertEqual(cdp.evaluate('window.submits'),0)

    def test_disabled_or_loading_submit_never_clicked(self):
        for attribute in ('submit-disabled','submit-loading'):
            with self.subTest(attribute=attribute):
                cdp=self.dom(f'<xhs-publish-btn submit-text="发布" submit-disabled="false" submit-loading="false"></xhs-publish-btn>',f'''
                window.submits=0;const host=document.querySelector('xhs-publish-btn');host.setAttribute('{attribute}','true');
                const root=host.attachShadow({{mode:'closed'}});root.innerHTML='<button>发布</button>';
                root.querySelector('button').onclick=()=>window.submits++;
                ''')
                publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
                publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
                with self.assertRaises(CDPError):publisher._click_publish()
                self.assertEqual(cdp.evaluate('window.submits'),0)

    def test_legacy_submit_ignores_hidden_and_draft_buttons(self):
        cdp=self.dom('<button hidden>发布</button><button>暂存离开</button><button id="submit">发布</button>',"window.submits=0;document.querySelector('#submit').onclick=()=>window.submits++;")
        publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
        publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
        publisher._click_publish()
        self.assertEqual(cdp.evaluate('window.submits'),1)

    def test_ambiguous_submit_never_clicked(self):
        cdp=self.dom('<button>发布</button><button>发布</button>',"window.submits=0;for(const b of document.querySelectorAll('button'))b.onclick=()=>window.submits++;")
        publisher=XiaohongshuPublisherCore.__new__(XiaohongshuPublisherCore)
        publisher.cdp=cdp;publisher.ui=UIAutomator(cdp)
        with self.assertRaises(CDPError):publisher._click_publish()
        self.assertEqual(cdp.evaluate('window.submits'),0)

if __name__ == "__main__":
    unittest.main()
