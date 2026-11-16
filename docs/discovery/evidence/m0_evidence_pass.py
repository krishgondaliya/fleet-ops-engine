import requests, json, io, zipfile, gzip, datetime, math, re, collections
import xml.etree.ElementTree as ET
UA={"User-Agent":"independent-research-feasibility-check/0.1"}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
def hdrs(r):
    keep=["Content-Type","Content-Length","Content-Encoding","Cache-Control","ETag","Last-Modified","Age","Expires","Date","Server","X-Cache","Via"]
    return {k:r.headers.get(k) for k in keep if r.headers.get(k) is not None}
def get(url):
    t=now(); r=requests.get(url,headers=UA,timeout=60)
    print("\n### GET",url,"\n fetched_at_utc=",t,"status=",r.status_code,"decoded_bytes=",len(r.content),"wire_Content-Length=",r.headers.get("Content-Length"))
    print(" headers:",json.dumps(hdrs(r)))
    return r
def fieldinv(rows):
    n=len(rows); types=collections.defaultdict(collections.Counter); nulls=collections.Counter(); keys=set()
    for s in rows: keys|=set(s)
    for s in rows:
        for k in keys:
            if k not in s: nulls[k]+=1; continue
            v=s[k]
            if v is None: nulls[k]+=1
            types[k][type(v).__name__]+=1
    for k in sorted(keys):
        print("  %-30s types=%s missing_or_null=%d/%d (%.2f%%)"%(k,dict(types[k]),nulls[k],n,100*nulls[k]/n))
    return keys
d=get("https://gbfs.citibikenyc.com/gbfs/2.3/gbfs.json").json()
print(" discovery keys:",list(d),"version:",d.get("version"),"ttl:",d.get("ttl"),"last_updated:",repr(d.get("last_updated")))
feeds={}
for lang,v in d["data"].items():
    print(" lang",lang,[f["name"] for f in v["feeds"]])
    if lang=="en": feeds={f["name"]:f["url"] for f in v["feeds"]}
print(" en feeds:",json.dumps(feeds,indent=1))
si_r=get(feeds["station_information"]); si=si_r.json()
ss_r=get(feeds["station_status"]); ss=ss_r.json()
if "system_information" in feeds:
    sysinfo=get(feeds["system_information"]).json()
    print(" system_information:",json.dumps(sysinfo,default=str)[:1500])
for name,j,r in [("station_information",si,si_r),("station_status",ss,ss_r)]:
    print("\n== %s: version=%r ttl=%r last_updated=%r type=%s"%(name,j.get("version"),j.get("ttl"),j.get("last_updated"),type(j.get("last_updated")).__name__))
    print("   gzip_size_local=",len(gzip.compress(r.content)),"top keys",list(j),"data keys",list(j["data"]))
    rows=j["data"]["stations"]; print("   n_stations=",len(rows))
    fieldinv(rows)
    print("   sample record:",json.dumps(rows[0])[:900])
st=ss["data"]["stations"]; inf=si["data"]["stations"]
infk=set().union(*[set(s) for s in inf]); stk=set().union(*[set(s) for s in st])
for f in ["short_name","capacity","num_ebikes_available","vehicle_types_available","num_bikes_disabled","num_docks_disabled","is_installed","is_renting","is_returning"]:
    print("  EXISTS? %-26s station_information=%s station_status=%s"%(f,f in infk,f in stk))
vt=[s.get("vehicle_types_available") for s in st if s.get("vehicle_types_available")]
if vt: print(" vehicle_types_available example:",vt[0])
lr=[s.get("last_reported") for s in st if s.get("last_reported") is not None]
print(" last_reported types:",collections.Counter(type(x).__name__ for x in lr))
if lr and isinstance(lr[0],(int,float)) and isinstance(ss["last_updated"],(int,float)):
    lu=ss["last_updated"]; ages=sorted(lu-x for x in lr)
    print(" age(last_updated-last_reported) s: min=%s median=%s p90=%s max=%s n>1h=%d n>1d=%d"%(ages[0],ages[len(ages)//2],ages[int(.9*len(ages))],ages[-1],sum(a>3600 for a in ages),sum(a>86400 for a in ages)))
    print(" tiny last_reported (<1e6) count:",sum(1 for x in lr if x<10**6))
for f in ["is_installed","is_renting","is_returning"]:
    print("  %s value counts: %s"%(f,collections.Counter(s.get(f) for s in st)))
print("  num_bikes_available==0:",sum(1 for s in st if s.get("num_bikes_available")==0)," num_docks_available==0:",sum(1 for s in st if s.get("num_docks_available")==0))
ids_info={s["station_id"] for s in inf}; ids_st={s["station_id"] for s in st}
print(" station_id join info/status: info=%d status=%d both=%d info_only=%d status_only=%d"%(len(ids_info),len(ids_st),len(ids_info&ids_st),len(ids_info-ids_st),len(ids_st-ids_info)))
capm={s["station_id"]:s.get("capacity") for s in inf}
mis=[s for s in st if capm.get(s["station_id"]) is not None and isinstance(s.get("num_bikes_available"),int) and isinstance(s.get("num_docks_available"),int)]
over=sum(1 for s in mis if s["num_bikes_available"]+s["num_docks_available"]+(s.get("num_bikes_disabled") or 0)+(s.get("num_docks_disabled") or 0)>capm[s["station_id"]])
print(" bikes+docks+disabled > capacity: %d/%d"%(over,len(mis)))
print(" region_id counts:",collections.Counter(s.get("region_id") for s in inf).most_common(10))
print(" short_name examples:",[s.get("short_name") for s in inf[:5]]," station_type:",collections.Counter(s.get("station_type") for s in inf))
ttl=ss.get("ttl"); b=len(ss_r.content); gz=len(gzip.compress(ss_r.content))
if ttl:
    n=86400/ttl
    print("\nQ6 ttl=%ss polls/day=%.0f decoded=%dB/poll -> %.1f MB/day raw; gzip=%dB/poll -> %.1f MB/day"%(ttl,n,b,b*n/1e6,gz,gz*n/1e6))
def hav(a,b_,c,d_):
    R=6371.0; p=math.pi/180
    x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d_-b_)*p/2)**2
    return 2*R*math.asin(math.sqrt(x))
seeds={"A_midtown_cbd":(40.7540,-73.9840),"B_residential_brooklyn":(40.6760,-73.9800),"C_jersey_city_downtown":(40.7190,-74.0400)}
docked=[s for s in inf if s.get("lat") is not None and s.get("capacity")]
for nm,(la,lo) in seeds.items():
    cl=sorted(docked,key=lambda s:hav(la,lo,s["lat"],s["lon"]))[:40]
    lats=[s["lat"] for s in cl]; lons=[s["lon"] for s in cl]; cap=sum(s["capacity"] for s in cl)
    pref=collections.Counter(re.sub(r"[0-9.]+","#",str(s.get("short_name"))) for s in cl)
    print(" CLUSTER %s seed=(%s,%s): n=%d bbox lat[%.5f,%.5f] lon[%.5f,%.5f] total_capacity=%d radius_km=%.2f regions=%s short_name_patterns=%s"%(nm,la,lo,len(cl),min(lats),max(lats),min(lons),max(lons),cap,hav(la,lo,cl[-1]["lat"],cl[-1]["lon"]),dict(collections.Counter(s.get("region_id") for s in cl)),dict(pref)))
print("\n### trip bucket index", now())
keys=[];marker=""
while True:
    r=requests.get("https://s3.amazonaws.com/tripdata/"+("?marker="+marker if marker else ""),headers=UA,timeout=60)
    root=ET.fromstring(r.content); ns={"s":root.tag.split("}")[0].strip("{")}
    for c in root.findall("s:Contents",ns): keys.append((c.find("s:Key",ns).text,int(c.find("s:Size",ns).text),c.find("s:LastModified",ns).text))
    if root.find("s:IsTruncated",ns).text=="true": marker=keys[-1][0]
    else: break
print(" total keys:",len(keys)," status",r.status_code)
jc=sorted([k for k in keys if k[0].startswith("JC")])
print(" JC keys:",len(jc)," first:",jc[:2]," last 4:",jc[-4:])
nyc=sorted([k for k in keys if not k[0].startswith("JC")]); print(" non-JC count",len(nyc)," last 6:",nyc[-6:])
def ym(k):
    m=re.search(r"(\d{6})",k); return m.group(1) if m else ""
latest=max(jc,key=lambda k:ym(k[0])); print(" latest JC:",latest)
zr=get("https://s3.amazonaws.com/tripdata/"+latest[0])
import pandas as pd
z=zipfile.ZipFile(io.BytesIO(zr.content)); print(" zip members:",[(i.filename,i.file_size) for i in z.infolist()])
csvs=[i for i in z.infolist() if i.filename.lower().endswith(".csv") and "__MACOSX" not in i.filename]
df=pd.concat([pd.read_csv(z.open(i),dtype=str,keep_default_na=False) for i in csvs])
print(" rows:",len(df)," columns:",list(df.columns))
for c in df.columns:
    col=df[c]; empty=int((col.str.strip()=="").sum())
    num=pd.to_numeric(col.replace("",None),errors="coerce"); isnum=int(num.notna().sum())==(len(col)-empty)
    print("  %-20s empty=%d/%d (%.3f%%) all_numeric=%s nunique=%d examples=%s"%(c,empty,len(df),100*empty/len(df),isnum,col.nunique(),list(col[col!=""].head(3))))
for c in ["started_at","ended_at"]:
    print("  %s length dist: %s  has Z/offset: %d"%(c,dict(collections.Counter(df[c].str.len()).most_common(5)),int(df[c].str.contains(r"Z|[+-]\d\d:?\d\d$",regex=True).sum())))
s=pd.to_datetime(df["started_at"],format="mixed"); e=pd.to_datetime(df["ended_at"],format="mixed")
print("  started min/max:",s.min(),s.max()," ended min/max:",e.min(),e.max())
dur=(e-s).dt.total_seconds(); print("  duration: neg=",int((dur<0).sum())," median_s=",dur.median()," >1day=",int((dur>86400).sum()))
wk=s.dt.dayofweek<5
print("  weekday start-hour hist:",dict(sorted(collections.Counter(s[wk].dt.hour).items())))
print("  weekend start-hour hist:",dict(sorted(collections.Counter(s[~wk].dt.hour).items())))
sn={str(x.get("short_name")) for x in inf}; sid={str(x.get("station_id")) for x in inf}
for c in ["start_station_id","end_station_id"]:
    v=df[c][df[c]!=""]; u=set(v)
    print("  %s: nonempty=%d distinct=%d | short_name: trips %.2f%% distinct %d/%d | station_id: trips %.2f%% distinct %d/%d"%(c,len(v),len(u),v.isin(sn).mean()*100,len(u&sn),len(u),v.isin(sid).mean()*100,len(u&sid),len(u)))
    print("    unmatched-by-short_name:",sorted(u-sn)[:15])
