fleet={'low':[3000,5000,8000,13000,20000],'base':[4000,8000,14000,22000,35000],'high':[4500,12000,28000,55000,100000]}
mpv=55000;obs,hum=0.435,4.111
need=1.0e6/(300*0.866)  # claims/yr at £300, 86.6% GM to cover £1.0M opex
print("break-even ADS claims/yr",round(need))
for s,f in fleet.items():
  row=[]
  for i,y in enumerate(range(2026,2031)):
    m=f[i]*mpv/1e6
    row.append("%d:obs%d/hum%d(25%%:%d)"%(y,m*obs,m*hum,m*hum*.25))
  print(s,row)
# projection
yrs=[2027,2028,2029]
cust=[3,8,15];sub=[40e3,60e3,80e3];ads=[150,400,900];l2=[1000,4000,10000]
heads=[6,8,11];other=[250e3,300e3,400e3]
cum=0
for i,y in enumerate(yrs):
  rs=cust[i]*sub[i];ra=ads[i]*300;rl=l2[i]*75;rev=rs+ra+rl
  cogs=ads[i]*40.3+l2[i]*7.3+0.10*rs;gp=rev-cogs
  opex=heads[i]*110e3+other[i];burn=opex-gp;cum+=burn
  print(y,"rev %.0f (sub %.0f ads %.0f l2 %.0f) GP %.0f GM %.1f%% opex %.0f burn %.0f cum %.0f"%(rev,rs,ra,rl,gp,gp/rev*100,opex,burn,cum))
print("COGS ADS: claude $0.27=%.2f GBP"%(0.27/1.33))
