obs,hum=0.435,4.111
ads_m={2026:{'low':.15e9,'base':.21e9,'high':.26e9},2030:{'low':1.10e9,'base':1.93e9,'high':5.5e9}}
l2={2026:{'low':5000,'base':15000,'high':30000},2030:{'low':10000,'base':45000,'high':150000}}
pa={'low':200,'base':400,'high':1000}; pl={'low':50,'base':100,'high':150}
som={2026:{'low':0,'base':.02,'high':.05},2030:{'low':.10,'base':.20,'high':.30}}
for y in (2026,2030):
  for s in ('low','base','high'):
    m=ads_m[y][s]/1e6
    tam=m*hum*pa[s]+l2[y][s]*pl[s]
    sam=m*obs*pa[s]+l2[y][s]*0.2*pl[s]
    td=ads_m[y][s]/3.294e12*27e9
    print(y,s,"TAM $%.2fM (ads %.2f l2 %.2f)"%(tam/1e6,m*hum*pa[s]/1e6,l2[y][s]*pl[s]/1e6),"SAM $%.2fM"%(sam/1e6),"SOM $%.3fM"%(sam*som[y][s]/1e6),
      "topdown ADS demand $%.1fM fee15-33%% $%.2f-%.2fM"%(td/1e6,td*.15/1e6,td*.33/1e6))
