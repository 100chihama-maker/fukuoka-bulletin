import unittest,json,tempfile,subprocess,sys,hashlib
from pathlib import Path
import update_feed as f

class FeedTests(unittest.TestCase):
    def test_work_editions_and_platform_links(self):
        data=json.loads((f.ROOT/'public/feed.json').read_text('utf8'))
        works=[e for e in data['entries'] if e['category']==6]
        self.assertEqual(len(works),14)
        self.assertEqual([sum(bool(e['workMask']&k) for e in works) for k in (1,2,4,8)],[9,2,3,1])
        kimi=next(e for e in works if e['id']=='work-kimisui')
        self.assertIn('SID0031774',kimi['workLinks'][0]['url'])
        self.assertIn('SID0038200',kimi['workLinks'][1]['url'])
        self.assertIn('レンタル',kimi['workLinks'][1]['label'])
        self.assertEqual(next(e for e in works if e['id']=='work-koishi')['workMask'],8)
        self.assertTrue(all(e['imageSlot']==-1 and e['start']==e['end']==0 for e in works))
        for bad in ('javascript:alert(1)','http://insecure.example/'):
            invalid=json.loads(json.dumps(data));next(e for e in invalid['entries'] if e['category']==6)['workLinks'][0]['url']=bad
            with self.assertRaises(ValueError):f.validate(invalid)
        invalid=json.loads(json.dumps(data));next(e for e in invalid['entries'] if e['category']==6)['workMask']=1.5
        with self.assertRaises(ValueError):f.validate(invalid)

    def test_city_fact_scope_and_history_preserved(self):
        data=json.loads((f.ROOT/'public/feed.json').read_text('utf8'))
        facts=[e for e in data['entries'] if e['category']==5]
        self.assertEqual([sum(e['factKind']==k for e in facts) for k in (1,2)],[12,8])
        self.assertTrue(all(e['scope'] and e['basis'] and e['url'].startswith('https://') for e in facts))
        self.assertTrue(all(e['start']==e['end']==0 and e['imageSlot']==-1 for e in facts))
        invalid=json.loads(json.dumps(data));next(e for e in invalid['entries'] if e['category']==5)['factKind']=99
        with self.assertRaises(ValueError):f.validate(invalid)
        history=json.loads(json.dumps(data));next(e for e in history['entries'] if e['id']=='fact-tenjin-robbery')['end']=20170420
        with self.assertRaises(ValueError):f.validate(history)
    def test_year_rollover(self):
        self.assertEqual(f.date_range('2026年12月25日〜1月11日'),(20261225,20270111))
        self.assertEqual(f.date_range('2027/1/16(土)～3/14(日)'),(20270116,20270314))
    def test_no_screening_from_date_header(self):
        raw='<section data-title="映画"><td data-date="20261120"><p>11/20</p></td><td data-date="20261121"><span>12:10</span></td></section>'
        e=f.parse_movies(raw,'7080','劇場','https://example.com/','test',20261119)
        self.assertEqual(len(e),1);self.assertEqual(e[0]['start'],20261121);self.assertEqual(e[0]['end'],20261121)
    def test_old_movie_does_not_claim_current_screening(self):
        raw='<section data-title="映画"><td data-date="20261120"><span>12:10</span></td></section>'
        self.assertEqual(f.parse_movies(raw,'7080','劇場','https://example.com/','test',20261121),[])
    def test_discrete_events_and_access_notice(self):
        raw='''<div class="ex_top_titles"><div class="exev_main_titles"><a href="/access"><h2>車でお越しの方へ</h2></a></div><p>2026年11月20日〜12月31日</p></div>
        <div class="eventlist_info"><div class="exev_main_titles"><a href="/talk"><h2>鑑賞会</h2></a></div><p>2027年1月16日 2027年2月13日</p></div>'''
        e=f.parse_events('kenbi',raw,'https://example.com/','美術館','test')
        self.assertEqual(len(e),1);self.assertEqual(e[0]['start'],20270116);self.assertEqual(e[0]['end'],20270116)
    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):f.validate({'schema':2,'entries':[]})
    def test_atlas_slots_do_not_change_when_entries_reorder(self):
        old={'imageSlots':{'2':{'old-removed':0,'still-here':1}}}
        def item(ident):return dict(id=ident,category=2,title=ident,subtitle='',imageSlot=-1)
        data={'entries':[item('new'),item('still-here')]}
        with tempfile.TemporaryDirectory() as temp:f.render(data,Path(temp),old)
        self.assertEqual(data['entries'][0]['imageSlot'],2)
        self.assertEqual(data['entries'][1]['imageSlot'],1)
        self.assertEqual(data['imageSlots']['2']['old-removed'],0)
    def test_published_feed(self):
        data=json.loads((f.ROOT/'public/feed.json').read_text(encoding='utf8'));f.validate(data)
        self.assertEqual({s['source'] for s in data['sources']},{s[0] for s in f.EVENT_SOURCES}|{'cinema-'+s[0] for s in f.THEATERS})
        self.assertTrue(all(s['ok'] or 'retained' in s for s in data['sources']))
        self.assertTrue(all(e['start']<=e['end'] for e in data['entries'] if e['category'] in [0,1]))
        self.assertFalse(any(e['title']=='車でお越しの方へ' for e in data['entries']))
    def test_failed_refresh_preserves_file(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'feed.json';original=(f.ROOT/'public/feed.json').read_bytes();p.write_bytes(original)
            subprocess.run([sys.executable,str(f.ROOT/'update_feed.py'),'--no-network','--output',temp],check=True,capture_output=True)
            self.assertEqual(p.read_bytes(),original)

if __name__=='__main__':unittest.main()
