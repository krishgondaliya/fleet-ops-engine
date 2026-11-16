import requests, json, math, collections, datetime, gzip
UA={"User-Agent":"independent-research-feasibility-check/0.1"}
base="https://gbfs.lyft.com/gbfs/2.3/bkn/en/"
out={}
for f in ["station_information","station_status","system_regions"]:
    t=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    r=requests.get(base+f+".json",headers=UA,timeout=60)
    print(f,t,r.status_code,len(r.content),"ETag",r.headers.get("ETag"),"Cache-Control",r.headers.get("Cache-Control"),"Content-Encoding",r.headers.get("Content-Encoding"))
    out[f]=r.json()
print("regions:",json.dumps(out["system_regions"]["data"])[:800])
inf=out["station_information"]["data"]["stations"]; st={s["station_id"]:s for s in out["station_status"]["data"]["stations"]}
print("ttl/last_updated status:",out["station_status"]["ttl"],out["station_status"]["last_updated"])
def hav(a,b_,c,d_):
    R=6371.0; p=math.pi/180
    x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d_-b_)*p/2)**2
    return 2*R*math.asin(math.sqrt(x))
ok=[s for s in inf if s.get("capacity") and st.get(s["station_id"],{}).get("is_installed")==1]
print("eligible installed docked stations:",len(ok),"of",len(inf))
spec={"A_midtown_cbd":((40.7540,-73.9840),{"71"}),"B_residential_brooklyn":((40.6760,-73.9800),{"71"}),"C_jersey_city_hoboken":((40.7190,-74.0400),{"70","311"})}
for nm,((la,lo),regs) in spec.items():
    pool=[s for s in ok if s.get("region_id") in regs]
    cl=sorted(pool,key=lambda s:hav(la,lo,s["lat"],s["lon"]))[:40]
    lats=[s["lat"] for s in cl]; lons=[s["lon"] for s in cl]; caps=[s["capacity"] for s in cl]
    now_b=sum(st[s["station_id"]]["num_bikes_available"] for s in cl); now_d=sum(st[s["station_id"]]["num_docks_available"] for s in cl)
    print("\nCLUSTER %s seed=(%s,%s) regions=%s n=%d bbox lat[%.5f,%.5f] lon[%.5f,%.5f] total_capacity=%d mean_cap=%.1f median_cap=%d radius_km=%.2f snapshot_bikes=%d snapshot_docks=%d"%(nm,la,lo,sorted(regs),len(cl),min(lats),max(lats),min(lons),max(lons),sum(caps),sum(caps)/len(caps),sorted(caps)[len(caps)//2],hav(la,lo,cl[-1]["lat"],cl[-1]["lon"]),now_b,now_d))
    print(" short_names:",",".join(s["short_name"] for s in cl))
