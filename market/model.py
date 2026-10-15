PD,BI=6770,28278
obs=(9+2)/25.3; hum=(78+26)/25.3
v_obs=(9*PD+2*BI)/11; v_hum=(78*PD+26*BI)/104
print("rates obs %.3f hum %.3f  values obs %.0f hum %.0f"%(obs,hum,v_obs,v_hum))
waymo_ann=(271.3-170.7)*2
print("waymo annualised H1-2026 M mi",waymo_ann, "per veh @3500/3800", waymo_ann*1e6/3500, waymo_ann*1e6/3800)
mpv=55000
for yr,sc in [(2026,{'low':150e6,'base':210e6,'high':260e6}),(2030,{'low':20000*mpv,'base':35000*mpv,'high':100000*mpv})]:
  for k,m in sc.items():
    co=m/1e6*obs; ch=m/1e6*hum
    print(yr,k,"miles %.2fbn"%(m/1e9),"claims obs %d hum %d"%(co,ch),"value obs $%.1fM hum $%.1fM"%(co*v_obs/1e6,ch*v_hum/1e6),
          "recov(40%%x70%%) obs $%.2fM hum $%.1fM"%(co*v_obs*.28/1e6,ch*v_hum*.28/1e6))
# US regular
us_mi=3.294031e12
print("US liability claims implied", us_mi/1e6*hum/1e6, "M; value $bn", us_mi/1e6*hum*v_hum/1e9)
print("ISO freq x regs", 0.033*297.5e6/1e6)
print("UK claims/Mmi", 2.5e6/256.1e3, "avg", 11.9e9/2.5e6)
# L2
for yr,sc in [(2026,{'low':(10e9,0.5),'base':(20e9,0.75),'high':(30e9,1.0)}),(2030,{'low':(20e9,0.5),'base':(60e9,0.75),'high':(150e9,1.0)})]:
  for k,(m,r) in sc.items():
    c=m/1e6*r; print("L2",yr,k,"claims %d"%c,"value $%.0fM"%(c*v_hum/1e6),"recov(10%%x40%%) $%.1fM"%(c*v_hum*.04/1e6))
