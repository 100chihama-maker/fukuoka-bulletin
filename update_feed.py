"""Build the public VRChat feed. Network failures preserve each source's last good data.

Run: python update_feed.py --output public
Do not place API keys, Unity projects or user information in public/.
"""
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from urllib.parse import urljoin
import argparse,hashlib,json,re,urllib.request,time,os,html
from bs4 import BeautifulSoup
from PIL import Image,ImageDraw,ImageFont,ImageOps

ROOT=Path(__file__).resolve().parent
JST=timezone(timedelta(hours=9))
START,END=20261120,20270131
CATEGORIES=['イベント','映画','サークル・会場','お土産のお菓子','福岡ゆかりの人物','すごい・やばい福岡市','作品・舞台']
THEATERS=[
 ('7080','T・ジョイ博多','https://tjoy.jp/t-joy_hakata/'),
 ('7001','ユナイテッド・シネマ キャナルシティ13','https://www.unitedcinemas.jp/canalcity/'),
 ('7003','TOHOシネマズ 天神・ソラリア館','https://www.tohotheater.jp/theater/056/info/schedule.html'),
 ('7107','TOHOシネマズ ららぽーと福岡','https://www.tohotheater.jp/theater/087/info/schedule.html'),
 ('7103','kino cinéma 天神','https://kinocinema.jp/tenjin/'),
 ('7010','KBCシネマ','https://kbc-cinema.com/'),
 ('7096','ユナイテッド・シネマ 福岡ももち','https://www.unitedcinemas.jp/fukuokamomochi/'),
]
EVENT_SOURCES=[
 ('advent','https://www.crossroadfukuoka.jp/event/13738','福岡市内・各会場'),
 ('art','https://www.fukuoka-art-museum.jp/exhibition/','福岡市美術館 / 中央区大濠公園'),
 ('science','https://www.fukuokacity-kagakukan.jp/sp_exhibition/planning.html','福岡市科学館 / 中央区六本松'),
 ('kenbi','https://fukuoka-kenbi.jp/exhibition-event/','福岡県立美術館 / 中央区天神'),
]

def clean(s):return re.sub(r'\s+',' ',s).strip()
def key(s):return hashlib.sha256(s.encode()).hexdigest()[:16]
def intdate(d):return d.year*10000+d.month*100+d.day
def pretty(d):return f'{d//10000}/{d//100%100:02}/{d%100:02}'
def date_range(text,year=2026):
    values=re.findall(r'(?:(\d{4})[年/.\-])?(\d{1,2})[月/.\-](\d{1,2})(?:日)?',text)
    if not values:return None
    result=[]
    for yy,mm,dd in values[:2]:
        if yy:year=int(yy)
        try:d=date(year,int(mm),int(dd))
        except ValueError:return None
        if result and d<result[0] and not yy:d=date(year+1,int(mm),int(dd))
        result.append(d)
    return intdate(result[0]),intdate(result[-1])

def entry(source,cat,title,subtitle,body,url,stamp,start=0,end=0,**extra):
    return dict(id=source+'-'+key(title+url),sourceKey=source,category=cat,title=title[:180],subtitle=subtitle[:240],body=body[:1500],url=url,
                verifiedAt=stamp,start=start,end=end,status='公開情報を取得。変更・休止・料金は出典で確認してください。',
                tags='',imageSlot=-1,imageUrl='',imageCredit='ワールド用の案内カード（公式ポスターではありません）',**extra)

def parse_events(source,raw,url,venue,stamp):
    soup=BeautifulSoup(raw,'html.parser');found=[]
    if source=='advent':
        text=soup.get_text(' ',strip=True)
        config=[('博多','クリスマスマーケット 光の街・博多','博多区 / JR博多駅前広場'),('天神','TENJIN CHRISTMAS ADVENT','中央区 / 福岡市役所西側ふれあい広場'),('百道浜','Christmas Market ICE WORLD in 百道浜','早良区 / 福岡タワー前'),('渡辺通','渡辺通イルミネーション','中央区 / 渡辺通沿い')]
        for marker,title,where in config:
            part=text.split('【'+marker+'】',1)
            if len(part)<2:raise ValueError('Advent venue missing: '+marker)
            section=part[1].split('【',1)[0];dates=date_range(section)
            if not dates:raise ValueError('Advent date not found: '+marker)
            start,end=dates
            if start>END or end<START:continue
            extra='\nイルミネーションのみの会場です。' if marker=='渡辺通' else ''
            note=re.search(r'※([^※]+休業)',section)
            if note:extra+='\n'+clean(note.group(1))[:140]
            found.append(entry(source,0,title,where,f'開催期間：{pretty(start)}〜{pretty(end)}。\n会場ごとの時間・営業日は公式案内へ。'+extra,url,stamp,start,end))
        return found
    if source=='art':blocks=soup.select('.c-article-contents, .c-article-list__item')
    elif source=='science':blocks=[a for a in soup.select('a[id^="news_"]') if a.select_one('.description')]
    else:
        blocks=[]
        for h in soup.select('.exev_main_titles'):
            n=h
            for _ in range(4):
                n=n.parent
                if re.search(r'20\d\d年\d',n.get_text(' ',strip=True)):break
            if len(n.select('h2'))==1:blocks.append(n)
    for block in blocks:
        h=block.select_one('h1,h2');a=block if block.name=='a' else block.select_one('a[href]')
        if not h or not a:continue
        title=clean(h.get_text(' ',strip=True));text=clean(block.get_text(' ',strip=True))
        if any(t in title for t in ['車でお越し','駐車場','アクセス','臨時休館']):continue
        if source=='kenbi' and 'eventlist_info' in block.get('class',[]):
            # Separate dates are separate occurrences, never an invented continuous event.
            year=2026
            for yy,mm,dd in re.findall(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日',text):
                if yy:year=int(yy)
                day=intdate(date(year,int(mm),int(dd)))
                if not START<=day<=END:continue
                e=entry(source,0,title,venue,f'開催日：{pretty(day)}。\n対象の展覧会に関連するイベントです。申込の要否・観覧券・開始時刻は公式案内で確認してください。',urljoin(url,a['href']),stamp,day,day)
                e['id']+='-'+str(day);found.append(e)
            continue
        dates=date_range(text)
        if not dates:continue
        start,end=dates
        if start>END or end<START:continue
        title=re.sub(r'^［[^］]+］','',title)
        # The date prefix is kept in science titles because it is part of their official listing.
        e=entry(source,0,title,venue,f'会期：{pretty(start)}〜{pretty(end)}。\n開催日が対象期間に重なる展覧会です。休館日・開館時間・料金は公式の各展覧会ページへ。',urljoin(url,a['href']),stamp,start,end)
        found.append(e)
    # Some pages present the same exhibition twice. A stable URL+title key removes duplicates.
    return list({e['id']:e for e in found}.values())

def parse_movies(raw,theater_id,name,official,stamp,today):
    soup=BeautifulSoup(raw,'html.parser');found=[]
    for section in soup.select('section[data-title]'):
        title=clean(section['data-title']);days=set()
        for cell in section.select('td[data-date]'):
            d=int(cell['data-date'])
            # A header-only or empty cell is not evidence of a screening.
            times=[n.get_text(' ',strip=True) for n in cell.find_all(['a','span'],recursive=False)]
            if d>=max(START,today) and d<=END and any(re.search(r'\d{1,2}:\d{2}',t) for t in times):days.add(d)
        if not days:continue
        e=entry('cinema-'+theater_id,1,title,name,'上映回の掲載を確認した日：\n'+', '.join(pretty(d) for d in sorted(days))+'\n\n掲載期間の上映情報です。上映終了日や、それ以降の上映を保証するものではありません。時刻・字幕／吹替・座席は劇場公式へ。',official,stamp,min(days),max(days))
        e['status']='上映情報出典：映画.com（劇場公式URLは案内URL欄）。取得できた掲載期間のみ表示。'
        e['referenceUrl']=f'https://eiga.com/theater/40/400101/{theater_id}/'
        e['tags']=name+' 映画 上映'
        found.append(e)
    return found

def validate(data):
    if data.get('schema')!=1:raise ValueError('Unsupported schema')
    es=data.get('entries',[])
    if not 0<len(es)<=512:raise ValueError('Feed entry limit (1..512)')
    ids=set()
    for e in es:
        if e['id'] in ids:raise ValueError('Duplicate ID '+e['id'])
        ids.add(e['id'])
        if e['category'] not in range(7):raise ValueError('Category')
        if e['category']==6:
            if type(e.get('workMask')) is not int or not 1<=e['workMask']<=15 or not e.get('relationNote'):raise ValueError('Work type / relation missing')
            if e.get('start')!=0 or e.get('end')!=0 or e.get('imageSlot')!=-1:raise ValueError('Work must not expire or reference an atlas')
            links=e.get('workLinks')
            if not isinstance(links,list) or not 1<=len(links)<=8:raise ValueError('Work links missing')
            for link in links:
                if not isinstance(link,dict) or not isinstance(link.get('label'),str) or not 1<=len(link['label'])<=100 or not isinstance(link.get('url'),str) or not link['url'].startswith('https://') or len(link['url'])>2048:raise ValueError('Invalid work link')
        if e['category']==5:
            if e.get('factKind') not in (1,2) or not e.get('scope') or not e.get('basis'):raise ValueError('Fact classification / scope / date missing')
            if e.get('start')!=0 or e.get('end')!=0 or e.get('imageSlot')!=-1:raise ValueError('Evergreen fact must not expire or reference an atlas')
        if not e['url'].startswith('https://'):raise ValueError('Source URL')
        if not e['title'] or len(e['title'])>180 or len(e['body'])>1800:raise ValueError('Text length')
        if e['category']==0 and not (e['start']<=END and e['end']>=START and e['start']<=e['end']):raise ValueError('Event period')
        if e['imageSlot'] not in range(-1,16):raise ValueError('Atlas slot')
    if len(json.dumps(data,ensure_ascii=False))>1500000:raise ValueError('Feed too large')

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'FukuokaGatheringBulletin/1.0 (community guide, 15 minute refresh)'})
    with urllib.request.urlopen(req,timeout=30) as r:
        if int(r.headers.get('Content-Length',0))>4000000:raise ValueError('Source too large')
        return r.read(4000001).decode('utf8')

def wrap(text,font,width):
    lines=[];line=''
    for c in text:
        if c=='\n' or font.getlength(line+c)>width:
            lines.append(line);line='' if c=='\n' else c
        else:line+=c
    if line:lines.append(line)
    return lines

def poster(e):
    colors=['#186B72','#54466F','#406E50','#A76742','#3C5677'];color=colors[e['category']]
    canvas=Image.new('RGB',(512,512),'#F6F3E9');d=ImageDraw.Draw(canvas)
    small=ImageFont.truetype(str(ROOT/'FukuokaGuideSans.ttf'),20)
    big=ImageFont.truetype(str(ROOT/'FukuokaGuideSans.ttf'),33)
    d.rectangle((0,0,512,60),fill=color);d.text((24,15),CATEGORIES[e['category']],font=small,fill='white')
    image_path=ROOT/e.get('imageFile','MISSING')
    if e.get('imageFile') and image_path.is_file():
        im=Image.open(image_path).convert('RGB');im=ImageOps.contain(im,(480,366));canvas.paste(im,((512-im.width)//2,65+(366-im.height)//2))
        d.text((20,446),e['title'][:19],font=small,fill=color)
        d.text((20,477),'写真の出典・撮影時点は詳細へ',font=small,fill='#566466')
    else:
        # Original typography; never imitate an official poster or fabricate a photograph.
        d.ellipse((347,73,570,296),outline=color,width=3);d.ellipse((381,111,533,263),outline=color,width=2)
        y=105
        for l in wrap(e['title'],big,440)[:6]:d.text((28,y),l,font=big,fill=color);y+=44
        d.line((28,392,482,392),fill=color,width=3)
        for j,l in enumerate(wrap(e['subtitle'],small,450)[:2]):d.text((28,407+j*29),l,font=small,fill='#46565A')
        d.text((28,479),'FUKUOKA / ワールド用の案内',font=small,fill=color)
    return canvas

def render(data,out,previous=None):
    # Never recycle an image slot for a different article. This keeps cached atlases
    # from putting somebody else's photograph / poster beside newly fetched text.
    slots=(previous or {}).get('imageSlots',{})
    data['imageSlots']=slots
    for cat in range(5):
        atlas=Image.new('RGB',(2048,2048),'#F6F3E9');items=[e for e in data['entries'] if e['category']==cat]
        mapping=slots.setdefault(str(cat),{})
        for e in items:
            if e['id'] not in mapping and len(mapping)<16:mapping[e['id']]=next(n for n in range(16) if n not in mapping.values())
            slot=mapping.get(e['id'],-1);e['imageSlot']=slot
            if slot>=0:atlas.paste(poster(e),((slot%4)*512,(slot//4)*512))
        atlas.save(out/f'atlas-{cat}.jpg',quality=88,optimize=True)
    p=poster(dict(category=0,title='福岡の情報を、ここから。',subtitle='情報と出典は右の詳細へ'))
    p.save(out/'placeholder.jpg',quality=90)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='public');p.add_argument('--fixture-dir');p.add_argument('--now');p.add_argument('--no-network',action='store_true');a=p.parse_args()
    out=ROOT/a.output;out.mkdir(parents=True,exist_ok=True)
    now=datetime.fromisoformat(a.now) if a.now else datetime.now(JST);stamp=now.strftime('%Y-%m-%d %H:%M JST');today=intdate(now.date())
    previous=json.loads((out/'feed.json').read_text(encoding='utf8')) if (out/'feed.json').exists() else {'entries':[]}
    seed=json.loads((ROOT/'seed.json').read_text(encoding='utf8'))
    records=[e for e in seed if not e['id'].startswith('advent-')];statuses=[]
    sources=[(name,url,venue,None) for name,url,venue in EVENT_SOURCES]+[('cinema-'+i,f'https://eiga.com/theater/40/400101/{i}/',name,official) for i,name,official in THEATERS]
    for source,url,venue,official in sources:
        try:
            if a.fixture_dir:raw=(Path(a.fixture_dir)/(source+'.html')).read_text(encoding='utf8')
            elif a.no_network:raise RuntimeError('network intentionally disabled')
            else:raw=fetch(url)
            parsed=parse_movies(raw,source.split('-')[-1],venue,official,stamp,today) if official else parse_events(source,raw,url,venue,stamp)
            if not parsed:raise ValueError('No validated records; retain previous source data')
            records.extend(parsed);statuses.append(dict(source=source,url=url,ok=True,checkedAt=stamp,count=len(parsed)))
            print(source,len(parsed),flush=True)
        except Exception as ex:
            old=[dict(e) for e in previous['entries'] if e.get('sourceKey')==source]
            if not old and source=='advent':old=[dict(e) for e in seed if e['id'].startswith('advent-')]
            for e in old:e['status']='今回の取得に失敗。前回確認の情報です。 '+e.get('status','').replace('今回の取得に失敗。前回確認の情報です。 ','')
            records.extend(old);statuses.append(dict(source=source,url=url,ok=False,error=str(ex)[:180],retained=len(old)))
            print(source,'FAILED / retained',len(old),str(ex)[:100],flush=True)
    records=list({e['id']:e for e in records}.values())
    records.sort(key=lambda e:(e['category'],max(e.get('start',0),START) if e['category']==0 else e.get('start',0),e['title'],e['subtitle']))
    if len(records)>512:raise ValueError('Too many records: enlarge client capacity before publishing, do not silently truncate')
    data={'schema':1,'generatedAt':stamp,'windowStart':START,'windowEnd':END,'sources':statuses,'entries':records}
    # Separate source freshness from build time. All-failed refreshes keep the previous public feed intact.
    if previous['entries'] and not any(s['ok'] for s in statuses):
        (out/'last_attempt.json').write_text(json.dumps(statuses,ensure_ascii=False,indent=2),encoding='utf8');print('All sources failed: feed unchanged');return
    render(data,out,previous);validate(data)
    temp=out/'feed.tmp';temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');os.replace(temp,out/'feed.json')
    (out/'source_status.json').write_text(json.dumps(statuses,ensure_ascii=False,indent=2),encoding='utf8')
    print('FEED',len(records),'records;',sum(s['ok'] for s in statuses),'/',len(statuses),'sources')

if __name__=='__main__':main()
